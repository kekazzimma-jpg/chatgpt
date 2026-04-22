from __future__ import annotations

from typing import Any, Dict, List

ALLOWED_BLOCK_TYPES = {
    "heading",
    "paragraph",
    "list",
    "table",
    "signature_block",
    "separator",
    "preformatted",
    "image_placeholder",
    "stamp_or_seal",
    "header_block",
    "footer_block",
    "address_block",
    "reference_block",
}


def default_style() -> Dict[str, Any]:
    return {
        "alignment": "left",
        "font_size_relative": "normal",
        "bold": False,
        "italic": False,
        "underline": False,
        "all_caps": False,
        "indent_level": 0,
    }


def fallback_document(source_filename: str, source_type: str, raw_text: str, warning: str) -> Dict[str, Any]:
    text = raw_text.strip() or "[illeggibile]"
    return {
        "document_info": {
            "source_filename": source_filename,
            "source_type": source_type,
            "page_count": 1,
            "estimated_page_size": "unknown",
            "orientation": "unknown",
            "language_estimate": "it",
            "document_visual_style": "fallback",
            "ocr_quality": "poor",
            "warnings": [warning],
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
        "pages": [
            {
                "page_number": 1,
                "header": "",
                "footer": "",
                "page_notes": [warning],
                "layout_quality": "poor",
                "blocks": [
                    {
                        "id": "p1_b1",
                        "type": "paragraph",
                        "content": text,
                        "style": default_style(),
                        "inline_spans": [
                            {"text": text, "bold": False, "italic": False, "underline": False, "all_caps": False}
                        ],
                        "reading_order": 1,
                        "source_page": 1,
                    }
                ],
            }
        ],
    }


def _normalize_block(block: Dict[str, Any], page_number: int, idx: int) -> Dict[str, Any]:
    t = block.get("type", "paragraph")
    if t not in ALLOWED_BLOCK_TYPES:
        t = "paragraph"

    content = str(block.get("content", "")).strip()
    style = block.get("style") if isinstance(block.get("style"), dict) else {}
    merged_style = default_style()
    merged_style.update(style)

    spans = block.get("inline_spans") if isinstance(block.get("inline_spans"), list) else []
    if spans:
        joined = "".join(str(sp.get("text", "")) for sp in spans if isinstance(sp, dict))
        if ("..." in joined or "…" in joined) and len(content) > len(joined):
            spans = [{"text": content, "bold": False, "italic": False, "underline": False, "all_caps": False}]
        elif len(joined.strip()) < max(20, int(len(content) * 0.6)):
            spans = [{"text": content, "bold": False, "italic": False, "underline": False, "all_caps": False}]
    if not spans:
        spans = [{"text": content, "bold": False, "italic": False, "underline": False, "all_caps": False}]

    out = {
        "id": block.get("id") or f"p{page_number}_b{idx}",
        "type": t,
        "content": content,
        "style": merged_style,
        "inline_spans": spans,
        "reading_order": int(block.get("reading_order", idx)),
        "source_page": int(block.get("source_page", page_number)),
    }

    for extra in ("level", "list_type", "items", "headers", "rows", "caption", "description", "relevance", "overlaps_text"):
        if extra in block:
            out[extra] = block[extra]

    return out


def normalize_document(doc: Dict[str, Any], source_filename: str, source_type: str) -> Dict[str, Any]:
    if not isinstance(doc, dict):
        return fallback_document(source_filename, source_type, "", "JSON non valido")

    di = doc.get("document_info") if isinstance(doc.get("document_info"), dict) else {}
    md = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    pages_in = doc.get("pages") if isinstance(doc.get("pages"), list) else []

    pages: List[Dict[str, Any]] = []
    for pidx, p in enumerate(pages_in, start=1):
        if not isinstance(p, dict):
            continue
        blocks_in = p.get("blocks") if isinstance(p.get("blocks"), list) else []
        blocks = [_normalize_block(b if isinstance(b, dict) else {}, pidx, i + 1) for i, b in enumerate(blocks_in)]
        pages.append(
            {
                "page_number": int(p.get("page_number", pidx)),
                "header": str(p.get("header", "")),
                "footer": str(p.get("footer", "")),
                "page_notes": p.get("page_notes", []) if isinstance(p.get("page_notes"), list) else [],
                "layout_quality": str(p.get("layout_quality", "fair")),
                "blocks": blocks,
            }
        )

    if not pages:
        return fallback_document(source_filename, source_type, "", "Nessuna pagina nel JSON OCR")

    return {
        "document_info": {
            "source_filename": di.get("source_filename", source_filename),
            "source_type": di.get("source_type", source_type),
            "page_count": di.get("page_count", len(pages)),
            "estimated_page_size": di.get("estimated_page_size", "unknown"),
            "orientation": di.get("orientation", "unknown"),
            "language_estimate": di.get("language_estimate", "it"),
            "document_visual_style": di.get("document_visual_style", "documento amministrativo"),
            "ocr_quality": di.get("ocr_quality", "fair"),
            "warnings": di.get("warnings", []) if isinstance(di.get("warnings"), list) else [],
        },
        "metadata": {
            "document_title": md.get("document_title"),
            "document_date": md.get("document_date"),
            "document_number": md.get("document_number"),
            "protocol_number": md.get("protocol_number"),
            "subject": md.get("subject"),
            "sender": md.get("sender"),
            "recipients": md.get("recipients", []) if isinstance(md.get("recipients"), list) else [],
            "mentioned_attachments": md.get("mentioned_attachments", []) if isinstance(md.get("mentioned_attachments"), list) else [],
            "mentioned_references": md.get("mentioned_references", []) if isinstance(md.get("mentioned_references"), list) else [],
        },
        "pages": pages,
    }
