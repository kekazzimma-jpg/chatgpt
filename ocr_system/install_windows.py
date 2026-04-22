#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import shutil
from pathlib import Path

MODEL_DEFAULT = "gemini-3.1-flash-lite"
EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png"]


def ensure_venv(base_dir: Path, full_install: bool) -> Path:
    venv_dir = base_dir / ".venv"
    python_exe = venv_dir / "Scripts" / "python.exe"

    if not python_exe.exists():
        subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
        full_install = True

    if full_install:
        subprocess.check_call([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call([str(python_exe), "-m", "pip", "install", "-r", str(base_dir / "requirements.txt")])
    else:
        # modalità rapida ma con verifica minima dipendenze obbligatorie
        check = subprocess.run([str(python_exe), "-c", "import fitz,requests,docx,ocrmypdf"], capture_output=True, text=True)
        if check.returncode != 0:
            print("Dipendenze mancanti rilevate, installo requirements...")
            subprocess.check_call([str(python_exe), "-m", "pip", "install", "-r", str(base_dir / "requirements.txt")])
        else:
            print("Install dipendenze saltata (modalità rapida): requisiti già presenti.")

    return python_exe


def save_env(base_dir: Path, model: str, force_api_prompt: bool) -> None:
    env_path = base_dir / ".env"
    existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    has_key = "GOOGLE_API_KEY=" in existing

    if has_key and not force_api_prompt:
        print("GOOGLE_API_KEY già presente in .env (nessuna modifica).")
        return

    api_key = input("Inserisci GOOGLE_API_KEY (Google AI Studio): ").strip()
    if not api_key:
        raise SystemExit("API key vuota: setup interrotto.")

    env_path.write_text(
        f"GOOGLE_API_KEY={api_key}\nGEMINI_MODEL={model}\n",
        encoding="utf-8",
    )
    print(f"Salvato: {env_path}")


def register_context_menu(base_dir: Path) -> None:
    if os.name != "nt":
        print("Registro menu contestuale: saltato (non Windows).")
        return

    import winreg

    run_cmd = str((base_dir / "run_ocr.cmd").resolve())
    command = f'cmd /c "\"{run_cmd}\" \"%1\""'

    for ext in EXTENSIONS:
        shell_key = rf"Software\Classes\SystemFileAssociations\{ext}\shell\OCR_to_MD_HTML"
        cmd_key = shell_key + r"\command"

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, shell_key) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "Converti in MD + HTML (OCR)")
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, "imageres.dll,-5302")

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, cmd_key) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, command)

    print("Menu contestuale registrato per .pdf/.jpg/.jpeg/.png (utente corrente).")


def ensure_tesseract() -> None:
    if shutil.which("tesseract"):
        print("Tesseract trovato nel PATH.")
        return
    raise SystemExit(
        "Tesseract non trovato nel PATH. Installa Tesseract OCR (es. `winget install UB-Mannheim.TesseractOCR` "
        "oppure `choco install tesseract`) e poi riavvia il terminale."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Installer OCR Windows")
    parser.add_argument("--model", default=MODEL_DEFAULT)
    parser.add_argument("--full", action="store_true", help="Reinstalla/aggiorna dipendenze")
    parser.add_argument("--register-only", action="store_true", help="Aggiorna solo menu contestuale")
    parser.add_argument("--force-api", action="store_true", help="Richiedi nuovamente la API key")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent

    if args.register_only:
        register_context_menu(base_dir)
        print("Aggiornamento menu completato.")
        return

    print("[1/3] Setup venv + dipendenze...")
    ensure_venv(base_dir, full_install=args.full)

    ensure_tesseract()

    print("[2/3] Configuro API key locale...")
    save_env(base_dir, args.model, force_api_prompt=args.force_api)

    print("[3/3] Registro menu contestuale...")
    register_context_menu(base_dir)

    print("Setup completato. Usa click destro: Converti in MD + HTML (OCR).")


if __name__ == "__main__":
    main()
