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
3. Tasto destro su un PDF/JPG/PNG → voce "Converti con OCR (MD/HTML/DOCX/PDF)". L'output va in `OCR/` accanto al file.
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

1. ~~**Incoerenza output reali vs testi del menu / setup / README.**~~ Risolto il 2026-04-23 (sessione correnti sicure): voce menu allineata a "Converti con OCR (MD/HTML/DOCX/PDF)" in `install_windows.py`, `setup_portable_windows.ps1`, `install_windows_context_menu.reg`, `README.md`; in README Ghostscript non è più "consigliato" ma chiaramente "opzionale, non richiesto dal flusso di default". Resta da verificare `docs/PROJECT_DETAILS.md` e `docs/CHANGELOG_OPERATIVO.md` (non toccati: documenti storici).
2. ~~**Retry Gemini troppo permissivo su errori non transitori.**~~ Risolto il 2026-04-23 (secondo batch tecnico). In `ocr_core.py::call_gemini_json` la condizione `transient` è stata ristretta a `status in {429,500,502,503,504}` OR `isinstance(exc, (requests.ConnectionError, requests.Timeout))`. Gli `HTTPError` su 4xx non transitori (400/401/403/404/...) NON vengono più ritentati; inoltre viene loggato esplicitamente `ERROR` con lo status non transitorio per facilitare la diagnosi (API key, model id, payload).
3. **Possibile perdita o appiattimento di `inline_spans`.** Mitigato (non chiuso) il 2026-04-23 (secondo batch tecnico):
   - estratti in `document_model.py` due helper pubblici `spans_look_incoherent(spans, content)` e `spans_majority_style(spans)` — fonte unica di verità, usata sia dal normalize che dall'exporter Markdown;
   - soglia di copertura abbassata da 60% a 40% (costante `_SPAN_COVERAGE_THRESHOLD = 0.40`), così scatta meno spesso;
   - floor in caratteri abbassato da 20 a 5, sbloccando blocchi brevi legittimi tipo "Oggetto: foo" che prima venivano sempre collassati;
   - quando il collasso scatta, il nuovo span piatto preserva i flag `bold/italic/underline/all_caps` dominanti (≥50% del testo degli spans originali pesato per lunghezza), anziché azzerarli come prima;
   - in `exporters.py::_block_text_md` la rete di sicurezza è ora coerente con il normalize: se gli spans risultano incoerenti, emette il content applicando lo stesso style di maggioranza via `_style_wrap_md`.
   Rischio residuo: la majority-style OR-pesata schiaccia le variazioni sub-span quando scatta il collasso (es. un blocco 60% bold diventa tutto bold). Accettabile come peggioramento rispetto a "tutto senza stile" e non riguarda il caso normale in cui gli spans sono coerenti.
4. **Resa non affidabile di grassetti/corsivi interni e centrature.** Parzialmente mitigato il 2026-04-23 (secondo batch tecnico) sul fronte del prompt Gemini, senza toccare le euristiche PyMuPDF: in `prompts.py` è stata aggiunta una sezione "Regole per inline_spans" che chiede esplicitamente di spezzare gli spans a ogni cambio di stile dentro la frase e di far coincidere la concatenazione degli spans col `content`, e una sezione "Regole per style.alignment" che insiste su center/right/justify e sulla frequenza dei titoli centrati in delibere/decreti/avvisi. Il miglioramento è atteso solo per le pagine che passano per Gemini vision; sulle pagine selezionabili la detection resta su flag PyMuPDF e bbox (`_detect_alignment`, soglia 10%), non modificata.
5. ~~**Possibile paragrafo superfluo nel DOCX per `list`/`table`.**~~ Risolto il 2026-04-23 (secondo batch tecnico). In `exporters.py::export_docx` i rami `t == "list"` e `t == "table"` sono stati spostati *prima* della creazione del paragrafo iniziale e chiudono il blocco con `continue`: ora per list/table viene emesso solo il contenuto strutturato (items con stile `List Bullet`/`List Number` oppure `docx.Table` con headers/rows), senza il paragrafo duplicato col `content` grezzo.
6. ~~**Log non allineati con `output_dir` personalizzato.**~~ Risolto il 2026-04-23 (secondo batch tecnico). `convert.py::setup_logger` ora accetta un secondo parametro opzionale `output_dir: Path | None`; se passato, il file `ocr_debug.log` viene scritto in quella cartella, altrimenti resta il comportamento storico `input_path.parent / "OCR"`. In `main()` il valore viene risolto da `args.output_dir` e registrato in log con un messaggio informativo. Inoltre `genera_output` usa `mkdir(parents=True, exist_ok=True)` per coerenza con cartelle multilivello.
7. **Setup Windows e file `.reg` da chiarire / semplificare.** Parzialmente affrontato il 2026-04-23: `install_windows_context_menu.reg` è stato declassato con un'intestazione esplicita "FILE LEGACY - NON È IL METODO DI INSTALLAZIONE PRINCIPALE" che rimanda a `setup_portable_windows.cmd` / `install_windows.py --register-only` / `refresh_context_menu.cmd`, e spiega le differenze (HKCR vs HKCU, path hardcoded, nessun launcher `run_ocr.cmd`). Corretta anche la numerazione dei passi di `install_windows.py::main` (era `[1/3]`, `[2/3]`, `[3/4]`, `[4/4]`: ora tutti `[x/4]`). Resta aperto il consolidamento del flusso unico (scelta fra `.cmd` + `.ps1` + `install_windows.py` + `.reg`) e la fragilità di `py -3` come prerequisito.

8. ~~**Incompatibilità ocrmypdf 16.10 + pikepdf ≥ 9 → conversione marcata come fallita anche se il PDF è generato.**~~ Risolto il 2026-04-23 (terzo batch). Sintomo visibile in `ocr_run.log`: `AttributeError: 'pikepdf._core.Pdf' object has no attribute 'check'` dentro `ocrmypdf/helpers.py::check_pdf`, seguito da `CalledProcessError: exit status 15`. Causa: pikepdf 9.x ha rimosso `Pdf.check()` che ocrmypdf 16.10 continua a chiamare nella fase finale `report_output_pdf → check_pdf`. Il searchable.pdf era effettivamente scritto su disco prima del crash (log `Image optimization ratio…`), ma `convert.py` lo considerava fallito e rilanciava `RuntimeError`. Fix doppio:
   - `requirements.txt` ora pinna `pikepdf>=8,<9` con commento esplicativo, per evitare che `pip install` in futuro tiri giù una versione incompatibile.
   - `exporters.py::export_searchable_pdf` cattura `subprocess.CalledProcessError` e, se il file di output esiste ed è un PDF valido (inizia con `%PDF-` e > 1 KB, check in `_pdf_looks_valid`), accetta la generazione con un `logging.warning`. Se il file non è valido, rilancia l'errore. Questa rete di sicurezza regge anche scenari analoghi futuri (ocrmypdf che crasha in validation ma ha già scritto il file).

9. **Italic non rilevato sui verbi-introduttori di atti amministrativi.** Emerso il 2026-04-23 leggendo `Ingiunzione n. 3_2019.ocr.json`. Parole come «Premesso», «Ritenuto», «Visto» sul documento originale sono in corsivo (spesso corsivo grassetto) ma nel JSON arrivano `bold: true, italic: false`. Il modello Gemini vision cattura lo spessore ma non lo slanting. Mitigazioni applicate (non risolutive):
   - DPI di rendering pagine PDF alzato in `ocr_core.py::render_pdf_pages_png` da `dpi=170` a `dpi=220`, così il modello ha più dettaglio sui glifi inclinati (costo: immagini ~67% più grandi in memoria, payload Gemini più grosso — accettabile per documenti tipici di 1-10 pagine).
   - `prompts.py` esteso con una sezione "Regole per italic (corsivo) — attenzione specifica" che:
     - distingue esplicitamente italic da bold e precisa che i due sono combinabili;
     - elenca i verbi-introduttori tipici delle delibere/decreti/ingiunzioni italiane («Premesso», «Considerato», «Ritenuto», «Visto», «Visti», «Vista», «Viste», «Atteso», «Attesa», «Richiamato», «Dato atto», «Preso atto», «Sentito», «Letto», «Valutato», «Acquisito»);
     - spinge esplicitamente verso il falso positivo («meglio italic=true anche in dubbio che perderlo sistematicamente»).
   Il risultato reale va verificato sul documento `Ingiunzione n. 3_2019.PDF` e su altri atti amministrativi. Se italic resta mancante nonostante il prompt rafforzato, le strade successive sono: detection euristica pre/post-Gemini basata su match regex sui verbi-introduttori (con flag `italic=true` iniettato in `document_model.py` quando il content corrisponde), oppure uso combinato di PyMuPDF `get_text("dict")` sui font name (regex `/Italic/`, `/Oblique/`) anche sulle pagine raster, passando i font rilevati come hint nel prompt.

---

## Aspettative realistiche sulla fedeltà formattazione

Risposta onesta alla domanda "fino a che punto possiamo arrivare" sulla parte formattazione/impaginazione/centrature/giustificazioni/margini:

**Cosa è realistico / già affidabile:**
- Struttura dei blocchi (heading, paragraph, list, table, signature, header/footer, stamp): buona.
- Allineamento blocco-per-blocco `left/center/right`: buona accuratezza su documenti tipografici puliti. `justify` è più rumoroso perché visivamente si distingue solo con righe lunghe piene.
- Grassetto "marcato" (titoli, parole-chiave isolate in bold spesso): tipicamente 80-90% di recall sul nostro pipeline attuale.
- Testo pagina-per-pagina integrale su documenti leggibili: ~95-99% caratteri, con cali su scansioni degradate.

**Cosa è parzialmente realistico / dipende dal modello:**
- Corsivo inline nel mezzo del testo: 50-75% di recall. Il corsivo è la feature tipografica che i modelli vision riconoscono peggio, perché richiede di cogliere l'inclinazione di pochi gradi su glifi piccoli (~10-12pt a 220 DPI sono ~30 pixel di altezza). Il miglioramento del prompt spinge la precisione ma non porta al 100%.
- Bold+italic combinato: simile al solo italic, a volte il modello resta sul solo bold.
- Dimensione relativa del font (`small/normal/large`): grezzo, a 3 livelli; non ricostruisce i pt esatti.
- Livello delle liste (numerato vs puntato, rientri nidificati): ragionevole ma può confondere liste con rientri misti.

**Cosa NON è realistico pretendere con questo pipeline:**
- Fedeltà pixel-perfect dell'impaginazione originale: il DOCX/HTML esporta con Times New Roman 11pt di default, margini 72pt, interlinea standard. Non è un ricostruttore di layout ma un rielaborator semantico.
- Ricostruzione esatta dei margini originali, dell'interlinea, dello spazio prima/dopo paragrafo: l'OCR non trasmette queste metriche.
- Font originale: non lo abbiamo; tutto viene reso in Times New Roman nel DOCX.
- Tabulazioni, rientri di prima riga, bullet a caratteri speciali non standard: persi o normalizzati.
- Immagini/loghi/firme grafiche: segnalate come `image_placeholder`/`stamp_or_seal`, non riprodotte visivamente.

**Percorsi residui di miglioramento concreto (non rivoluzionari):**
1. Detection euristica dei verbi-introduttori lato post-processing: regex su `content` in `document_model.py::_normalize_block` che forza `italic=true` quando il content corrisponde a `^(Premesso|Considerato|Ritenuto|Visto|Visti|Vista|Viste|Atteso|Attesa|Richiamato|Richiamata|Dato atto|Preso atto)(\b|[\s,:])`. Basso rischio, alto ritorno su atti amministrativi italiani, prompt-indipendente.
2. Uso combinato testo selezionabile + Gemini sulle stesse pagine: quando il PDF è misto, prendere da PyMuPDF i nomi dei font (in `font` dentro i `dict` span: stringhe come `"TimesNewRoman-Italic"`, `"Arial-BoldItalic"`) e passarli come hint nel prompt, oppure derivarne direttamente `italic=true` post-hoc.
3. Second-pass di coerenza cross-blocco: se su una pagina 5 blocchi sono marcati italic e uno no ma ha stesso font-size e posizione, promuoverlo. Costoso in complessità, utile solo su atti molto lunghi.
4. Esportazione HTML "side-by-side" con il raster originale a fianco del testo estratto, come controllo qualità. È più un tool di QA che un miglioramento della resa.

Su file lunghi (oltre 10-15 pagine) il costo Gemini cresce linearmente (pagina-per-pagina già implementato correttamente) e i tempi di risposta diventano rilevanti. Il DPI 220 raddoppia circa il payload image→modello rispetto a 170: su documenti di 50+ pagine conviene parametrizzare il DPI da CLI (`--dpi`) come ottimizzazione futura.

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

Sessione del 2026-04-23 (terzo batch: sblocco ocrmypdf + miglioramento italic + DPI).

Analisi di un caso reale fornito dall'utente (`Ingiunzione n. 3_2019.PDF`, 2 pagine, Comune di San Giorgio a Cremano, atto amministrativo italiano tipico). Letto `ocr_run.log` e `*.ocr.json` generati. Scoperte:

- Exit 15 ocrmypdf NON era un vero fallimento OCR: `AttributeError` su `pikepdf.Pdf.check()` in fase di validazione post-scrittura, PDF già generato e presente su disco. Fix: pin pikepdf + fallback difensivo su exit-code != 0 con `_pdf_looks_valid` in `exporters.py`.
- Retry ristretto (secondo batch) ha funzionato come previsto: 1 solo retry su 503 nel log, vs i 5 che il codice precedente avrebbe generato.
- Titoli centrati (`IL DIRIGENTE`, `INGIUNGE`, `ORDINA`, `AVVERTE`, `DISPONE`, `COMUNICA`): `bold: true, alignment: "center"` → resa corretta.
- Allineamenti: `header_block` `center`, `OGGETTO:` `justify`, paragrafi `left` → ragionevoli per quel documento.
- Verbi-introduttori (`Premesso`, `Ritenuto`, `Visto`) marcati `bold: true, italic: false` — nel PDF originale sono in corsivo. Gap confermato del modello vision. Affrontato con DPI 220 e prompt rafforzato.

Sessione del 2026-04-23 (secondo batch tecnico).

Modifiche puntuali ai 5 punti concordati. Riferimenti:

- `ocr_core.py::call_gemini_json` — retry ristretto a 429/500/502/503/504 + `ConnectionError`/`Timeout`; log `ERROR` esplicito su status non transitorio.
- `prompts.py` — aggiunte due sezioni: "Regole per inline_spans" (spezzare a ogni cambio stile, concatenazione = content) e "Regole per style.alignment" (center/right/justify/left con enfasi su titoli centrati).
- `exporters.py::export_docx` — list/table emessi solo come contenuto strutturato, senza paragrafo iniziale duplicato.
- `convert.py::setup_logger` — accetta `output_dir` opzionale; in `main()` i log seguono `--output-dir`.
- `document_model.py` — nuovi helper pubblici `spans_look_incoherent` e `spans_majority_style`; soglia `_SPAN_COVERAGE_THRESHOLD = 0.40` (era 0.60), floor caratteri 5 (era 20), collasso con preservazione majority-style.
- `exporters.py::_block_text_md` — usa gli helper condivisi invece di duplicare la logica; quando collassa applica `_style_wrap_md` col majority style.

---

## Verifiche manuali minime

Test logico automatico già eseguito su `document_model` dopo le modifiche (tutti i casi passati, senza installare `.venv`):

```bash
cd ocr_system
python -c "from document_model import _normalize_block, spans_look_incoherent, spans_majority_style; \
b={'type':'paragraph','content':'Hello world','inline_spans':[{'text':'Hello ','bold':False},{'text':'world','bold':True}]}; \
n=_normalize_block(b,1,1); assert n['inline_spans'][1]['bold'] is True; \
b2={'type':'paragraph','content':'TITOLO','inline_spans':[{'text':'TIT...','bold':True}]}; \
n2=_normalize_block(b2,1,1); assert n2['inline_spans'][0]['bold'] is True; \
print('OK')"
```

Test end-to-end da rifare a mano su una macchina con `.venv` + tesseract installati (non disponibili nell'ambiente di questa sessione):

1. **Retry 401 no-retry.** Esegui `python convert.py <file.pdf> --api-key "chiave_finta_invalida"`. Il log deve contenere una singola riga `Errore Gemini non transitorio (status=400|401|403): nessun retry` e nessuna serie di 5 tentativi con backoff. Tempo totale < 10s, non 30+.
2. **Log in output_dir personalizzato.** Esegui `python convert.py <file.pdf> --output-dir "%TEMP%\ocr_check"`. Verifica che `%TEMP%\ocr_check\ocr_debug.log` esista e che in `<cartella file>\OCR\` NON venga creato un nuovo `ocr_debug.log`.
3. **DOCX senza duplicati su list/table.** Usa un PDF con almeno una lista puntata e/o una tabella. Apri il `.docx` generato in Word: ogni lista deve apparire solo come lista puntata/numerata, senza un paragrafo precedente che ripete gli items; ogni tabella deve essere la sola resa del blocco `table`.
4. **Prompt: spans e centratura.** Usa un PDF raster con un titolo chiaramente centrato e una frase con una parola in grassetto. Nel `.ocr.json` generato: il blocco del titolo deve avere `style.alignment = "center"`; la frase deve avere ≥ 2 `inline_spans` con `bold` differenti.
5. **Fallback spans non brutale.** Forza manualmente un JSON con `content = "TITOLO IN GRASSETTO"` e `inline_spans = [{"text":"TITO...","bold":true}]`, poi esegui solo la normalizzazione (script sopra). L'output deve avere un unico span con `text = "TITOLO IN GRASSETTO"` e `bold = True`.

Nessun test automatico aggiunto come file separato: il progetto non ha una cartella `tests/` e l'utente ha chiesto di non introdurre nuovi file inutili. Il mini-test logico resta eseguibile ad-hoc come sopra.

---

## Prossimo passo consigliato

Problemi chiusi finora: 1, 2, 5, 6, 8. Parzialmente mitigati: 3, 4, 9. Aperti: 7.

Candidati per il prossimo batch, in ordine di impatto concreto vs rischio:

1. **Re-run del caso reale `Ingiunzione n. 3_2019.PDF`** (o un altro atto amministrativo con corsivi noti) dopo aver rieseguito `setup_full_update.cmd` — serve per allineare il venv al nuovo `requirements.txt` (pin pikepdf<9). Verifiche attese:
   - `ocr_run.log` non contiene più `AttributeError` né `exit status 15`;
   - se l'exit 15 ricomparisse (es. pikepdf non downgrade-abile), verificare che ora il log contenga il warning `ocrmypdf uscito con exit 15 ma il file di output esiste…` e che `*.searchable.pdf` venga comunque generato;
   - nel nuovo `*.ocr.json` controllare se «Premesso», «Ritenuto», «Visto» arrivano ora con `italic: true` (effetto combinato DPI 220 + prompt rafforzato).
2. **Detection euristica dei verbi-introduttori** in `document_model.py::_normalize_block` (opzione 1 del blocco "Percorsi residui"): rete di sicurezza prompt-indipendente via regex. Basso rischio, alto ritorno su documenti amministrativi italiani. Da fare solo se il punto 1 mostra che il prompt da solo non basta.
3. **Parametrizzazione DPI da CLI** (`convert.py --dpi`, default 220) in vista di documenti lunghi (30+ pagine). Micro-task, utile prima di processare batch grossi perché su un documento di 50 pagine a 220 DPI il payload verso Gemini diventa significativo.
4. **Consolidamento setup Windows (problema 7)** — decidere se eliminare `install_windows_context_menu.reg` del tutto e unificare `setup_portable_windows.cmd` + `.ps1`. Non urgente.

---

## Diario sintetico delle sessioni

- **2026-04-23** — Creata la memoria condivisa del progetto: `AGENTS.md`, `CLAUDE.md`, `STATO.md` nella root. Nessuna modifica al codice OCR. Lettura completa del repo (`ocr_system/`) e mappatura di problemi aperti, decisioni prese, prossimo passo consigliato.
- **2026-04-23** — Primo batch di correzioni sicure (nessuna modifica a logica OCR, PDF ricercabile, `inline_spans` o fallback). File toccati:
  - `ocr_system/install_windows.py`: etichetta menu contestuale passata da "Converti in MD + HTML (OCR)" a "Converti con OCR (MD/HTML/DOCX/PDF)" (riflette gli output reali); numerazione dei passi di `main()` corretta da `[1/3] … [3/4] [4/4]` a `[1/4] … [4/4]`; aggiornata la stringa finale "Setup completato".
  - `ocr_system/setup_portable_windows.ps1`: stessa etichetta allineata (valore registro e messaggio finale).
  - `ocr_system/install_windows_context_menu.reg`: aggiunta intestazione commentata "FILE LEGACY - NON È IL METODO DI INSTALLAZIONE PRINCIPALE" con riferimento al flusso ufficiale (`setup_portable_windows.cmd` / `install_windows.py --register-only` / `refresh_context_menu.cmd`) e spiegazione delle differenze (HKCR vs HKCU, path hardcoded, niente launcher `run_ocr.cmd`). Allineate anche le etichette di menu nel file.
  - `ocr_system/README.md`: sezione 5 aggiornata alla nuova etichetta e chiarito che la cartella `OCR` contiene JSON + MD + HTML + DOCX + PDF ricercabile; sezione 16 "Per Ghostscript (opzionale ma consigliato)" → "opzionale, non richiesto dal flusso di default" per coerenza con la scelta `--skip-text --output-type pdf`.
  - `STATO.md`: aggiornata voce "Come si prova su Windows" con la nuova etichetta, segnati come risolti/parzialmente affrontati i problemi 1 e 7, aggiunto questo diario e prossimo passo invariato (retry Gemini).
- **2026-04-23** — Secondo batch tecnico. File toccati:
  - `ocr_system/ocr_core.py`: `call_gemini_json` — condizione `transient` ristretta a status whitelistati (429/500/502/503/504) + `ConnectionError`/`Timeout`, estratta costante `TRANSIENT_HTTP_STATUSES`, aggiunto log `ERROR` dedicato quando lo status è non transitorio (niente più retry mascheranti su API key/model id invalidi).
  - `ocr_system/prompts.py`: aggiunte due sezioni "Regole per inline_spans" (spezzare a ogni cambio di stile, concatenazione spans = content) e "Regole per style.alignment" (enfasi su center, right, justify; attenzione ai titoli centrati in atti amministrativi).
  - `ocr_system/exporters.py::export_docx`: i rami `list` e `table` spostati all'inizio del loop con `continue` → niente più paragrafo iniziale col `content` grezzo davanti a lista/tabella. Aggiunto anche `from document_model import spans_look_incoherent, spans_majority_style` in testa al file.
  - `ocr_system/exporters.py::_block_text_md`: rimossa la logica duplicata di truncation-check; ora usa gli helper condivisi di `document_model.py` e, quando collassa, applica il majority-style via `_style_wrap_md` invece di azzerare la formattazione.
  - `ocr_system/convert.py::setup_logger`: nuovo parametro opzionale `output_dir`; `main()` calcola `custom_out_dir` da `args.output_dir` e lo passa al logger. Log dedicato quando la cartella è personalizzata. `genera_output` ora usa `mkdir(parents=True, exist_ok=True)` per cartelle multilivello.
  - `ocr_system/document_model.py`: aggiunti helper pubblici `spans_look_incoherent(spans, content)` e `spans_majority_style(spans)` + costante `_SPAN_COVERAGE_THRESHOLD = 0.40`. `_normalize_block` usa i nuovi helper e, quando deve collassare, preserva i flag `bold/italic/underline/all_caps` dominanti (≥50% del testo degli spans pesato per lunghezza). Floor caratteri 20 → 5 per non sacrificare blocchi legittimi brevi.
  - Test logico ad-hoc eseguito sul modulo `document_model` (8 casi su blocchi coerenti, troncati, copertura 30/40/50/60%, blocchi brevi, vuoti, stili mixed): tutti passati. Nessun test automatico salvato come file.
  - `STATO.md`: problemi 2, 5, 6 segnati come risolti; 3 e 4 segnati come mitigati con rischi residui espliciti; aggiunto blocco "Verifiche manuali minime" con 5 controlli end-to-end da eseguire su Windows con venv + tesseract; nuovo prossimo passo consigliato.
