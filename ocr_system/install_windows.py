#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
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
        check = subprocess.run([str(python_exe), "-c", "import fitz,requests,docx,ocrmypdf"], capture_output=True, text=True)
        if check.returncode != 0:
            print("Dipendenze Python mancanti rilevate, installo requirements...")
            subprocess.check_call([str(python_exe), "-m", "pip", "install", "-r", str(base_dir / "requirements.txt")])
        else:
            print("Install dipendenze Python saltata (modalità rapida): requisiti già presenti.")

    return python_exe


def _try_install_with_winget(package_ids: list[str]) -> bool:
    if shutil.which("winget") is None:
        return False
    for package_id in package_ids:
        cmd = [
            "winget",
            "install",
            "--id",
            package_id,
            "-e",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ]
        if subprocess.run(cmd).returncode == 0:
            return True
    return False


def _try_install_with_choco(package_name: str) -> bool:
    if shutil.which("choco") is None:
        return False
    return subprocess.run(["choco", "install", package_name, "-y"]).returncode == 0


def _append_common_paths() -> None:
    candidates = [
        r"C:\Program Files\Tesseract-OCR",
        r"C:\Program Files\qpdf\bin",
    ]
    gs_root = Path(r"C:\Program Files\gs")
    if gs_root.exists():
        for p in gs_root.glob("*\\bin"):
            candidates.append(str(p))

    cur = os.environ.get("PATH", "")
    for c in candidates:
        if Path(c).exists() and c.lower() not in cur.lower():
            cur = c + os.pathsep + cur
    os.environ["PATH"] = cur


def ensure_system_dependencies(auto_install: bool = True) -> None:
    _append_common_paths()

    required = {
        "tesseract": {
            "winget": ["UB-Mannheim.TesseractOCR", "Tesseract-OCR.Tesseract"],
            "choco": "tesseract",
            "mandatory": True,
        },
        "gswin64c": {
            "winget": ["ArtifexSoftware.Ghostscript", "ArtifexSoftware.GhostScript"],
            "choco": "ghostscript",
            "mandatory": False,
        },
        "qpdf": {
            "winget": ["qpdf.qpdf"],
            "choco": "qpdf",
            "mandatory": False,
        },
    }

    missing = [exe for exe in required if shutil.which(exe) is None]
    if not missing:
        print("Dipendenze sistema OCR trovate (tesseract; ghostscript/qpdf opzionali).")
        return

    if auto_install:
        print(f"Dipendenze sistema mancanti: {', '.join(missing)}. Provo installazione automatica...")
        for exe in list(missing):
            spec = required[exe]
            ok = _try_install_with_winget(spec["winget"]) or _try_install_with_choco(spec["choco"])
            if ok:
                print(f"Installato: {exe}")
        _append_common_paths()

    missing_after = [exe for exe in required if shutil.which(exe) is None]
    mandatory_missing = [exe for exe in missing_after if required[exe].get("mandatory", True)]
    optional_missing = [exe for exe in missing_after if not required[exe].get("mandatory", True)]
    if optional_missing:
        print("Dipendenze opzionali mancanti (non bloccanti): " + ", ".join(optional_missing))
    if mandatory_missing:
        raise SystemExit(
            "Dipendenze sistema obbligatorie mancanti anche dopo tentativo automatico: "
            + ", ".join(mandatory_missing)
            + ". Installa manualmente e riavvia il terminale."
        )


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

    env_path.write_text(f"GOOGLE_API_KEY={api_key}\nGEMINI_MODEL={model}\n", encoding="utf-8")
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
    parser = argparse.ArgumentParser(description="Installer OCR Windows")
    parser.add_argument("--model", default=MODEL_DEFAULT)
    parser.add_argument("--full", action="store_true", help="Reinstalla/aggiorna dipendenze")
    parser.add_argument("--register-only", action="store_true", help="Aggiorna solo menu contestuale")
    parser.add_argument("--force-api", action="store_true", help="Richiedi nuovamente la API key")
    parser.add_argument("--no-auto-system", action="store_true", help="Non tentare installazione automatica dipendenze sistema")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent

    if args.register_only:
        register_context_menu(base_dir)
        print("Aggiornamento menu completato.")
        return

    print("[1/3] Setup venv + dipendenze Python...")
    ensure_venv(base_dir, full_install=args.full)

    print("[2/3] Verifica dipendenze sistema OCR (tesseract obbligatorio; ghostscript/qpdf opzionali)...")
    ensure_system_dependencies(auto_install=not args.no_auto_system)

    print("[3/4] Configuro API key locale...")
    save_env(base_dir, args.model, force_api_prompt=args.force_api)

    print("[4/4] Registro menu contestuale...")
    register_context_menu(base_dir)

    print("Setup completato. Usa click destro: Converti in MD + HTML (OCR).")


if __name__ == "__main__":
    main()
