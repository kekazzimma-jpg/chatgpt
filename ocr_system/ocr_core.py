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



def _merge_pdf_pages_from_single_calls(input_path: Path, api_key: str, model: str) -> Dict[str, Any]:
    pages_png = render_pdf_pages_png(input_path)
    merged_pages: List[Dict[str, Any]] = []
    global_warnings: List[str] = []

    for idx, png in enumerate(pages_png, start=1):
        logging.info("OCR pagina %s/%s", idx, len(pages_png))
        page_prompt = (
            get_structured_ocr_prompt()
            + f"\n\nIMPORTANTE: questa richiesta riguarda SOLO la pagina {idx}/{len(pages_png)}. "
            "Restituisci pages con una sola pagina."
        )
        raw = call_gemini_json(api_key, model, [{"text": page_prompt}, b64_part(png, "image/png")])
        norm = normalize_document(raw, input_path.name, "pdf")
        if norm.get("pages"):
            page = norm["pages"][0]
            page["page_number"] = idx
            merged_pages.append(page)
        global_warnings.extend(norm.get("document_info", {}).get("warnings", []))

    doc = {
        "document_info": {
            "source_filename": input_path.name,
            "source_type": "pdf",
            "page_count": len(merged_pages),
            "estimated_page_size": "A4",
            "orientation": "portrait",
            "language_estimate": "it",
            "document_visual_style": "documento amministrativo",
            "ocr_quality": "fair",
            "warnings": global_warnings,
        },
        "metadata": {
            "document_title": None,
            "document_date": None,
            "document_number": None,
            "protocol_number": None,
            "subject": None,
            "sender": None,
            "recipients": [],
            "mentioned_attachments": [],
            "mentioned_references": [],
        },
        "pages": merged_pages,
    }
    return normalize_document(doc, input_path.name, "pdf")


def _enrich_with_selectable_text(input_path: Path, document: Dict[str, Any]) -> Dict[str, Any]:
    if input_path.suffix.lower() != ".pdf":
        return document

    doc_pdf = fitz.open(input_path)
    pages = document.get("pages", [])
    for i, p in enumerate(pages):
        if i >= len(doc_pdf):
            break
        selectable = doc_pdf[i].get_text("text").strip()
        if not selectable:
            continue
        blocks = p.get("blocks", []) if isinstance(p.get("blocks"), list) else []
        joined = "\n".join(str(b.get("content", "")) for b in blocks)
        # se manca una parte significativa del testo digitale, aggiungi blocco integrazione
        if len(selectable) > 200 and selectable[:120] not in joined:
            blocks.append({
                "id": f"p{i+1}_selectable_fallback",
                "type": "preformatted",
                "content": selectable,
                "style": {
                    "alignment": "left",
                    "font_size_relative": "small",
                    "bold": False,
                    "italic": False,
                    "underline": False,
                    "all_caps": False,
                    "indent_level": 0,
                },
                "inline_spans": [{"text": selectable, "bold": False, "italic": False, "underline": False, "all_caps": False}],
                "reading_order": len(blocks) + 1,
                "source_page": i + 1,
            })
            p["blocks"] = blocks
            p.setdefault("page_notes", []).append("Aggiunto testo selezionabile per evitare perdita contenuto")

    return document


def _raw_text_fallback(input_path: Path) -> str:
    if input_path.suffix.lower() == ".pdf":
        doc = fitz.open(input_path)
        return "\n".join(p.get_text("text") for p in doc).strip()
    return "[illeggibile]"


def ocr_to_document(input_path: Path, api_key: str, model: str) -> Dict[str, Any]:
    source_type = "pdf" if input_path.suffix.lower() == ".pdf" else "image"
    try:
        if source_type == "pdf":
            normalized = _merge_pdf_pages_from_single_calls(input_path, api_key, model)
            return _enrich_with_selectable_text(input_path, normalized)

        img = input_path.read_bytes()
        mime = mimetypes.guess_type(input_path.name)[0] or "image/jpeg"
        raw_json = call_gemini_json(api_key, model, [{"text": get_structured_ocr_prompt()}, b64_part(img, mime)])
        return normalize_document(raw_json, input_path.name, source_type)
    except Exception as exc:
        logging.error("Fallback OCR JSON: %s", exc)
        return fallback_document(input_path.name, source_type, _raw_text_fallback(input_path), f"fallback attivato: {exc}")
