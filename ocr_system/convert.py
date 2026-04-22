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
import io
import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

import fitz  # PyMuPDF
from PIL import Image
import requests


GOOGLE_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.1-flash-lite"


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

    # Strategia adattiva:
    # - digital: manda testo selezionabile + snapshot prima pagina per struttura
    # - scanned/mixed: manda immagini di tutte le pagine (OCR vision)
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


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR/estrazione adattiva verso Markdown + HTML.")
    parser.add_argument("input_file", help="PDF/JPG/JPEG/PNG")
    parser.add_argument("--model", default=os.getenv("GEMINI_MODEL", DEFAULT_MODEL))
    parser.add_argument("--api-key", default=os.getenv("GOOGLE_API_KEY", ""))
    args = parser.parse_args()

    input_path = Path(args.input_file).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"File non trovato: {input_path}")
    if not args.api_key:
        raise SystemExit("Imposta GOOGLE_API_KEY o passa --api-key.")

    suffix = input_path.suffix.lower()
    if suffix == ".pdf":
        md, html, analysis = extract_markdown_and_html_from_pdf(input_path, args.api_key, args.model)
    elif suffix in {".jpg", ".jpeg", ".png"}:
        md, html, analysis = extract_markdown_and_html_from_image(input_path, args.api_key, args.model)
    else:
        raise SystemExit("Formato non supportato. Usa PDF/JPG/JPEG/PNG.")

    md_path, html_path = save_outputs(input_path, md, html, analysis)
    print(f"[OK] Strategia: {analysis.kind}")
    print(f"[OK] Markdown: {md_path}")
    print(f"[OK] HTML: {html_path}")


if __name__ == "__main__":
    main()
