from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import re
import statistics
import subprocess
import tempfile
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


def render_pdf_pages_png(path: Path, dpi: int = 220) -> List[bytes]:
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


TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}


def call_gemini_json(api_key: str, model: str, parts: List[dict], retries: int = 5) -> Dict[str, Any]:
    url = f"{GOOGLE_API_BASE}/{model}:generateContent?key={api_key}"
    payload = {"contents": [{"parts": parts}], "generationConfig": {"response_mime_type": "application/json"}}

    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(url, json=payload, timeout=240)
            if r.status_code in TRANSIENT_HTTP_STATUSES:
                raise requests.HTTPError(f"transient status {r.status_code}", response=r)
            r.raise_for_status()
            data = r.json()
            try:
                txt = data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError) as key_exc:
                # Gemini può rispondere 200 senza 'parts' quando finishReason è
                # SAFETY / MAX_TOKENS / RECITATION, oppure quando promptFeedback
                # blocca la richiesta. Senza questa diagnostica si propagava un
                # KeyError: 'parts' opaco.
                cands = data.get("candidates") or [{}]
                finish = cands[0].get("finishReason") if isinstance(cands[0], dict) else None
                block = (data.get("promptFeedback") or {}).get("blockReason")
                raise RuntimeError(
                    f"Risposta Gemini senza testo (finishReason={finish}, blockReason={block})"
                ) from key_exc
            return json.loads(extract_json_text(txt))
        except Exception as exc:
            last = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            # Transitorio solo su status whitelistati o su errori di trasporto espliciti.
            # HTTPError generico su 4xx non transitori (400/401/403/404/...) NON deve ritentare:
            # mascherava API key errata, model id invalido o payload rotto.
            transient = (
                status in TRANSIENT_HTTP_STATUSES
                or isinstance(exc, (requests.ConnectionError, requests.Timeout))
            )
            if attempt < retries and transient:
                wait_s = min(20, 2 ** (attempt - 1))
                logging.warning("Errore Gemini transitorio (tentativo %s/%s, status=%s). Retry %ss", attempt, retries, status, wait_s)
                time.sleep(wait_s)
                continue
            if status is not None and status not in TRANSIENT_HTTP_STATUSES:
                logging.error("Errore Gemini non transitorio (status=%s): nessun retry. %s", status, exc)
            break
    raise RuntimeError(f"Gemini JSON fallito: {last}")


def _detect_alignment(x0: float, x1: float, page_width: float) -> str:
    cx = (x0 + x1) / 2
    if abs(cx - page_width / 2) < page_width * 0.10:
        return "center"
    if x0 > page_width * 0.55:
        return "right"
    return "left"


def _block_from_text_dict(page: fitz.Page, page_num: int) -> List[Dict[str, Any]]:
    data = page.get_text("dict")
    blocks_in = data.get("blocks", []) if isinstance(data, dict) else []

    # median font size for heading heuristic
    sizes = []
    for b in blocks_in:
        for l in b.get("lines", []) if isinstance(b, dict) else []:
            for sp in l.get("spans", []) if isinstance(l, dict) else []:
                if isinstance(sp, dict) and isinstance(sp.get("size"), (int, float)):
                    sizes.append(float(sp["size"]))
    med = statistics.median(sizes) if sizes else 11.0

    out: List[Dict[str, Any]] = []
    ridx = 1
    page_w = page.rect.width
    for b in blocks_in:
        if not isinstance(b, dict) or b.get("type") != 0:
            continue
        lines = b.get("lines", [])
        content_lines = []
        spans_out = []
        has_bold = False
        has_italic = False
        max_size = med

        for l in lines:
            line_txt = []
            for sp in l.get("spans", []) if isinstance(l, dict) else []:
                txt = str(sp.get("text", ""))
                if not txt:
                    continue
                flags = int(sp.get("flags", 0))
                bold = bool(flags & 16)
                italic = bool(flags & 2)
                has_bold = has_bold or bold
                has_italic = has_italic or italic
                max_size = max(max_size, float(sp.get("size", med)))
                line_txt.append(txt)
                spans_out.append({"text": txt, "bold": bold, "italic": italic, "underline": False, "all_caps": txt.isupper() and len(txt) > 2})
            if line_txt:
                content_lines.append("".join(line_txt))

        content = "\n".join([x for x in content_lines if x.strip()]).strip()
        if not content:
            continue

        # list detection
        if re.search(r"^\s*[-•]|^\s*\d+[\)\.]", content, flags=re.M):
            btype = "list"
        else:
            btype = "heading" if (has_bold and max_size >= med + 1.0 and len(content) < 120) else "paragraph"

        x0, y0, x1, y1 = b.get("bbox", [0, 0, page_w, 0])
        align = _detect_alignment(float(x0), float(x1), float(page_w))
        out.append(
            {
                "id": f"p{page_num}_b{ridx}",
                "type": btype,
                "content": content,
                "style": {
                    "alignment": align,
                    "font_size_relative": "large" if max_size >= med + 1.0 else "normal",
                    "bold": has_bold,
                    "italic": has_italic,
                    "underline": False,
                    "all_caps": content.isupper() and len(content) > 2,
                    "indent_level": 0,
                },
                "inline_spans": spans_out if spans_out else [{"text": content, "bold": has_bold, "italic": has_italic, "underline": False, "all_caps": False}],
                "reading_order": ridx,
                "source_page": page_num,
            }
        )
        ridx += 1

    return out


def _extract_selectable_page_doc(page: fitz.Page, input_path: Path, page_num: int) -> Dict[str, Any]:
    blocks = _block_from_text_dict(page, page_num)
    return {
        "document_info": {
            "source_filename": input_path.name,
            "source_type": "pdf",
            "page_count": 1,
            "estimated_page_size": "A4",
            "orientation": "portrait",
            "language_estimate": "it",
            "document_visual_style": "digitale/selezionabile",
            "ocr_quality": "good",
            "warnings": [],
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
        "pages": [{"page_number": page_num, "header": "", "footer": "", "page_notes": ["Estrazione da testo selezionabile locale"], "layout_quality": "good", "blocks": blocks}],
    }


_TESSERACT_LANG_CACHE: List[str] | None = None


def _tesseract_available_langs() -> List[str]:
    global _TESSERACT_LANG_CACHE
    if _TESSERACT_LANG_CACHE is not None:
        return _TESSERACT_LANG_CACHE
    try:
        # Import locale per evitare dipendenza circolare a top-level.
        from exporters import _find_tesseract_exe
        exe = _find_tesseract_exe()
        if not exe:
            _TESSERACT_LANG_CACHE = []
            return _TESSERACT_LANG_CACHE
        r = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=15)
        langs = [l.strip() for l in r.stdout.splitlines() if l.strip() and "List of" not in l]
        _TESSERACT_LANG_CACHE = langs
        return langs
    except Exception:
        _TESSERACT_LANG_CACHE = []
        return _TESSERACT_LANG_CACHE


def _tesseract_ocr_png_bytes(png_bytes: bytes) -> str:
    # Ripiego locale quando Gemini blocca o fallisce su una pagina raster.
    # Sceglie la lingua migliore disponibile (preferisce ita+eng, poi ita,
    # poi eng). Se tesseract non è raggiungibile o esce non-zero, ritorna "".
    from exporters import _find_tesseract_exe
    exe = _find_tesseract_exe()
    if not exe:
        return ""
    avail = _tesseract_available_langs()
    if "ita" in avail and "eng" in avail:
        lang = "ita+eng"
    elif "ita" in avail:
        lang = "ita"
    elif "eng" in avail:
        lang = "eng"
    else:
        return ""
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tf.write(png_bytes)
            tmp_path = tf.name
        r = subprocess.run(
            [exe, tmp_path, "-", "-l", lang],
            capture_output=True, timeout=180,
        )
        if r.returncode != 0:
            logging.warning("tesseract exit %s su pagina di fallback (lang=%s)", r.returncode, lang)
            return ""
        return r.stdout.decode("utf-8", errors="replace").strip()
    except Exception as exc:
        logging.warning("Errore esecuzione tesseract per fallback: %s", exc)
        return ""
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass


def _page_text_fallback_doc(text: str, input_path: Path, page_num: int, reason: str, is_secondary_ocr: bool = False) -> Dict[str, Any]:
    # Fallback per SINGOLA pagina quando Gemini vision non risponde o la
    # risposta non è parsabile. Serve a non buttare via le altre pagine.
    raw = (text or "").strip()
    if is_secondary_ocr and raw:
        # Marker visibile in tutti gli output (MD/HTML/DOCX) perché è inline
        # nel content del blocco: il lettore sa subito che il testo è meno
        # affidabile rispetto al resto del documento.
        prefix = "[Pagina recuperata con OCR locale tesseract — il testo potrebbe contenere errori di riconoscimento e perde la formattazione originale.]\n\n"
        content = prefix + raw
        ocr_quality = "fair"
        visual_style = "fallback OCR locale"
    elif raw:
        content = raw
        ocr_quality = "fair"
        visual_style = "fallback per-pagina"
    else:
        content = "[pagina illeggibile, OCR non disponibile]"
        ocr_quality = "poor"
        visual_style = "fallback per-pagina"
    block = {
        "id": f"p{page_num}_b1",
        "type": "paragraph",
        "content": content,
        "style": {},
        "inline_spans": [{"text": content, "bold": False, "italic": False, "underline": False, "all_caps": False}],
        "reading_order": 1,
        "source_page": page_num,
    }
    return {
        "document_info": {
            "source_filename": input_path.name,
            "source_type": "pdf",
            "page_count": 1,
            "estimated_page_size": "A4",
            "orientation": "portrait",
            "language_estimate": "it",
            "document_visual_style": visual_style,
            "ocr_quality": ocr_quality,
            "warnings": [f"pagina {page_num}: {visual_style} ({reason})"],
        },
        "metadata": {
            "document_title": None, "document_date": None, "document_number": None,
            "protocol_number": None, "subject": None, "sender": None,
            "recipients": [], "mentioned_attachments": [], "mentioned_references": [],
        },
        "pages": [{"page_number": page_num, "header": "", "footer": "",
                   "page_notes": [f"Fallback testo grezzo: {reason}"],
                   "layout_quality": "poor", "blocks": [block]}],
    }


def _merge_pdf_pages(input_path: Path, api_key: str, model: str) -> Dict[str, Any]:
    doc_pdf = fitz.open(input_path)
    pages_png = render_pdf_pages_png(input_path)
    merged_pages: List[Dict[str, Any]] = []
    warnings: List[str] = []
    total = len(doc_pdf)

    for idx in range(total):
        page = doc_pdf[idx]
        selectable_text = page.get_text("text").strip()
        page_num = idx + 1
        # Resilienza per-pagina: un errore su una pagina NON deve buttare via
        # le altre. In caso di failure inseriamo una pagina di fallback e
        # proseguiamo. Il searchable.pdf non dipende da questo path.
        try:
            if len(selectable_text) > 180:
                logging.info("OCR pagina %s/%s -> percorso testo selezionabile", page_num, total)
                norm = normalize_document(_extract_selectable_page_doc(page, input_path, page_num), input_path.name, "pdf")
            else:
                logging.info("OCR pagina %s/%s -> percorso Gemini vision", page_num, total)
                page_prompt = get_structured_ocr_prompt() + f"\n\nIMPORTANTE: questa richiesta riguarda SOLO la pagina {page_num}/{total}. Restituisci pages con una sola pagina."
                raw = call_gemini_json(api_key, model, [{"text": page_prompt}, b64_part(pages_png[idx], "image/png")])
                norm = normalize_document(raw, input_path.name, "pdf")
        except Exception as page_exc:
            # Tentativo 1 di ripiego: OCR locale tesseract sull'immagine raster.
            # Cattura sia i blocchi RECITATION/SAFETY di Gemini sia i fallimenti
            # di rete persistenti. Quando produce testo, lo segnaliamo nel
            # content del blocco perché il lettore deve sapere che la pagina ha
            # qualità inferiore al resto.
            logging.warning(
                "OCR Gemini pagina %s/%s fallito (%s): tento OCR locale tesseract come ripiego",
                page_num, total, page_exc,
            )
            secondary_text = _tesseract_ocr_png_bytes(pages_png[idx])
            if secondary_text:
                logging.info(
                    "OCR locale tesseract pagina %s/%s OK (%s caratteri recuperati)",
                    page_num, total, len(secondary_text),
                )
                fallback_text = secondary_text
                reason_str = f"Gemini fallito ({page_exc}); recuperato con OCR locale tesseract"
                is_secondary = True
            else:
                logging.warning(
                    "OCR locale tesseract anche fallito per pagina %s/%s: uso testo selezionabile (potrebbe essere vuoto)",
                    page_num, total,
                )
                fallback_text = selectable_text
                reason_str = f"Gemini fallito ({page_exc}); tesseract non disponibile o senza output"
                is_secondary = False
            norm = normalize_document(
                _page_text_fallback_doc(fallback_text, input_path, page_num, reason_str, is_secondary_ocr=is_secondary),
                input_path.name, "pdf",
            )
            warnings.append(f"pagina {page_num}: OCR fallito ({page_exc})")

        if norm.get("pages"):
            pg = norm["pages"][0]
            pg["page_number"] = page_num
            merged_pages.append(pg)
        warnings.extend(norm.get("document_info", {}).get("warnings", []))

    merged = {
        "document_info": {
            "source_filename": input_path.name,
            "source_type": "pdf",
            "page_count": len(merged_pages),
            "estimated_page_size": "A4",
            "orientation": "portrait",
            "language_estimate": "it",
            "document_visual_style": "misto (selectable+raster)",
            "ocr_quality": "fair",
            "warnings": warnings,
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
    return normalize_document(merged, input_path.name, "pdf")


def _raw_text_fallback(input_path: Path) -> str:
    if input_path.suffix.lower() == ".pdf":
        doc = fitz.open(input_path)
        return "\n".join(p.get_text("text") for p in doc).strip()
    return "[illeggibile]"


def ocr_to_document(input_path: Path, api_key: str, model: str) -> Dict[str, Any]:
    source_type = "pdf" if input_path.suffix.lower() == ".pdf" else "image"
    try:
        if source_type == "pdf":
            return _merge_pdf_pages(input_path, api_key, model)

        img = input_path.read_bytes()
        mime = mimetypes.guess_type(input_path.name)[0] or "image/jpeg"
        raw = call_gemini_json(api_key, model, [{"text": get_structured_ocr_prompt()}, b64_part(img, mime)])
        return normalize_document(raw, input_path.name, source_type)
    except Exception as exc:
        logging.error("Fallback OCR JSON: %s", exc)
        return fallback_document(input_path.name, source_type, _raw_text_fallback(input_path), f"fallback attivato: {exc}")
