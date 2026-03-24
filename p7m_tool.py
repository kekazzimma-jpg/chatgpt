#!/usr/bin/env python3
"""Portable P7M extractor + signature info viewer.

Features:
- Open one or more .p7m files from CLI, file dialog, or drag&drop (if tkinterdnd2 installed).
- Extract embedded PDF to output folder.
- Show signature/certificate information collected from OpenSSL.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


@dataclass
class ProcessResult:
    source: Path
    output_pdf: Path | None
    signer_summary: str
    details: str
    ok: bool


def find_openssl() -> str:
    env_path = os.environ.get("OPENSSL_BIN")
    if env_path and shutil.which(env_path):
        return env_path
    for candidate in ("openssl", "openssl.exe"):
        path = shutil.which(candidate)
        if path:
            return path
    raise FileNotFoundError(
        "OpenSSL non trovato. Installa OpenSSL o imposta OPENSSL_BIN con il percorso dell'eseguibile."
    )


def run_cmd(cmd: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True)


def extract_pdf(openssl_bin: str, p7m_path: Path, output_dir: Path) -> tuple[Path | None, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_pdf = output_dir / (p7m_path.stem + ".pdf")

    verify_cmd = [
        openssl_bin,
        "smime",
        "-verify",
        "-inform",
        "DER",
        "-in",
        str(p7m_path),
        "-noverify",
        "-out",
        str(output_pdf),
    ]
    res = run_cmd(verify_cmd)

    if res.returncode == 0 and output_pdf.exists() and output_pdf.stat().st_size > 0:
        return output_pdf, ""

    if output_pdf.exists() and output_pdf.stat().st_size == 0:
        output_pdf.unlink(missing_ok=True)

    error = (res.stderr or res.stdout or "Errore sconosciuto durante estrazione PDF").strip()
    return None, error


def parse_signers(cert_text: str) -> str:
    chunks = cert_text.split("subject=")
    entries = []
    for chunk in chunks[1:]:
        lines = chunk.splitlines()
        subject = lines[0].strip()
        issuer = ""
        for ln in lines:
            if ln.strip().startswith("issuer="):
                issuer = ln.split("issuer=", 1)[1].strip()
                break
        entries.append((subject, issuer))

    if not entries:
        return "Nessun dettaglio certificato disponibile"

    msg = []
    for i, (subj, iss) in enumerate(entries, start=1):
        msg.append(f"Firmatario {i}: {subj}")
        if iss:
            msg.append(f"  Emittente: {iss}")
    return "\n".join(msg)


def collect_signature_info(openssl_bin: str, p7m_path: Path) -> tuple[str, str]:
    cmd = [
        openssl_bin,
        "pkcs7",
        "-inform",
        "DER",
        "-in",
        str(p7m_path),
        "-print_certs",
        "-text",
    ]
    res = run_cmd(cmd)
    details = (res.stdout or "") + ("\n" + res.stderr if res.stderr else "")
    details = details.strip() or "Nessun dettaglio disponibile"
    summary = parse_signers(res.stdout or "") if res.returncode == 0 else "Impossibile leggere i certificati"
    return summary, details


def process_file(openssl_bin: str, p7m_file: Path, output_dir: Path) -> ProcessResult:
    out_pdf, err = extract_pdf(openssl_bin, p7m_file, output_dir)
    summary, details = collect_signature_info(openssl_bin, p7m_file)

    ok = out_pdf is not None
    if not ok:
        details = f"Errore estrazione PDF:\n{err}\n\n{details}"
    return ProcessResult(
        source=p7m_file,
        output_pdf=out_pdf,
        signer_summary=summary,
        details=details,
        ok=ok,
    )


def normalize_drop_paths(raw: str) -> List[Path]:
    # tkdnd passes paths as a TCL list, often wrapped in braces when spaces are present.
    raw = raw.strip()
    parts: List[str] = []
    current = ""
    in_brace = False
    for ch in raw:
        if ch == "{" and not in_brace:
            in_brace = True
            current = ""
            continue
        if ch == "}" and in_brace:
            in_brace = False
            parts.append(current)
            current = ""
            continue
        if ch == " " and not in_brace:
            if current:
                parts.append(current)
                current = ""
            continue
        current += ch
    if current:
        parts.append(current)

    return [Path(p) for p in parts]


class P7MApp:
    def __init__(self, root: tk.Tk, initial_files: Iterable[Path], output_dir: Path):
        self.root = root
        self.root.title("P7M -> PDF Extractor")
        self.output_dir = output_dir

        self.openssl_bin = ""
        try:
            self.openssl_bin = find_openssl()
        except FileNotFoundError as exc:
            messagebox.showerror("OpenSSL mancante", str(exc))

        self._build_ui()
        self._enable_dnd_if_available()

        initial = [p for p in initial_files if p.suffix.lower() == ".p7m"]
        if initial:
            self.process_files(initial)

    def _build_ui(self) -> None:
        frm = ttk.Frame(self.root, padding=10)
        frm.pack(fill="both", expand=True)

        top = ttk.Frame(frm)
        top.pack(fill="x")

        ttk.Button(top, text="Apri file .p7m", command=self.open_files).pack(side="left")
        ttk.Button(top, text="Scegli cartella output", command=self.select_output_dir).pack(side="left", padx=8)

        self.out_label = ttk.Label(top, text=f"Output: {self.output_dir}")
        self.out_label.pack(side="left", padx=8)

        self.drop_label = ttk.Label(
            frm,
            text="Trascina qui i file .p7m (drag & drop se supportato)",
            relief="groove",
            padding=8,
        )
        self.drop_label.pack(fill="x", pady=10)

        self.tree = ttk.Treeview(frm, columns=("status", "pdf"), show="headings", height=8)
        self.tree.heading("status", text="Stato")
        self.tree.heading("pdf", text="PDF estratto")
        self.tree.column("status", width=120, anchor="center")
        self.tree.column("pdf", width=580)
        self.tree.pack(fill="both", expand=True)

        ttk.Label(frm, text="Dettagli firma:").pack(anchor="w", pady=(10, 2))
        self.details = tk.Text(frm, height=14, wrap="word")
        self.details.pack(fill="both", expand=True)

        self.tree.bind("<<TreeviewSelect>>", self.show_selected_details)
        self._results: list[ProcessResult] = []

    def _enable_dnd_if_available(self) -> None:
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD
        except Exception:
            self.drop_label.configure(
                text=(
                    "Drag & drop non attivo (installa tkinterdnd2). "
                    "Puoi usare comunque 'Apri file .p7m'."
                )
            )
            return

        if not isinstance(self.root, TkinterDnD.Tk):
            return

        self.drop_label.drop_target_register(DND_FILES)
        self.drop_label.dnd_bind("<<Drop>>", self.handle_drop)

    def select_output_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=str(self.output_dir))
        if selected:
            self.output_dir = Path(selected)
            self.out_label.configure(text=f"Output: {self.output_dir}")

    def open_files(self) -> None:
        files = filedialog.askopenfilenames(
            title="Seleziona file P7M",
            filetypes=[("File firmati", "*.p7m"), ("Tutti i file", "*.*")],
        )
        if files:
            self.process_files([Path(f) for f in files])

    def handle_drop(self, event) -> None:
        files = normalize_drop_paths(event.data)
        self.process_files([p for p in files if p.suffix.lower() == ".p7m"])

    def process_files(self, files: Iterable[Path]) -> None:
        if not self.openssl_bin:
            messagebox.showerror("Errore", "OpenSSL non disponibile")
            return

        for p in files:
            if not p.exists():
                continue
            result = process_file(self.openssl_bin, p, self.output_dir)
            self._results.append(result)
            status = "OK" if result.ok else "ERRORE"
            pdf_path = str(result.output_pdf) if result.output_pdf else "-"
            self.tree.insert("", "end", values=(status, pdf_path), text=str(p))

    def show_selected_details(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        if idx >= len(self._results):
            return
        r = self._results[idx]
        self.details.delete("1.0", "end")
        payload = textwrap.dedent(
            f"""
            File: {r.source}
            Esito: {'OK' if r.ok else 'ERRORE'}
            PDF: {r.output_pdf if r.output_pdf else '-'}

            Riepilogo firmatari:
            {r.signer_summary}

            Dettagli completi:
            {r.details}
            """
        ).strip()
        self.details.insert("1.0", payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Estrae PDF da file P7M e mostra info firma")
    parser.add_argument("files", nargs="*", help="File .p7m da aprire")
    parser.add_argument("-o", "--output", default="output_pdf", help="Cartella output PDF")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    initial_files = [Path(x) for x in args.files]
    output_dir = Path(args.output)

    # If tkinterdnd2 is installed, create Tk via TkinterDnD for native DnD support.
    root_cls = tk.Tk
    try:
        from tkinterdnd2 import TkinterDnD

        root_cls = TkinterDnD.Tk
    except Exception:
        pass

    root = root_cls()
    app = P7MApp(root, initial_files, output_dir)
    root.geometry("980x700")
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
