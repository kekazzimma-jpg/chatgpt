# Sistema OCR portatile → Markdown + HTML

Obiettivo: uso principale tramite **menu contestuale Windows** (click destro), con setup rapido su PC diversi.

## Cosa fa

Converte automaticamente PDF (digitali/scansiti/misti) e immagini (JPG/JPEG/PNG) in:
1. `nomefile.md` (LLM-friendly)
2. `nomefile.html` (resa visuale più fedele possibile)

Gli output vengono salvati nella cartella `OCR` accanto al file sorgente.

## Fix importante sul tuo errore 404

Dal log che hai incollato, il problema era il modello `gemini-3.1-flash-lite` (endpoint non trovato).  
Ora il sistema usa di default `gemini-2.5-flash-lite` e, se il modello richiesto non esiste per la tua key, prova fallback automatici compatibili.

## Installazione consigliata (NO PowerShell policy issues)

Apri `cmd.exe` nella cartella `ocr_system` e lancia:

```bat
setup_portable_windows.cmd
```

Questo evita il problema tipico di PowerShell:
> "script non firmato digitalmente / ExecutionPolicy"

Il setup `.cmd` avvia un installer Python che:
- crea `.venv` locale,
- (solo al primo setup) installa dipendenze,
- chiede la tua `GOOGLE_API_KEY`,
- salva la key in `ocr_system/.env`,
- registra il menu contestuale per `.pdf/.jpg/.jpeg/.png` (utente corrente, no admin).

## Sviluppo/debug snello (senza reinstallare tutto)

Non serve rifare setup completo ad ogni modifica.

### Caso 1: modifichi solo `convert.py` / `run_ocr.cmd`
- Salva i file.
- Riprova subito dal menu contestuale.
- **Nessun setup da rifare.**

### Caso 2: hai spostato la cartella `ocr_system`
- Esegui solo:
```bat
refresh_context_menu.cmd
```
(per aggiornare i path del tasto destro)

### Caso 3: vuoi reinstallare dipendenze o cambiare API key
- Esegui:
```bat
setup_full_update.cmd
```

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
GEMINI_MODEL=gemini-2.5-flash-lite
```

Priorità lettura configurazione:
1. `--api-key`
2. variabile ambiente `GOOGLE_API_KEY`
3. file locale `ocr_system/.env`

## Uso quotidiano

- Tasto destro su file → **Converti in MD + HTML (OCR)**.
- Output automatici in cartella `OCR`.

## Debug e log (se non succede nulla)

Se la finestra si chiude troppo in fretta o la conversione fallisce:
- il launcher crea `OCR/ocr_run.log` vicino al file input;
- il motore salva `OCR/ocr_debug.log` con dettagli interni/traceback.

In caso di errore, la finestra resta aperta e mostra il percorso del log.

## File principali

- `convert.py`: motore OCR/adattivo
- `install_windows.py`: setup portabile senza PowerShell
- `setup_portable_windows.cmd`: setup rapido (consigliato)
- `refresh_context_menu.cmd`: aggiorna solo il menu contestuale
- `setup_full_update.cmd`: reinstall completa dipendenze/config
- `run_ocr.cmd`: launcher usato dal menu contestuale
- `setup_portable_windows.ps1`: alternativa PowerShell
- `.env.example`: template API
- `requirements.txt`: dipendenze Python
