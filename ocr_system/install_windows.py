#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

MODEL_DEFAULT = "gemini-3.1-flash-lite"
EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png"]


def ensure_venv(base_dir: Path) -> Path:
    venv_dir = base_dir / ".venv"
    python_exe = venv_dir / "Scripts" / "python.exe"

    if not python_exe.exists():
        subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])

    subprocess.check_call([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([str(python_exe), "-m", "pip", "install", "-r", str(base_dir / "requirements.txt")])
    return python_exe


def save_env(base_dir: Path, model: str) -> None:
    env_path = base_dir / ".env"
    existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    if "GOOGLE_API_KEY=" in existing:
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


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    model = MODEL_DEFAULT
    if len(sys.argv) > 1 and sys.argv[1].strip():
        model = sys.argv[1].strip()

    print("[1/3] Setup venv + dipendenze...")
    ensure_venv(base_dir)

    print("[2/3] Configuro API key locale...")
    save_env(base_dir, model)

    print("[3/3] Registro menu contestuale...")
    register_context_menu(base_dir)

    print("Setup completato. Usa click destro: Converti in MD + HTML (OCR).")


if __name__ == "__main__":
    main()
