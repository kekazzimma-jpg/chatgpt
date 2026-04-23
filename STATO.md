# STATO.md

Memoria viva del progetto. Aggiornare a fine sessione. Da leggere sempre prima di qualunque modifica.

---

## Scopo reale del progetto

Sistema OCR per Windows che prende in input un file PDF/JPG/PNG e produce:

1. Un JSON strutturato (`*.ocr.json`) trattato come fonte di verità del documento (blocchi, stile, inline_spans, reading_order, metadata).
2. Esportazioni derivate dal JSON: Markdown, HTML, DOCX.
3. Un PDF ricercabile (`*.searchable.pdf`) generato con `ocrmypdf` + `tesseract`, considerato output obbligatorio.

Tutti gli output finiscono in una cartella `OCR/` accanto al file originale (a meno che non venga passato `--output-dir`).

Il motore OCR è Gemini (Google AI Studio, endpoint `generativelanguage.googleapis.com/v1beta/models`), richiamato con prompt JSON strutturato. Per PDF con testo selezionabile c'è un percorso alternativo che estrae direttamente da PyMuPDF senza passare da Gemini.

L'integrazione utente principale è il menu contestuale di Windows ("tasto destro sul file → voce OCR").

---

## Struttura reale del progetto

Radice repo: cartella `ocr_system/` con i seguenti file principali:

- `convert.py` — orchestratore CLI. Setup logger, chiamata `ocr_to_document`, esportazioni, PDF ricercabile obbligatorio.
- `ocr_core.py` — chiamate Gemini (`call_gemini_json` con retry/backoff), risoluzione API key e model id, percorso ibrido PDF (testo selezionabile via `fitz.get_text("dict")` vs vision Gemini pagina-per-pagina), fallback testo grezzo.
- `prompts.py` — prompt OCR strutturato in JSON.
- `document_model.py` — `default_style`, `ALLOWED_BLOCK_TYPES`, `normalize_document`, `_normalize_block`, `fallback_document`.
- `exporters.py` — `export_json`, `export_markdown`, `export_html` (da JSON), `export_html_faithful` (raster, non usato di default), `export_docx`, `export_searchable_pdf` (chiama `python -m ocrmypdf`).
- `install_windows.py` — crea `.venv`, installa `requirements.txt`, tenta winget/choco per tesseract/ghostscript/qpdf, scrive `.env`, registra menu contestuale via `winreg` su `HKEY_CURRENT_USER\Software\Classes\SystemFileAssociations\{.pdf,.jpg,.jpeg,.png}\shell\OCR_to_MD_HTML`.
- `install_windows_context_menu.reg` — file .reg alternativo/legacy con path hardcoded `C:\OCR\convert.py`. Convive con il metodo `winreg` di `install_windows.py`.
- `setup_portable_windows.cmd` — avvia `install_windows.py` (setup rapido).
- `setup_portable_windows.ps1` — variante PowerShell che fa setup + registrazione menu.
- `setup_full_update.cmd` — `install_windows.py --full --force-api`.
- `refresh_context_menu.cmd` — `install_windows.py --register-only`.
- `run_ocr.cmd` — launcher invocato dal menu contestuale; usa `.venv\Scripts\python.exe` se presente, altrimenti `python` di sistema; scrive `ocr_run.log` nella cartella `OCR/` accanto al file.
- `requirements.txt` — PyMuPDF 1.26.0, requests 2.32.3, python-docx 1.1.2, ocrmypdf 16.10.0.
- `.env.example` — `GOOGLE_API_KEY`, `GEMINI_MODEL` (default `gemini-3.1-flash-lite`).
- `README.md` — guida utente.
- `docs/PROJECT_DETAILS.md`, `docs/CHANGELOG_OPERATIVO.md`, `docs/ROADMAP.md` — documentazione storica.

Log runtime (generati durante l'uso, non nel repo):
- `OCR/ocr_run.log` — log launcher (da `run_ocr.cmd`).
- `OCR/ocr_debug.log` — log Python dettagliato (da `convert.py::setup_logger`).

---

## Come si prova su Windows

1. Aprire `cmd.exe` dentro la cartella `ocr_system/`.
2. Lanciare `setup_portable_windows.cmd`. Serve Python 3 con launcher `py -3`. Verranno:
   - creato il venv locale `.venv/`,
   - installate le dipendenze Python da `requirements.txt`,
   - tentata installazione di tesseract (obbligatorio) e ghostscript/qpdf (opzionali) via winget/choco,
   - chiesta la `GOOGLE_API_KEY` e scritta in `ocr_system/.env`,
   - registrate le voci del menu contestuale per `.pdf/.jpg/.jpeg/.png`.
3. Tasto destro su un PDF/JPG/PNG → voce "Converti in MD + HTML (OCR)". L'output va in `OCR/` accanto al file.
4. In alternativa da CLI: `python convert.py "C:\path\file.pdf"`. Il PDF ricercabile viene sempre generato.
5. In caso di errori, controllare `OCR/ocr_run.log` e `OCR/ocr_debug.log`. Per reset completo: `setup_full_update.cmd`.

---

## Cosa funziona già

- Pipeline end-to-end input → Gemini → JSON normalizzato → exporter separati.
- JSON intermedio `*.ocr.json` come fonte unica di verità.
- Retry/backoff sulle chiamate Gemini (su status 429/500/502/503/504).
- Percorso ibrido PDF: pagine con testo selezionabile estratte localmente (PyMuPDF `dict`), pagine raster via Gemini vision; OCR pagina-per-pagina per evitare troncamenti multipagina.
- Fallback `fallback_document` quando il JSON Gemini non è valido / nessuna pagina / errore OCR.
- Exporter Markdown, HTML (da JSON, con stile inline e allineamento), DOCX (con run bold/italic/underline, allineamento, Times New Roman), PDF ricercabile (ocrmypdf `--skip-text --output-type pdf`, con ricerca tesseract anche fuori PATH).
- Rimozione preventiva del file di output PDF per evitare exit code 15 di ocrmypdf.
- Installer Windows con venv, tentativo winget/choco, fallback ID alternativi, distinzione dipendenze obbligatorie vs opzionali.
- Registrazione menu contestuale via `winreg` in HKCU (no admin richiesto).
- Schema normalizzazione blocchi con tipi ammessi e degradazione a `paragraph` per tipi sconosciuti.

---

## Problemi aperti

1. **Incoerenza output reali vs testi del menu / setup / README.** La voce del menu è "Converti in MD + HTML (OCR)" ma il flusso di default produce JSON + MD + HTML + DOCX + PDF ricercabile. Alcuni testi in README e docs parlano di "MD + HTML" o di Ghostscript come consigliato pur essendo opzionale. Da allineare.
2. **Retry Gemini troppo permissivo su errori non transitori.** In `ocr_core.py::call_gemini_json` la condizione `transient` include `isinstance(exc, requests.RequestException)`, che è vera anche per `HTTPError` su 4xx (400, 401, 403, 404). Di conseguenza il sistema fa retry anche su errori non recuperabili (API key errata, modello inesistente, payload invalido), sprecando tempo e quota. Da restringere ai soli status transienti + errori di trasporto (ConnectionError/Timeout).
3. **Possibile perdita o appiattimento di `inline_spans`.** In `document_model.py::_normalize_block` e in `exporters.py::_block_text_md`, se gli spans sembrano troncati (`...`/`…`) o se la loro lunghezza è < 60% del `content`, gli spans vengono rimpiazzati da un singolo span piatto ricostruito dal `content`. Questo risolve il caso "testo mancante" ma elimina il bold/italic interno quando la stima di completezza scatta per altri motivi (es. testo con molti spazi o simboli). Da rivedere la soglia e/o preservare almeno gli attributi di stile.
4. **Resa non affidabile di grassetti/corsivi interni e centrature.** Oltre al punto 3, su pagine raster la detection dipende dal modello Gemini; su pagine selezionabili viene da flag PyMuPDF (bold = flag & 16, italic = flag & 2) che non coprono tutti i casi (es. font "pseudo-bold" senza flag). Allineamento stimato via bbox con soglia 10% sulla larghezza pagina (`_detect_alignment`): robusto ma grossolano.
5. **Possibile paragrafo superfluo nel DOCX per `list`/`table`.** In `exporters.py::export_docx`, il ciclo per ogni blocco crea *sempre* prima un `doc.add_paragraph()` (o heading) e ci mette dentro gli spans. Solo *dopo*, se il tipo è `list` o `table`, aggiunge items/tabella. Per blocchi `list`/`table`, il paragrafo iniziale contiene il `content` grezzo del blocco, duplicando o anticipando la lista/tabella. Da verificare se va emesso solo il contenuto strutturato.
6. **Log non allineati con `output_dir` personalizzato.** In `convert.py::setup_logger` il file `ocr_debug.log` viene sempre scritto in `input_path.parent / "OCR"`, ignorando il parametro `--output-dir`. Se l'utente manda gli output altrove, i log restano accanto al file sorgente.
7. **Setup Windows e file `.reg` da chiarire / semplificare.** Convivono tre meccanismi di registrazione menu: `install_windows.py` via `winreg` (HKCU, metodo reale in uso), `setup_portable_windows.ps1` che fa la stessa cosa in PowerShell, e `install_windows_context_menu.reg` con path hardcoded `C:\OCR\convert.py` (legacy, da verificare se ancora utile). Inoltre la catena `.cmd` → `install_windows.py` → winget/choco è ridondante e fragile se `py -3` non è presente. Da consolidare un flusso unico.

---

## Decisioni già prese

- JSON `*.ocr.json` è la **fonte unica di verità**. MD/HTML/DOCX si derivano *sempre* dal JSON, mai dal testo grezzo.
- Il **PDF ricercabile è output obbligatorio**: se fallisce, l'intera conversione è considerata fallita (`convert.py` rilancia `RuntimeError`).
- Il **menu contestuale Windows si registra in HKCU**, senza privilegi admin, via `winreg` dentro `install_windows.py`.
- `ocrmypdf` viene invocato con `--skip-text --output-type pdf` (non PDF/A, per ridurre dipendenza da Ghostscript).
- **Tesseract è obbligatorio**, Ghostscript/QPDF sono opzionali.
- **OCR PDF pagina-per-pagina**: scelta esplicita per evitare risposte Gemini troncate su documenti multipagina.
- `.env` locale in `ocr_system/.env`, non in home utente.
- Modello Gemini di default: `gemini-3.1-flash-lite`. Il model id viene risolto contro la lista modelli dell'account (fallback su corrispondenza token).
- Retry Gemini: max 5 tentativi, backoff `min(20, 2^(n-1))` secondi.
- Percorso selectable-text attivato se `page.get_text("text").strip()` > 180 caratteri.

---

## Ultima analisi tecnica

Sessione del 2026-04-23 (setup memoria condivisa).

Analisi statica dei file sorgenti. Rilevati i 7 problemi aperti elencati sopra leggendo:

- `ocr_core.py:119-143` — retry permissivo.
- `document_model.py:94-102` e `exporters.py:24-36` — appiattimento spans.
- `exporters.py:196-263` — paragrafo precedente a list/table in `export_docx`.
- `convert.py:14-28` vs `convert.py:42-50` — log vs output_dir.
- `install_windows.py:143-164` vs `install_windows_context_menu.reg` — doppio meccanismo registrazione.
- `ocr_core.py:155-231` — euristiche stile/allineamento su testo selezionabile.
- Coerenza etichette: README sezioni 1-5 vs default `--formats json,md,html,docx` in `convert.py:103`.

Nessuna modifica al codice è stata fatta in questa sessione: obiettivo esclusivo era fissare la memoria condivisa.

---

## Prossimo passo consigliato

Allineare la condizione di retry di Gemini in `ocr_core.py::call_gemini_json` in modo che gli errori 4xx non transitori (400, 401, 403, 404) non vengano ritentati. È il fix a rischio più basso, più isolato, e rimuove un comportamento che può anche mascherare errori di configurazione (API key / model id). Dopo questo, valutare se affrontare il punto 3 (appiattimento spans) perché impatta direttamente la fedeltà visiva degli export.

---

## Diario sintetico delle sessioni

- **2026-04-23** — Creata la memoria condivisa del progetto: `AGENTS.md`, `CLAUDE.md`, `STATO.md` nella root. Nessuna modifica al codice OCR. Lettura completa del repo (`ocr_system/`) e mappatura di problemi aperti, decisioni prese, prossimo passo consigliato.
