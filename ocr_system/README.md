# OCR System (rifattorizzato con JSON intermedio)

## Cosa resta invariato lato utente

- uso da menu contestuale Windows (`run_ocr.cmd`): invariato
- API key in `.env`: invariato
- output in cartella `OCR` vicino al file sorgente: invariato
- input supportati: PDF/JPG/JPEG/PNG

## Nuova architettura (pragmatica)

- `convert.py`: orchestratore + funzione `genera_output(...)`
- `ocr_core.py`: OCR Gemini -> JSON strutturato
- `prompts.py`: prompt OCR strutturato
- `document_model.py`: normalizzazione/validazione/fallback JSON
- `exporters.py`: exporter separati (`json`, `md`, `docx`, `html`, `pdf` opzionale)

Pipeline:

```text
input -> ocr_core (Gemini) -> JSON intermedio -> exporters
```

## JSON intermedio

File sempre generato: `nomefile.ocr.json`

Contiene:
- `document_info`
- `metadata`
- `pages[]`
  - `header/footer/page_notes/layout_quality`
  - `blocks[]` ordinati con `type`, `content`, `style`, `inline_spans`, `reading_order`, `source_page`

Se Gemini restituisce JSON invalido, viene attivato fallback robusto (documento minimale + warning).

## Output e default

### Funzione Python

```python
from convert import genera_output

out = genera_output("file.pdf")
```

Default funzione: `json`, `md`.

### CLI / launcher

Per mantenere compatibilità pratica con il flusso attuale, la CLI usa default:
`json,md,html,docx`

```bash
python convert.py "file.pdf" --formats json,md
python convert.py "file.pdf" --formats json,md,docx,html
python convert.py "file.pdf" --formats json,md,pdf
```

## DOCX

Il DOCX ora nasce dal JSON con `python-docx` (non più da HTML).
Gestisce heading, paragrafi, liste, tabelle, firme, page break e inline spans (bold/italic/underline).

## PDF ricercabile (opzionale)

Formato `pdf` usa `ocrmypdf` se disponibile nel sistema.
Se non disponibile, viene registrato errore exporter senza bloccare gli altri output.
