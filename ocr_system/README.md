# Sistema OCR portatile → Markdown + HTML

Obiettivo: uso principale tramite **menu contestuale Windows** (click destro), con setup rapido su PC diversi.

## Cosa fa

Converte automaticamente PDF (digitali/scansiti/misti) e immagini (JPG/JPEG/PNG) in:
1. `nomefile.md` (LLM-friendly)
2. `nomefile.html` (resa visuale più fedele possibile)

Gli output vengono salvati nella cartella `OCR` accanto al file sorgente.

## Installazione consigliata (NO PowerShell policy issues)

Apri `cmd.exe` nella cartella `ocr_system` e lancia:

```bat
setup_portable_windows.cmd
```

Questo evita il problema tipico di PowerShell:
> "script non firmato digitalmente / ExecutionPolicy"

Il setup `.cmd` avvia un installer Python che:
- crea `.venv` locale,
- installa dipendenze,
- chiede la tua `GOOGLE_API_KEY`,
- salva la key in `ocr_system/.env`,
- registra il menu contestuale per `.pdf/.jpg/.jpeg/.png` (utente corrente, no admin).

## Se vuoi comunque usare PowerShell

Puoi avviare temporaneamente lo script ignorando la policy solo per la sessione corrente:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_portable_windows.ps1
```

## Dove salvare la API key Google

La key viene salvata in:

`ocr_system/.env`

Esempio:

```env
GOOGLE_API_KEY=la_tua_chiave
GEMINI_MODEL=gemini-3.1-flash-lite
```

Priorità lettura configurazione:
1. `--api-key`
2. variabile ambiente `GOOGLE_API_KEY`
3. file locale `ocr_system/.env`

## Uso quotidiano

- Tasto destro su file → **Converti in MD + HTML (OCR)**.
- Output automatici in cartella `OCR`.

## File principali

- `convert.py`: motore OCR/adattivo
- `install_windows.py`: setup portabile senza PowerShell
- `setup_portable_windows.cmd`: avvio setup consigliato
- `run_ocr.cmd`: launcher usato dal menu contestuale
- `setup_portable_windows.ps1`: alternativa PowerShell
- `.env.example`: template API
- `requirements.txt`: dipendenze Python

## Debug e log (se non succede nulla)

Se la finestra si chiude troppo in fretta o la conversione fallisce:
- il launcher ora crea sempre `OCR/ocr_run.log` vicino al file input;
- il motore salva anche `OCR/ocr_debug.log` con dettagli interni/traceback.

In caso di errore, la finestra **resta aperta** e mostra il percorso del log.
