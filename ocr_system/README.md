# OCR System Windows (Guida completa per neofiti)

> Questo progetto converte PDF/JPG/PNG in output strutturati usando Gemini.
> È pensato per funzionare anche da menu contestuale (tasto destro) su Windows.

---

## 1) A cosa serve, in parole semplici

Il sistema prende un documento (PDF immagine, PDF misto, scansione, JPG/PNG) e genera:

1. **JSON strutturato** (`.ocr.json`) → base tecnica centrale del progetto.
2. **Markdown** (`.md`) → facile da leggere e ottimo per LLM.
3. **HTML** (`.html`) → versione leggibile web.
4. **DOCX** (`.docx`) → editabile in Word.
5. **PDF ricercabile** (`.searchable.pdf`) → **obbligatorio**, sempre generato.

Tutti i file finiscono nella cartella `OCR` accanto al file originale.

---

## 2) Cosa è cambiato nella rifattorizzazione

Prima c'era un file unico molto carico.
Ora l'architettura è separata e più chiara:

- `convert.py` → orchestratore (coordina il flusso)
- `ocr_core.py` → dialogo con Gemini e OCR strutturato
- `prompts.py` → prompt OCR in JSON
- `document_model.py` → schema/fallback/normalizzazione JSON
- `exporters.py` → conversione JSON -> md/docx/html/pdf

Pipeline logica:

```text
input -> OCR Gemini -> JSON intermedio -> exporter separati
```

---

## 3) Installazione rapida (utente Windows)

### Metodo consigliato

Apri `cmd.exe` nella cartella `ocr_system` e lancia:

```bat
setup_portable_windows.cmd
```

Il setup ora prova automaticamente a installare anche dipendenze di sistema OCR (Tesseract, Ghostscript, QPDF) via `winget` o `choco` quando mancanti.
Se non vuoi questo comportamento: `python install_windows.py --no-auto-system`.

### Installazione completa/forzata (quando serve)

```bat
setup_full_update.cmd
```

Usala se:
- hai errori di dipendenze,
- vuoi aggiornare tutto,
- vuoi reimpostare API key.

### Se hai spostato la cartella

```bat
refresh_context_menu.cmd
```

---

## 4) Dove mettere la API key

Nel file:

```text
ocr_system/.env
```

Esempio:

```env
GOOGLE_API_KEY=la_tua_chiave
GEMINI_MODEL=gemini-3.1-flash-lite
```

---

## 5) Uso da tasto destro

1. Tasto destro su PDF/JPG/PNG
2. **Converti in MD + HTML (OCR)**
3. Vai nella cartella `OCR` creata accanto al file sorgente

---

## 6) Uso da terminale

```bat
python convert.py "C:\path\documento.pdf"
```

Formati opzionali:

```bat
python convert.py "file.pdf" --formats json,md
python convert.py "file.pdf" --formats json,md,html,docx
```

> Nota: il **PDF ricercabile viene comunque generato sempre** (obbligatorio progetto).

---

## 7) PDF ricercabile: requisito obbligatorio

Il progetto ora tratta il PDF ricercabile come output obbligatorio.

Se non viene generato:
- la conversione viene considerata fallita,
- nel log trovi il motivo.

Dipendenze necessarie:
- `ocrmypdf` (installato via requirements)
- dipendenze di sistema richieste da `ocrmypdf` (in alcuni PC possono richiedere installazioni aggiuntive).

---

## 8) File di log (fondamentali)

Dentro `OCR/` trovi:

- `ocr_run.log` → log launcher/menu contestuale
- `ocr_debug.log` → log tecnico dettagliato Python

Se qualcosa va storto, condividi questi log.

---

## 9) Struttura output JSON (intermedio)

Il file `*.ocr.json` contiene:

- `document_info`
- `metadata`
- `pages[]`
  - `header`, `footer`, `layout_quality`, `page_notes`
  - `blocks[]` con:
    - `type`
    - `content`
    - `style`
    - `inline_spans`
    - `reading_order`
    - `source_page`

Questo JSON è la base comune per tutti gli exporter.

---

## 10) Documentazione extra (per non perdere il filo)

Vedi cartella `docs/`:

- `PROJECT_DETAILS.md` → descrizione tecnica completa del progetto
- `CHANGELOG_OPERATIVO.md` → cronologia modifiche e problemi affrontati
- `ROADMAP.md` → cosa è già fatto e cosa manca

---

## 11) Limiti noti (trasparenza totale)

- Qualità OCR dipende molto dalla qualità scansione.
- Alcune formattazioni complesse (documenti molto degradati) possono non essere perfette.
- `ocrmypdf` su Windows può richiedere componenti di sistema aggiuntive in certi ambienti.

---

## 12) Regola pratica di debug

Se un run fallisce:
1. apri `OCR/ocr_run.log`
2. apri `OCR/ocr_debug.log`
3. esegui `setup_full_update.cmd`
4. riprova su un PDF corto (1-2 pagine)


---


## 13) Garanzia maggiore contro testo mancante

Per ridurre i casi di testo incompleto:
- OCR JSON su PDF viene eseguito pagina per pagina (evita risposte troncate multipagina).
- Se il PDF contiene testo selezionabile, il sistema integra automaticamente blocchi mancanti nel JSON.

Questa doppia strategia serve proprio per evitare perdita di intere porzioni di testo.


---

## 14) Perché prima mancavano pezzi di testo

Cause identificate:
- alcuni blocchi `list` arrivavano con testo nel campo `content` ma senza array `items`;
- alcuni `inline_spans` includevano testo troncato con `...`, mentre `content` era completo.

Fix applicati:
- exporter ora ricostruiscono le liste anche quando `items` è assente;
- exporter e normalizzazione preferiscono `content` completo quando gli spans sono troncati o troppo corti.


---

## 15) Corsivo/grassetto/allineamento: limite reale vs obiettivo

Risposta trasparente:
- Su PDF con **testo selezionabile**, possiamo arrivare molto vicini all'originale perché leggiamo anche informazioni tipografiche locali (font/flags/allineamento stimato).
- Su PDF **solo raster/scansione**, il riconoscimento di corsivo, grassetto e centratura dipende dal modello vision e non è sempre perfetto.

In questa versione il sistema usa percorso ibrido per PDF:
1. pagina con testo selezionabile -> estrazione locale strutturale (più fedele su stili/allineamento)
2. pagina raster -> OCR Gemini vision

Quindi: "quasi perfetto" è realistico sui digitali/misti, meno garantibile sui raster puri degradati.

---

## 16) Requisito Tesseract per PDF ricercabile

Il PDF ricercabile usa `ocrmypdf`, che richiede `tesseract` installato nel PATH.
Se manca, la conversione viene fermata con messaggio chiaro.

Installazione rapida (Windows):
- `winget install UB-Mannheim.TesseractOCR`
- oppure `choco install tesseract`
