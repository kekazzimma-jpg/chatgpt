from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def export_json(document: Dict[str, Any], out_path: Path) -> Path:
    out_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _style_wrap_md(text: str, span: Dict[str, Any]) -> str:
    t = text
    if span.get("all_caps"):
        t = t.upper()
    if span.get("underline"):
        t = f"<u>{t}</u>"
    if span.get("italic"):
        t = f"*{t}*"
    if span.get("bold"):
        t = f"**{t}**"
    return t


def _block_text_md(block: Dict[str, Any]) -> str:
    spans = block.get("inline_spans", [])
    if spans:
        return "".join(_style_wrap_md(str(s.get("text", "")), s) for s in spans)
    return str(block.get("content", ""))


def export_markdown(document: Dict[str, Any], out_path: Path, include_headers: bool = False, include_footers: bool = False) -> Path:
    lines: List[str] = []
    for page in document.get("pages", []):
        pnum = page.get("page_number", "?")
        lines.append(f"<!-- Pagina {pnum} -->")
        if include_headers and page.get("header"):
            lines.append(page["header"])
            lines.append("")
        for block in page.get("blocks", []):
            btype = block.get("type", "paragraph")
            txt = _block_text_md(block).strip()
            if btype == "heading":
                level = int(block.get("level", 2))
                level = max(1, min(3, level))
                lines.append("#" * level + " " + txt)
            elif btype == "list":
                ltype = block.get("list_type", "unordered")
                items = block.get("items", []) if isinstance(block.get("items"), list) else []
                for i, item in enumerate(items, start=1):
                    itxt = str(item.get("content", "")).strip()
                    lines.append((f"{i}. " if ltype == "ordered" else "- ") + itxt)
            elif btype == "table":
                headers = block.get("headers", []) if isinstance(block.get("headers"), list) else []
                rows = block.get("rows", []) if isinstance(block.get("rows"), list) else []
                if headers:
                    lines.append("| " + " | ".join(map(str, headers)) + " |")
                    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
                for row in rows:
                    if isinstance(row, list):
                        lines.append("| " + " | ".join(map(str, row)) + " |")
            elif btype == "signature_block":
                lines.append("---")
                lines.append(txt)
            elif btype == "separator":
                lines.append("---")
            elif btype in {"image_placeholder", "stamp_or_seal"}:
                desc = block.get("description") or txt or "elemento non testuale"
                lines.append(f"[Nota: {desc}]")
            else:
                lines.append(txt)
            lines.append("")
        if include_footers and page.get("footer"):
            lines.append(page["footer"])
            lines.append("")
    out_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return out_path


def export_html(document: Dict[str, Any], out_path: Path) -> Path:
    html: List[str] = ["<html><head><meta charset='utf-8'><style>body{font-family:Times New Roman,serif;} .page{margin:24px auto;max-width:900px;padding:24px;border:1px solid #ddd;} .sig{margin-top:18px;} .note{color:#666;font-style:italic;}</style></head><body>"]
    for page in document.get("pages", []):
        html.append("<section class='page'>")
        html.append(f"<!-- Pagina {page.get('page_number')} -->")
        for block in page.get("blocks", []):
            t = block.get("type", "paragraph")
            content = block.get("content", "")
            if t == "heading":
                lvl = max(1, min(3, int(block.get("level", 2))))
                html.append(f"<h{lvl}>{content}</h{lvl}>")
            elif t == "list":
                items = block.get("items", []) if isinstance(block.get("items"), list) else []
                tag = "ol" if block.get("list_type") == "ordered" else "ul"
                html.append(f"<{tag}>")
                for it in items:
                    html.append(f"<li>{it.get('content','')}</li>")
                html.append(f"</{tag}>")
            elif t == "table":
                html.append("<table border='1' cellspacing='0' cellpadding='4'>")
                headers = block.get("headers", []) if isinstance(block.get("headers"), list) else []
                if headers:
                    html.append("<tr>" + "".join([f"<th>{h}</th>" for h in headers]) + "</tr>")
                for r in block.get("rows", []) if isinstance(block.get("rows"), list) else []:
                    if isinstance(r, list):
                        html.append("<tr>" + "".join([f"<td>{c}</td>" for c in r]) + "</tr>")
                html.append("</table>")
            elif t == "signature_block":
                html.append(f"<div class='sig'><hr/><p>{content}</p></div>")
            elif t == "separator":
                html.append("<hr/>")
            elif t in {"image_placeholder", "stamp_or_seal"}:
                html.append(f"<p class='note'>[{block.get('description') or content}]</p>")
            else:
                html.append(f"<p>{content}</p>")
        html.append("</section>")
    html.append("</body></html>")
    out_path.write_text("\n".join(html), encoding="utf-8")
    return out_path


def export_docx(document: Dict[str, Any], out_path: Path) -> Path:
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    section = doc.sections[0]
    section.top_margin = Pt(72)
    section.bottom_margin = Pt(72)
    section.left_margin = Pt(72)
    section.right_margin = Pt(72)

    def size_pt(sz: str) -> int:
        if sz == "small":
            return 9
        if sz == "large":
            return 14
        return 11

    for pidx, page in enumerate(document.get("pages", []), start=1):
        if pidx > 1:
            doc.add_page_break()
        for block in page.get("blocks", []):
            t = block.get("type", "paragraph")
            style = block.get("style", {}) if isinstance(block.get("style"), dict) else {}
            if t == "heading":
                level = max(1, min(3, int(block.get("level", 2))))
                p = doc.add_heading(level=level)
            else:
                p = doc.add_paragraph()

            spans = block.get("inline_spans", []) if isinstance(block.get("inline_spans"), list) else []
            if not spans:
                spans = [{"text": block.get("content", "")}]

            for sp in spans:
                r = p.add_run(str(sp.get("text", "")))
                r.bold = bool(sp.get("bold", False))
                r.italic = bool(sp.get("italic", False))
                r.underline = bool(sp.get("underline", False))
                r.font.name = "Times New Roman"
                r.font.size = Pt(size_pt(style.get("font_size_relative", "normal")))

            if t == "list":
                items = block.get("items", []) if isinstance(block.get("items"), list) else []
                for item in items:
                    lp = doc.add_paragraph(style="List Number" if block.get("list_type") == "ordered" else "List Bullet")
                    lp.add_run(str(item.get("content", "")))
            elif t == "table":
                rows = block.get("rows", []) if isinstance(block.get("rows"), list) else []
                headers = block.get("headers", []) if isinstance(block.get("headers"), list) else []
                cols = max(len(headers), len(rows[0]) if rows and isinstance(rows[0], list) else 1)
                table = doc.add_table(rows=1 if headers else 0, cols=cols)
                if headers:
                    for i, h in enumerate(headers):
                        table.rows[0].cells[i].text = str(h)
                for row in rows:
                    if isinstance(row, list):
                        cells = table.add_row().cells
                        for i, c in enumerate(row[:cols]):
                            cells[i].text = str(c)

    doc.save(out_path)
    return out_path


def export_searchable_pdf(input_path: Path, out_path: Path) -> Path:
    import shutil
    import subprocess

    if shutil.which("ocrmypdf") is None:
        raise RuntimeError("ocrmypdf non disponibile")
    subprocess.check_call(["ocrmypdf", str(input_path), str(out_path), "--skip-text"])
    return out_path
