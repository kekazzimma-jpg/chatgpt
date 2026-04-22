#!/usr/bin/env python3
"""OCR/adaptive extraction to Markdown + high-fidelity HTML."""

from __future__ import annotations

import argparse
import base64
import json
import logging
import mimetypes
import os
import re
import traceback
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import fitz  # PyMuPDF
import requests

GOOGLE_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.1-flash-lite"
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
CONFIG_PATH = BASE_DIR / "config.json"

PROMPT_MD = (
    "Estrai il testo completo mantenendo struttura, titoli, elenchi, tabelle e note. "
    "Mantieni il corsivo e il grassetto quando deducibili. Restituisci SOLO markdown valido."
)

PROMPT_HTML_PAGE = (
    "Ricostruisci SOLO la pagina mostrata nell'immagine come frammento HTML (senza <html>, <head>, <body>). "
    "Obiettivo: massima fedeltà visiva su impaginazione, corsivi, allineamenti, rientri, spaziature, elenchi puntati e margini. "
    "Usa contenitori con positioning CSS (preferibilmente assoluto all'interno della pagina) quando necessario. "
    "NON includere markdown fences (niente ```html). Non usare <img>, SVG base64, canvas o data URI. Restituisci SOLO HTML puro."
)


@dataclass
class SourceAnalysis:
    kind: str
    pages: int
    text_pages: int


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


def model_exists(api_key: str, model: str) -> bool:
    url = f"{GOOGLE_API_BASE}/{normalize_model_name(model)}?key={api_key}"
    return requests.get(url, timeout=60).status_code == 200


def list_models(api_key: str) -> List[str]:
    r = requests.get(f"{GOOGLE_API_BASE}?key={api_key}", timeout=60)
    r.raise_for_status()
    models = []
    for item in r.json().get("models", []):
        name = item.get("name", "")
        if name.startswith("models/"):
            models.append(name.replace("models/", ""))
    return models


def resolve_requested_model_id(api_key: str, requested_model: str) -> str:
    requested = normalize_model_name(requested_model)
    if model_exists(api_key, requested):
        return requested

    tokens = [t for t in re.split(r"[^a-z0-9]+", requested.lower()) if t]
    matches = []
    for m in list_models(api_key):
        low = m.lower()
        if all(t in low for t in tokens):
            matches.append(m)

    if len(matches) == 1:
        logging.warning("Model id esatto non trovato, uso corrispondenza AI Studio: %s", matches[0])
        return matches[0]

    shortlist = [m for m in list_models(api_key) if "flash" in m.lower() and "lite" in m.lower()][:10]
    raise SystemExit(
        f"Modello richiesto non trovato: '{requested_model}'. Nessun fallback automatico applicato. "
        f"Modelli simili disponibili: {', '.join(shortlist)}"
    )


def analyze_pdf(path: Path) -> SourceAnalysis:
    doc = fitz.open(path)
    text_pages = sum(1 for p in doc if p.get_text("text").strip())
    pages = len(doc)
    if text_pages == 0:
        kind = "pdf_scanned"
    elif text_pages == pages:
        kind = "pdf_digital"
    else:
        kind = "pdf_mixed"
    return SourceAnalysis(kind=kind, pages=pages, text_pages=text_pages)


def render_pdf_page_as_png(path: Path, page_index: int, dpi: int = 170) -> bytes:
    doc = fitz.open(path)
    page = doc[page_index]
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
    return pix.tobytes("png")


def get_pdf_page_size_pt(path: Path, page_index: int) -> Tuple[float, float]:
    doc = fitz.open(path)
    r = doc[page_index].rect
    return float(r.width), float(r.height)


def b64_part(content: bytes, mime: str) -> dict:
    return {"inline_data": {"mime_type": mime, "data": base64.b64encode(content).decode("utf-8")}}


def sanitize_model_output(text: str) -> str:
    t = text.strip()
    t = re.sub(r"^```(?:html|markdown)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```$", "", t)
    return t.strip()


def strip_heavy_media_from_html(html: str) -> str:
    cleaned = re.sub(r"<img[^>]*>", "", html, flags=re.IGNORECASE)
    cleaned = re.sub(r"data:image/[^;]+;base64,[A-Za-z0-9+/=\s]+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"background-image\s*:\s*url\([^)]*data:image[^)]*\)", "", cleaned, flags=re.IGNORECASE)
    return cleaned

def call_gemini(api_key: str, model: str, parts: List[dict], retries: int = 5) -> str:
    url = f"{GOOGLE_API_BASE}/{model}:generateContent?key={api_key}"
    payload = {"contents": [{"parts": parts}]}

    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(url, json=payload, timeout=240)
            if r.status_code in {429, 500, 502, 503, 504}:
                raise requests.HTTPError(f"{r.status_code} transient", response=r)
            r.raise_for_status()
            data = r.json()
            return sanitize_model_output(data["candidates"][0]["content"]["parts"][0]["text"])
        except Exception as exc:  # retry network/transient API issues
            last_exc = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            is_transient = status in {429, 500, 502, 503, 504} or isinstance(exc, requests.RequestException)
            if attempt < retries and is_transient:
                wait_s = min(20, 2 ** (attempt - 1))
                logging.warning("Gemini errore temporaneo (tentativo %s/%s, status=%s). Retry tra %ss.", attempt, retries, status, wait_s)
                time.sleep(wait_s)
                continue
            break

    raise RuntimeError(f"Chiamata Gemini fallita dopo {retries} tentativi: {last_exc}")

def build_html_document(page_fragments: List[str], page_sizes: List[Tuple[float, float]]) -> str:
    css = """
    body { margin: 0; background:#f3f3f3; font-family: 'Times New Roman', serif; }
    .doc-wrap { padding: 24px 0; }
    .page {
      position: relative;
      margin: 0 auto 24px auto;
      background: white;
      box-shadow: 0 2px 12px rgba(0,0,0,.15);
      overflow: hidden;
    }
    .page-content { position: relative; width: 100%; height: 100%; }
    """
    pages = []
    for idx, frag in enumerate(page_fragments):
        w, h = page_sizes[idx]
        pages.append(
            f'<section class="page" style="width:{w}pt;height:{h}pt;"><div class="page-content">{frag}</div></section>'
        )
    html = "<html><head><meta charset='utf-8'><style>" + css + "</style></head><body><div class='doc-wrap'>" + "".join(pages) + "</div></body></html>"
    return strip_heavy_media_from_html(html)


def render_pdf_pages_png(path: Path) -> List[bytes]:
    doc = fitz.open(path)
    return [render_pdf_page_as_png(path, i) for i in range(len(doc))]

def generate_html_from_pdf_pages(path: Path, api_key: str, model: str, page_pngs: List[bytes] | None = None) -> str:
    doc = fitz.open(path)
    fragments: List[str] = []
    sizes: List[Tuple[float, float]] = []
    if page_pngs is None:
        page_pngs = render_pdf_pages_png(path)

    for i, png in enumerate(page_pngs):
        logging.info("HTML pagina %s/%s", i + 1, len(page_pngs))
        try:
            frag = call_gemini(api_key, model, [{"text": PROMPT_HTML_PAGE}, b64_part(png, "image/png")])
        except Exception as exc:
            logging.error("HTML pagina %s fallita dopo retry: %s", i + 1, exc)
            frag = (
                "<div style='padding:24pt;font-family:Arial,sans-serif;color:#900'>"
                f"Errore generazione pagina {i + 1}. Controlla ocr_debug.log."
                "</div>"
            )
        fragments.append(frag)
        sizes.append(get_pdf_page_size_pt(path, i))

    return build_html_document(fragments, sizes)


def extract_markdown_from_pdf(path: Path, api_key: str, model: str, analysis: SourceAnalysis, page_pngs: List[bytes] | None = None) -> str:
    if analysis.kind == "pdf_digital":
        doc = fitz.open(path)
        full_text = "\n\n".join(p.get_text("text") for p in doc)
        cover = render_pdf_page_as_png(path, 0)
        return call_gemini(
            api_key,
            model,
            [{"text": PROMPT_MD + "\n\nTesto PDF:\n" + full_text[:400000]}, b64_part(cover, "image/png")],
        )

    if page_pngs is None:
        page_pngs = render_pdf_pages_png(path)
    image_parts = [b64_part(img, "image/png") for img in page_pngs]
    return call_gemini(api_key, model, [{"text": PROMPT_MD}] + image_parts)


def extract_from_image(path: Path, api_key: str, model: str) -> tuple[str, str, SourceAnalysis]:
    img = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    md = call_gemini(api_key, model, [{"text": PROMPT_MD}, b64_part(img, mime)])
    frag = call_gemini(api_key, model, [{"text": PROMPT_HTML_PAGE}, b64_part(img, mime)])

    pil_w, pil_h = (1240.0, 1754.0)
    html = build_html_document([frag], [(pil_w, pil_h)])
    return md, html, SourceAnalysis(kind="image", pages=1, text_pages=0)


def save_docx_from_html(html: str, output_path: Path) -> None:
    try:
        from html2docx import html2docx  # type: ignore
    except ImportError:
        logging.warning("html2docx non installato: salto output DOCX")
        return

    bio = html2docx(html, title=output_path.stem)
    output_path.write_bytes(bio.getvalue())

def save_outputs(input_path: Path, md: str, html: str, analysis: SourceAnalysis, with_docx: bool = True) -> tuple[Path, Path, Path | None]:
    out = input_path.parent / "OCR"
    out.mkdir(exist_ok=True)
    md_path = out / f"{input_path.stem}.md"
    html_path = out / f"{input_path.stem}.html"

    meta = f"<!-- source_kind={analysis.kind}; pages={analysis.pages}; text_pages={analysis.text_pages} -->\n\n"
    md_path.write_text(meta + sanitize_model_output(md), encoding="utf-8")
    html_path.write_text("<!-- " + meta.strip() + " -->\n" + sanitize_model_output(html), encoding="utf-8")
    docx_path = None
    if with_docx:
        docx_path = out / f"{input_path.stem}.docx"
        save_docx_from_html(sanitize_model_output(html), docx_path)
    return md_path, html_path, docx_path


def setup_logger(input_path: Path) -> Path:
    out = input_path.parent / "OCR"
    out.mkdir(exist_ok=True)
    log = out / "ocr_debug.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    fh = logging.FileHandler(log, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    root.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    root.addHandler(sh)
    return log


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR/estrazione adattiva verso Markdown + HTML.")
    parser.add_argument("input_file")
    parser.add_argument("--model", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--no-docx", action="store_true", help="Disabilita output DOCX")
    args = parser.parse_args()

    input_path = Path(args.input_file).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"File non trovato: {input_path}")

    log_path = setup_logger(input_path)
    logging.info("Input: %s", input_path)

    try:
        api_key = resolve_api_key(args.api_key)
        if not api_key:
            raise SystemExit("API key mancante. Inseriscila in ocr_system/.env come GOOGLE_API_KEY=...")

        requested = resolve_model(args.model)
        model = resolve_requested_model_id(api_key, requested)
        logging.info("Modello richiesto: %s", requested)
        logging.info("Modello attivo: %s", model)

        suffix = input_path.suffix.lower()
        if suffix == ".pdf":
            analysis = analyze_pdf(input_path)
            logging.info("Strategia: %s", analysis.kind)
            page_pngs = render_pdf_pages_png(input_path)
            md = extract_markdown_from_pdf(input_path, api_key, model, analysis, page_pngs=page_pngs)
            try:
                html = generate_html_from_pdf_pages(input_path, api_key, model, page_pngs=page_pngs)
            except Exception as exc:
                logging.error("Fallback HTML globale: %s", exc)
                html = "<html><body><pre>Errore generazione HTML. Vedi log.</pre></body></html>"
        elif suffix in {".jpg", ".jpeg", ".png"}:
            md, html, analysis = extract_from_image(input_path, api_key, model)
        else:
            raise SystemExit("Formato non supportato. Usa PDF/JPG/JPEG/PNG.")

        md_path, html_path, docx_path = save_outputs(input_path, md, html, analysis, with_docx=not args.no_docx)
        print(f"[OK] Markdown: {md_path}")
        print(f"[OK] HTML: {html_path}")
        if docx_path is not None:
            print(f"[OK] DOCX: {docx_path}")
        print(f"[OK] Log: {log_path}")
    except Exception as exc:
        logging.error("Errore durante conversione: %s", exc)
        logging.error(traceback.format_exc())
        print(f"[ERRORE] Conversione fallita. Vedi log: {log_path}")
        raise


if __name__ == "__main__":
    main()
