#!/usr/bin/env python3
"""
Pipeline OCR/adaptive extraction:
- Input: PDF (scanned, digital, mixed) or JPG/JPEG/PNG.
- Output: Markdown + HTML in ./OCR folder near source file.
- LLM backend: Gemini model (default: gemini-3.1-flash-lite) via Google AI Studio API key.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import mimetypes
import os
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import fitz  # PyMuPDF
import requests

GOOGLE_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.5-flash-lite"
FALLBACK_MODELS = ["gemini-2.5-flash-lite", "gemini-2.0-flash-lite"]
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
CONFIG_PATH = BASE_DIR / "config.json"


@dataclass
class SourceAnalysis:
    kind: str  # image | pdf_digital | pdf_scanned | pdf_mixed
    pages: int
    text_pages: int


PROMPT_MD = (
    "Estrai il testo dal documento mantenendo struttura, titoli, elenchi, tabelle "
    "(in markdown), e note. Restituisci SOLO markdown valido."
)

PROMPT_HTML = (
    "Ricostruisci il documento in HTML completo (<html><head>...</head><body>...</body>) "
    "preservando il più possibile impaginazione e formattazione visiva. "
    "Usa CSS inline o in <style>. Restituisci SOLO HTML valido."
)


def parse_dotenv(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    data: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def load_local_config() -> Dict[str, str]:
    cfg: Dict[str, str] = {}
    if CONFIG_PATH.exists():
        try:
            loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cfg.update({str(k): str(v) for k, v in loaded.items()})
        except json.JSONDecodeError:
            pass
    cfg.update(parse_dotenv(ENV_PATH))
    return cfg


def resolve_api_key(cli_api_key: str) -> str:
    if cli_api_key:
        return cli_api_key
    if os.getenv("GOOGLE_API_KEY"):
        return os.getenv("GOOGLE_API_KEY", "")
    local_cfg = load_local_config()
    return local_cfg.get("GOOGLE_API_KEY", "")


def resolve_model(cli_model: str) -> str:
    if cli_model:
        return cli_model
    if os.getenv("GEMINI_MODEL"):
        return os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    local_cfg = load_local_config()
    return local_cfg.get("GEMINI_MODEL", DEFAULT_MODEL)


def normalize_model_name(model: str) -> str:
    return model.replace("models/", "").strip()


def model_exists(api_key: str, model: str) -> bool:
    m = normalize_model_name(model)
    url = f"{GOOGLE_API_BASE}/{m}?key={api_key}"
    r = requests.get(url, timeout=60)
    return r.status_code == 200


def resolve_working_model(api_key: str, requested_model: str) -> str:
    candidates = [normalize_model_name(requested_model)]
    for fallback in FALLBACK_MODELS:
        f = normalize_model_name(fallback)
        if f not in candidates:
            candidates.append(f)

    for m in candidates:
        if model_exists(api_key, m):
            if m != normalize_model_name(requested_model):
                logging.warning("Modello '%s' non disponibile, uso fallback '%s'.", requested_model, m)
            return m

    raise SystemExit(
        "Nessun modello disponibile con questa API key. Verifica AI Studio o cambia GEMINI_MODEL. "
        f"Tentati: {', '.join(candidates)}"
    )


def analyze_pdf(path: Path) -> SourceAnalysis:
    doc = fitz.open(path)
    text_pages = 0
    for page in doc:
        txt = page.get_text("text").strip()
        if txt:
            text_pages += 1
    pages = len(doc)
    if text_pages == 0:
        kind = "pdf_scanned"
    elif text_pages == pages:
        kind = "pdf_digital"
    else:
        kind = "pdf_mixed"
    return SourceAnalysis(kind=kind, pages=pages, text_pages=text_pages)


def render_pdf_page_as_png(path: Path, page_index: int, dpi: int = 220) -> bytes:
    doc = fitz.open(path)
    page = doc[page_index]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return pix.tobytes("png")


def b64_part(content: bytes, mime: str) -> dict:
    return {
        "inline_data": {
            "mime_type": mime,
            "data": base64.b64encode(content).decode("utf-8"),
        }
    }


def call_gemini(api_key: str, model: str, parts: List[dict]) -> str:
    url = f"{GOOGLE_API_BASE}/{model}:generateContent?key={api_key}"
    payload = {"contents": [{"parts": parts}]}
    r = requests.post(url, json=payload, timeout=180)
    r.raise_for_status()
    data = r.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Risposta Gemini inattesa: {json.dumps(data)[:1000]}") from exc


def extract_markdown_and_html_from_pdf(path: Path, api_key: str, model: str) -> tuple[str, str, SourceAnalysis]:
    analysis = analyze_pdf(path)

    if analysis.kind == "pdf_digital":
        doc = fitz.open(path)
        full_text = "\n\n".join([p.get_text("text") for p in doc])
        cover_png = render_pdf_page_as_png(path, 0)

        md = call_gemini(
            api_key,
            model,
            [
                {"text": PROMPT_MD + "\n\nTesto estratto dal PDF:\n" + full_text[:400000]},
                b64_part(cover_png, "image/png"),
            ],
        )
        html = call_gemini(
            api_key,
            model,
            [
                {"text": PROMPT_HTML + "\n\nTesto estratto dal PDF:\n" + full_text[:400000]},
                b64_part(cover_png, "image/png"),
            ],
        )
        return md, html, analysis

    doc = fitz.open(path)
    image_parts = [b64_part(render_pdf_page_as_png(path, i), "image/png") for i in range(len(doc))]

    md = call_gemini(api_key, model, [{"text": PROMPT_MD}] + image_parts)
    html = call_gemini(api_key, model, [{"text": PROMPT_HTML}] + image_parts)
    return md, html, analysis


def extract_markdown_and_html_from_image(path: Path, api_key: str, model: str) -> tuple[str, str, SourceAnalysis]:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    image_bytes = path.read_bytes()
    md = call_gemini(api_key, model, [{"text": PROMPT_MD}, b64_part(image_bytes, mime)])
    html = call_gemini(api_key, model, [{"text": PROMPT_HTML}, b64_part(image_bytes, mime)])
    return md, html, SourceAnalysis(kind="image", pages=1, text_pages=0)


def save_outputs(input_path: Path, md: str, html: str, analysis: SourceAnalysis) -> tuple[Path, Path]:
    out_dir = input_path.parent / "OCR"
    out_dir.mkdir(exist_ok=True)

    stem = input_path.stem
    md_path = out_dir / f"{stem}.md"
    html_path = out_dir / f"{stem}.html"

    metadata = (
        f"<!-- source_kind={analysis.kind}; pages={analysis.pages}; "
        f"text_pages={analysis.text_pages} -->\n\n"
    )
    md_path.write_text(metadata + md, encoding="utf-8")
    html_path.write_text(f"<!-- {metadata.strip()} -->\n{html}", encoding="utf-8")
    return md_path, html_path


def setup_logger(input_path: Path) -> Path:
    out_dir = input_path.parent / "OCR"
    out_dir.mkdir(exist_ok=True)
    log_path = out_dir / "ocr_debug.log"

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(sh)
    return log_path


def log_step(message: str) -> None:
    logging.info(message)


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR/estrazione adattiva verso Markdown + HTML.")
    parser.add_argument("input_file", help="PDF/JPG/JPEG/PNG")
    parser.add_argument("--model", default="")
    parser.add_argument("--api-key", default="")
    args = parser.parse_args()

    input_path = Path(args.input_file).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"File non trovato: {input_path}")

    log_path = setup_logger(input_path)
    log_step(f"Input: {input_path}")

    try:
        requested_model = resolve_model(args.model)
        api_key = resolve_api_key(args.api_key)

        if not api_key:
            raise SystemExit(
                "API key mancante. Inseriscila in ocr_system/.env come GOOGLE_API_KEY=... "
                "oppure usa --api-key."
            )

        model = resolve_working_model(api_key, requested_model)
        log_step(f"Modello richiesto: {requested_model}")
        log_step(f"Modello attivo: {model}")
        suffix = input_path.suffix.lower()
        log_step(f"Rilevato formato: {suffix}")

        if suffix == ".pdf":
            log_step("Avvio estrazione PDF...")
            md, html, analysis = extract_markdown_and_html_from_pdf(input_path, api_key, model)
        elif suffix in {".jpg", ".jpeg", ".png"}:
            log_step("Avvio estrazione immagine...")
            md, html, analysis = extract_markdown_and_html_from_image(input_path, api_key, model)
        else:
            raise SystemExit("Formato non supportato. Usa PDF/JPG/JPEG/PNG.")

        md_path, html_path = save_outputs(input_path, md, html, analysis)
        log_step(f"Completato con strategia: {analysis.kind}")
        print(f"[OK] Strategia: {analysis.kind}")
        print(f"[OK] Modello: {model}")
        print(f"[OK] Markdown: {md_path}")
        print(f"[OK] HTML: {html_path}")
        print(f"[OK] Log: {log_path}")
    except Exception as exc:
        logging.error("Errore durante conversione: %s", exc)
        logging.error(traceback.format_exc())
        print(f"[ERRORE] Conversione fallita. Vedi log: {log_path}")
        raise


if __name__ == "__main__":
    main()
