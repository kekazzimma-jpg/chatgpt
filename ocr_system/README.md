# Sistema OCR portatile → Markdown + HTML

Obiettivo: usare **quasi solo il menu contestuale Windows** (click destro), con setup semplice anche su PC diversi.

## Cosa fa

Converte automaticamente:
- PDF con testo selezionabile,
- PDF scansiti (raster o scritto a mano),
- PDF misti,
- immagini JPG/JPEG/PNG,

in **2 output** nella cartella `OCR` (accanto al file sorgente):
1. `nomefile.md` (ottimizzato per LLM)
2. `nomefile.html` (resa visuale più fedele possibile)

## Strategia adattiva

Lo script sceglie in automatico la procedura migliore:
- `pdf_digital`: usa testo selezionabile + preview pagina.
- `pdf_scanned`: OCR vision pagina per pagina.
- `pdf_mixed`: OCR vision multi-pagina (evita perdita blocchi raster).
- `image`: OCR vision diretto.

## Installazione rapida (portabile)

1. Copia la cartella `ocr_system` dove vuoi (es: chiavetta, cloud sync, ecc.).
2. Apri PowerShell in quella cartella.
3. Esegui:

```powershell
.\setup_portable_windows.ps1
```

Lo script farà tutto:
- crea `.venv` locale,
- installa dipendenze,
- ti chiede la chiave Google AI Studio,
- salva la chiave in `ocr_system/.env`,
- registra il menu contestuale per `.pdf/.jpg/.jpeg/.png` (utente corrente, senza admin).

## Dove inserire e salvare la API key Google

La chiave viene salvata in:

`ocr_system/.env`

Esempio:

```env
GOOGLE_API_KEY=la_tua_chiave
GEMINI_MODEL=gemini-3.1-flash-lite
```

Ordine di priorità usato dal programma:
1. `--api-key` da riga comando
2. variabile ambiente `GOOGLE_API_KEY`
3. file locale `ocr_system/.env`

## Uso quotidiano (principale)

- Tasto destro sul file → **Converti in MD + HTML (OCR)**.
- Il sistema crea automaticamente la cartella `OCR` vicino al file sorgente.

## Uso da terminale (opzionale)

```bash
python convert.py "C:\\path\\documento.pdf"
```

## File principali

- `convert.py`: motore OCR/adattivo
- `run_ocr.cmd`: launcher chiamato dal menu contestuale
- `setup_portable_windows.ps1`: setup automatico portabile
- `.env.example`: template configurazione API
- `requirements.txt`: dipendenze Python

## Note

- Se sposti la cartella su un altro PC, riesegui `setup_portable_windows.ps1`.
- Il modello di default è `gemini-3.1-flash-lite`.
- Per documenti molto lunghi può servire chunking (estensione futura).
