from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List

import fitz
import requests

from document_model import fallback_document, normalize_document
from prompts import get_structured_ocr_prompt

GOOGLE_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.1-flash-lite"
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
CONFIG_PATH = BASE_DIR / "config.json"


def parse_dotenv(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    out: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_local_config() -> Dict[str, str]:
    cfg: Dict[str, str] = {}
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update({str(k): str(v) for k, v in data.items()})
        except json.JSONDecodeError:
            pass
    cfg.update(parse_dotenv(ENV_PATH))
    return cfg


def resolve_api_key(cli_api_key: str) -> str:
    if cli_api_key:
        return cli_api_key
    if os.getenv("GOOGLE_API_KEY"):
        return os.getenv("GOOGLE_API_KEY", "")
    return load_local_config().get("GOOGLE_API_KEY", "")


def resolve_model(cli_model: str) -> str:
    if cli_model:
        return cli_model
    if os.getenv("GEMINI_MODEL"):
        return os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    return load_local_config().get("GEMINI_MODEL", DEFAULT_MODEL)


def normalize_model_name(model: str) -> str:
    return model.replace("models/", "").strip()


def list_models(api_key: str) -> List[str]:
    r = requests.get(f"{GOOGLE_API_BASE}?key={api_key}", timeout=60)
    r.raise_for_status()
    return [m.get("name", "").replace("models/", "") for m in r.json().get("models", []) if m.get("name", "").startswith("models/")]


def model_exists(api_key: str, model: str) -> bool:
    r = requests.get(f"{GOOGLE_API_BASE}/{normalize_model_name(model)}?key={api_key}", timeout=60)
    return r.status_code == 200


def resolve_requested_model_id(api_key: str, requested_model: str) -> str:
    requested = normalize_model_name(requested_model)
    if model_exists(api_key, requested):
        return requested
    toks = [t for t in re.split(r"[^a-z0-9]+", requested.lower()) if t]
    matches = [m for m in list_models(api_key) if all(t in m.lower() for t in toks)]
    if len(matches) == 1:
        logging.warning("Model id esatto non trovato, uso corrispondenza AI Studio: %s", matches[0])
        return matches[0]
    raise SystemExit(f"Modello richiesto non trovato: {requested_model}")


def render_pdf_pages_png(path: Path, dpi: int = 170) -> List[bytes]:
    doc = fitz.open(path)
    images: List[bytes] = []
    for i in range(len(doc)):
        pix = doc[i].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
        images.append(pix.tobytes("png"))
    return images


def b64_part(content: bytes, mime: str) -> dict:
    return {"inline_data": {"mime_type": mime, "data": base64.b64encode(content).decode("utf-8")}}


def extract_json_text(raw: str) -> str:
    t = raw.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```$", "", t)
    if t.startswith("{"):
        return t
    m = re.search(r"\{[\s\S]*\}", t)
    return m.group(0) if m else t


def call_gemini_json(api_key: str, model: str, parts: List[dict], retries: int = 5) -> Dict[str, Any]:
    url = f"{GOOGLE_API_BASE}/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"response_mime_type": "application/json"},
    }
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(url, json=payload, timeout=240)
            if r.status_code in {429, 500, 502, 503, 504}:
                raise requests.HTTPError("transient", response=r)
            r.raise_for_status()
            data = r.json()
            txt = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(extract_json_text(txt))
        except Exception as exc:
            last = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            transient = status in {429, 500, 502, 503, 504} or isinstance(exc, requests.RequestException)
            if attempt < retries and transient:
                wait_s = min(20, 2 ** (attempt - 1))
                logging.warning("Errore Gemini (tentativo %s/%s, status=%s). Retry %ss", attempt, retries, status, wait_s)
                time.sleep(wait_s)
                continue
            break
    raise RuntimeError(f"Gemini JSON fallito: {last}")


def _raw_text_fallback(input_path: Path) -> str:
    if input_path.suffix.lower() == ".pdf":
        doc = fitz.open(input_path)
        return "\n".join(p.get_text("text") for p in doc).strip()
    return "[illeggibile]"


def ocr_to_document(input_path: Path, api_key: str, model: str) -> Dict[str, Any]:
    source_type = "pdf" if input_path.suffix.lower() == ".pdf" else "image"
    try:
        if source_type == "pdf":
            pages = render_pdf_pages_png(input_path)
            parts = [{"text": get_structured_ocr_prompt()}] + [b64_part(p, "image/png") for p in pages]
        else:
            img = input_path.read_bytes()
            mime = mimetypes.guess_type(input_path.name)[0] or "image/jpeg"
            parts = [{"text": get_structured_ocr_prompt()}, b64_part(img, mime)]

        raw_json = call_gemini_json(api_key, model, parts)
        return normalize_document(raw_json, input_path.name, source_type)
    except Exception as exc:
        logging.error("Fallback OCR JSON: %s", exc)
        return fallback_document(input_path.name, source_type, _raw_text_fallback(input_path), f"fallback attivato: {exc}")
