#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import traceback
from pathlib import Path
from typing import Dict, List

from exporters import export_docx, export_html, export_json, export_markdown, export_searchable_pdf
from ocr_core import ocr_to_document, resolve_api_key, resolve_model, resolve_requested_model_id


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


def _parse_formats(formati: List[str] | None) -> List[str]:
    if not formati:
        return ["json", "md"]
    seen = []
    for f in formati:
        x = f.strip().lower()
        if x and x not in seen:
            seen.append(x)
    return seen or ["json", "md"]


def genera_output(file_originale: str, output_dir: str | None = None, formati: List[str] | None = None, api_key: str = "", model: str = "") -> Dict[str, str | List[str] | None]:
    input_path = Path(file_originale).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"File non trovato: {input_path}")

    out_dir = Path(output_dir).resolve() if output_dir else input_path.parent / "OCR"
    out_dir.mkdir(exist_ok=True)

    active_formats = _parse_formats(formati)
    result: Dict[str, str | List[str] | None] = {"json": None, "md": None, "docx": None, "html": None, "pdf": None, "errors": []}

    api = resolve_api_key(api_key)
    if not api:
        raise SystemExit("API key mancante. Inseriscila in ocr_system/.env come GOOGLE_API_KEY=...")
    requested = resolve_model(model)
    active_model = resolve_requested_model_id(api, requested)
    logging.info("Modello richiesto: %s", requested)
    logging.info("Modello attivo: %s", active_model)

    document = ocr_to_document(input_path, api, active_model)

    # JSON sempre generato
    json_path = out_dir / f"{input_path.stem}.ocr.json"
    export_json(document, json_path)
    result["json"] = str(json_path)

    def safe_export(fmt: str, fn):
        try:
            p = fn()
            result[fmt] = str(p)
        except Exception as exc:
            logging.error("Exporter %s fallito: %s", fmt, exc)
            logging.error(traceback.format_exc())
            cast = result.get("errors")
            if isinstance(cast, list):
                cast.append(f"{fmt}: {exc}")

    if "md" in active_formats:
        safe_export("md", lambda: export_markdown(document, out_dir / f"{input_path.stem}.md"))
    if "html" in active_formats:
        safe_export("html", lambda: export_html(document, out_dir / f"{input_path.stem}.html"))
    if "docx" in active_formats:
        safe_export("docx", lambda: export_docx(document, out_dir / f"{input_path.stem}.docx"))
    if "pdf" in active_formats:
        safe_export("pdf", lambda: export_searchable_pdf(input_path, out_dir / f"{input_path.stem}.searchable.pdf"))

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR strutturato -> JSON + exporter")
    parser.add_argument("input_file")
    parser.add_argument("--model", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--formats", default="json,md,html,docx", help="es: json,md oppure json,md,docx,html,pdf")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    input_path = Path(args.input_file).expanduser().resolve()
    log_path = setup_logger(input_path)
    logging.info("Input: %s", input_path)

    try:
        fmt = [x.strip() for x in args.formats.split(",") if x.strip()]
        out = genera_output(
            file_originale=str(input_path),
            output_dir=args.output_dir or None,
            formati=fmt,
            api_key=args.api_key,
            model=args.model,
        )
        print(f"[OK] JSON: {out.get('json')}")
        if out.get("md"):
            print(f"[OK] Markdown: {out.get('md')}")
        if out.get("html"):
            print(f"[OK] HTML: {out.get('html')}")
        if out.get("docx"):
            print(f"[OK] DOCX: {out.get('docx')}")
        if out.get("pdf"):
            print(f"[OK] PDF: {out.get('pdf')}")
        errs = out.get("errors")
        if isinstance(errs, list) and errs:
            print(f"[WARN] Errori exporter: {' | '.join(errs)}")
        print(f"[OK] Log: {log_path}")
    except Exception as exc:
        logging.error("Errore durante conversione: %s", exc)
        logging.error(traceback.format_exc())
        print(f"[ERRORE] Conversione fallita. Vedi log: {log_path}")
        raise


if __name__ == "__main__":
    main()
