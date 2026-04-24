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

## Ultimo test end-to-end reale

Eseguito il 2026-04-24 su `C:\Users\Utente\OneDrive\ANTIABUSIVISMO\SOPRALLUOGHI\2026\COCOZZA\Ricorso.PDF` (20 pagine, atto amministrativo italiano). Log osservato: `OCR\ocr_run.log` (contiene due run: 23/04 su PC vecchio utente `crist`, 24/04 su PC attuale utente `Utente`).

**Run 23/04 (PC vecchio, pikepdf 9.x ancora installato):**
- Conversione completata con successo.
- Compare l'`AttributeError: 'pikepdf._core.Pdf' object has no attribute 'check'` previsto, ma la rete di sicurezza di `exporters.py::export_searchable_pdf` lo intercetta: warning `ocrmypdf uscito con exit 15 ma il file di output esiste ed è un PDF valido`, poi tutti gli `[OK]` finali incluso `Ricorso.searchable.pdf`.
- **Conferma sul campo che il fix del problema 8 funziona anche quando pikepdf resta a 9.x.**

**Run 24/04 (PC attuale, `C:\Users\Utente\Desktop\OCR`):**
- Falliscono le pagine 1 e 8 con `Errore Gemini transitorio (status=503)` → singolo retry ciascuna (retry ristretto del secondo batch → OK). Pagina 8 cade poi in `Fallback OCR JSON: Gemini JSON fallito: 'parts'` → fallback_document usato per quella pagina.
- Ma il fallimento bloccante è altro: `The program 'gs' could not be executed or was not found on your system PATH` / `Could not find program 'gswin64c' on the PATH` → ocrmypdf esce con **exit 3**, `*.searchable.pdf` NON viene creato, `convert.py` rilancia `RuntimeError: PDF ricercabile obbligatorio non generato`.
- Causa: **Ghostscript non è installato su questa macchina**. Il Run 23/04 funzionava solo perché sul PC vecchio Ghostscript c'era (confermato dalla riga `Image optimization ratio: 1.18 savings: 15.5%`, generata da `gs`).

**Conclusione operativa:**

Ghostscript è dichiarato "opzionale" in README e STATO perché usiamo `--skip-text --output-type pdf` (no PDF/A). **Nella realtà, su PDF multipagina con immagini, ocrmypdf 16.10 invoca `gs` nel post-processing (ottimizzazione/riscrittura) e senza di esso esce con status 3.** Su questo errore la rete di sicurezza non può intervenire: il file non viene scritto prima del crash.

Azione richiesta sul PC prima di ri-testare: installare Ghostscript (`winget install --id GnuPG.Ghostscript -e` oppure `choco install ghostscript -y`), riaprire `cmd.exe`, verificare con `gswin64c --version`, poi rilanciare il test sullo stesso PDF.

**Osservazione sul fronte italic:**

L'utente ha ispezionato il `*.ocr.json` del Run 23/04: il prompt rafforzato (terzo batch) ha prodotto **falsi positivi** sui verbi-introduttori (alcuni marcati italic quando non lo erano) e ha continuato a **perdere italic reali** in altre porzioni di testo. Il solo prompt non è sufficiente come strategia. Questo rafforza l'esigenza del punto 2 del "Prossimo passo consigliato" (detection euristica post-Gemini in `_normalize_block`), ma probabilmente non basta da sola: andrà combinata con l'uso dei font name da PyMuPDF sulle pagine miste (opzione 2 del blocco "Percorsi residui").

**Richiesta utente collaterale:** più informazioni a schermo in `cmd.exe` durante l'elaborazione. Oggi gli `INFO` dettagliati vanno solo su `ocr_debug.log`; su console arriva poco. Micro-task futuro: in `convert.py::setup_logger` duplicare il livello INFO anche sullo `StreamHandler` già presente (oggi filtrato), così l'utente vede in tempo reale le righe "OCR pagina X/N → percorso Y" e i warning. Rischio basso, utile.

---

## Prossimo passo consigliato (aggiornato 2026-04-24)

1. **Installare Ghostscript sul PC attuale e ripetere il test su `Ricorso.PDF` 20 pagine.** È il blocco immediato. Se esce `[OK] Conversione completata` con il file `.searchable.pdf` presente, il multipagina è confermato funzionante sul nuovo ambiente.
2. **Aggiornare README.md e STATO.md per spostare Ghostscript da "opzionale" a "consigliato/di fatto necessario su PDF multipagina".** Piccolo fix di documentazione, da fare solo dopo conferma al punto 1.
3. **Valutare se `install_windows.py` debba marcare Ghostscript come obbligatorio** (oggi è tra gli "opzionali" con tentativo best-effort via winget/choco). Decisione: probabilmente sì, almeno avvisare forte se manca.
4. **Micro-task: aumentare la verbosità di `convert.py` in console** (INFO visibili su stdout durante il run).
5. **Rimane aperto il problema 9 italic.** Dopo l'analisi utente sul JSON: prompt alone non basta. Andare su detection euristica regex in `document_model.py::_normalize_block` + uso font name PyMuPDF (opzioni 1 e 2 di "Percorsi residui"). Da fare in un batch dedicato, non ora.

---

## Sessione 2026-04-24 (test reali + batch resilienza + fix tabelle)

Batch tecnico concentrato su tre problemi emersi dai test reali. Files toccati: `ocr_core.py`, `prompts.py`, `document_model.py`. Nessuna modifica a `convert.py`, `exporters.py`.

**Bug 1 — Una pagina Gemini fallita buttava via tutto il documento.** `_merge_pdf_pages` lasciava propagare l'eccezione fuori dal loop; `ocr_to_document` prendeva l'eccezione e invocava `fallback_document` per l'INTERO documento, buttando via tutto il lavoro già fatto sulle altre pagine. Sintomo: JSON/MD/HTML/DOCX con solo il fallback piatto, searchable.pdf OK (non dipende da questo path). Fix: try/except per-pagina interno al loop, la singola pagina fallita diventa una pagina di fallback, le altre proseguono normalmente.

**Bug 2 — Errore `KeyError: 'parts'` oscuro.** `call_gemini_json` faceva `data["candidates"][0]["content"]["parts"][0]["text"]` e crashava con KeyError generico quando Gemini rispondeva 200 ma senza parts. Fix: try/except intorno a quell'accesso, logga `finishReason` e `promptFeedback.blockReason`. Risultato sul caso reale: abbiamo scoperto che il blocco era `finishReason=RECITATION` — il filtro Google anti-copia-verbatim di materiale di training (leggi italiane e sentenze TAR pubbliche). Non è disabilitabile via `safetySettings`.

**Opzione 3 — Fallback tesseract per pagine bloccate da Gemini.** Nuova funzione `_tesseract_ocr_png_bytes` in `ocr_core.py` che invoca `tesseract.exe` (localizzato riusando `_find_tesseract_exe` di `exporters.py`) sul PNG già renderizzato. Sceglie lingua automaticamente: `ita+eng` > `ita` > `eng`. Il tesseract utente è tornato utile anche per questo dopo l'aggiunta di `ita.traineddata`. Quando il fallback tesseract produce testo, il content del blocco viene prefissato con un marker visibile in TUTTI gli output MD/HTML/DOCX: `[Pagina recuperata con OCR locale tesseract — il testo potrebbe contenere errori di riconoscimento e perde la formattazione originale.]`. Nuova helper `_page_text_fallback_doc(text, input_path, page_num, reason, is_secondary_ocr=False)`. Test reale su `Ricorso.PDF`: pagine 8-9 bloccate per RECITATION recuperate con 1108 e 1620 caratteri tesseract rispettivamente, marker presente in MD/HTML (2/2).

**Bug 3 — Tabelle vuote nel DOCX.** Emerso su `Relazione Fasulo.pdf` (58 pagine raster, 25 tabelle nel JSON). Gemini metteva tutto il contenuto tabella dentro `content` come stringa con `|` separatore, senza popolare `headers`/`rows`. L'exporter DOCX in [exporters.py:230-243](ocr_system/exporters.py:230-243) legge solo `block["rows"]`/`block["headers"]`: col JSON vuoto creava tabelle 0×1 → tabelle invisibili nel documento Word. Fix doppio:
- `prompts.py`: nuova sezione "Regole per table" con schema esplicito (`headers`, `rows` come array di array di stringhe, celle normalizzate al numero massimo di colonne), indicazioni sulle tabelle chiave-valore a 2 colonne (caratteristiche dei moduli/schede amministrativi), esempio completo nello schema.
- `document_model.py::_normalize_block`: fallback parser deterministico. Quando `type == "table"` e `rows` è assente ma `content` contiene `|`, ricostruisce `rows` splittando per newline e `|`, normalizza tutte le righe al numero massimo di colonne. Non sovrascrive `rows`/`headers` se già forniti da Gemini (tested: due casi d'uso coperti).

Re-run su `Relazione Fasulo.pdf` con il nuovo prompt: tabelle passate da 25 a 39 (Gemini ne riconosce di più perché le istruzioni sono più forti), **39/39 con `rows` popolati** (100%), 12 con `headers` non vuoti (le altre sono chiave-valore 2 colonne come da istruzione). Il DOCX risultante contiene 39 `<w:tbl>`, 126 `<w:tr>`, 316 `<w:tc>`: tabelle visibili come griglia Word, non più vuote. Warning `diacritics` tesseract scesi da 5 a 2 grazie a `ita.traineddata` installato dall'utente.

**Verificato in questa sessione:**
- Resilienza per-pagina su `Ricorso.PDF`: 20/20 pagine, 2 in fallback tesseract con marker, nessun collasso del documento intero.
- Tabelle strutturate su `Relazione Fasulo.pdf`: 39 tabelle, DOCX con griglia vera.
- Encoding UTF-8 corretto nel JSON (verificato bytewise: 96 `à` minuscole, 2 `À` maiuscole, 0 U+FFFD).
- Image handling corretto su PDF con foto: Gemini marca come `image_placeholder` con descrizioni utili (`[DISEGNO TECNICO]`, `[PLANIMETRIA_DIAGRAM]`, `[Firma]`, `[Marche da bollo]`) invece di tentare OCR del contenuto fotografico. Comportamento richiesto dall'utente.

**Problema collaterale documentato ma non risolto:** README/STATO dicono Ghostscript "opzionale", ma ocrmypdf 16.10 lo invoca di fatto per il post-processing di PDF multipagina (exit 3 se manca). Stesso per `ita.traineddata`: non installato di default, ha effetto sul fallback tesseract E sul searchable.pdf di tutto il documento. Vedi prossimo passo.

---

## Prossimo passo consigliato (aggiornato 2026-04-24 dopo fix tabelle)

1. **Portabilità del progetto** — richiesta utente. Progetto ha molte dipendenze esterne (Python, Tesseract + `ita`, Ghostscript, più pacchetti Python). Opzioni:
   - A) Migliorare `install_windows.py` per scaricare anche Ghostscript e `ita.traineddata` quando winget/choco mancano. Richiede Python preesistente.
   - B) PyInstaller / Nuitka per produrre `.exe` standalone. Python non più richiesto, Tesseract/Ghostscript restano esterne.
   - C) **Portable vero**: cartella autocontenuta con Python embeddable + Tesseract portable (con `ita`) + Ghostscript portable + venv preinstallato + tutte le dipendenze pip pre-scaricate. Da portare su pennetta e avviare ovunque. Preferenza utente: opzione C. Costo: ~500MB-1GB di bundle, più complesso da costruire e mantenere, ma zero prerequisiti sulla macchina di destinazione.
   Da aprire in batch dedicato. Non iniziare finché non è confermato l'approccio.
2. **Aggiornare README.md** per riflettere la verità operativa: Ghostscript de facto obbligatorio su multipagina, `ita.traineddata` consigliato, `pytesseract`/`tesseract-ocr ita` diventano parte del setup standard.
3. **Continuare test reali** su PDF forniti dall'utente, con cartelle di output dedicate per ciascuno (`--output-dir` separato per file, pattern `PDFTEST\OCR\<stem>[_vN]\`).
4. **Problema italic rimane aperto** (problema 9): detection euristica regex in `_normalize_block` + font name PyMuPDF (opzioni 1 e 2 di "Percorsi residui"). Da fare in batch dedicato, più avanti, dopo la portabilità.

---

## Diario sintetico delle sessioni

- **2026-04-23** — Creata la memoria condivisa del progetto: `AGENTS.md`, `CLAUDE.md`, `STATO.md` nella root. Nessuna modifica al codice OCR. Lettura completa del repo (`ocr_system/`) e mappatura di problemi aperti, decisioni prese, prossimo passo consigliato.
- **2026-04-23** — Primo batch di correzioni sicure (nessuna modifica a logica OCR, PDF ricercabile, `inline_spans` o fallback). File toccati:
  - `ocr_system/install_windows.py`: etichetta menu contestuale passata da "Converti in MD + HTML (OCR)" a "Converti con OCR (MD/HTML/DOCX/PDF)" (riflette gli output reali); numerazione dei passi di `main()` corretta da `[1/3] … [3/4] [4/4]` a `[1/4] … [4/4]`; aggiornata la stringa finale "Setup completato".
  - `ocr_system/setup_portable_windows.ps1`: stessa etichetta allineata (valore registro e messaggio finale).
  - `ocr_system/install_windows_context_menu.reg`: aggiunta intestazione commentata "FILE LEGACY - NON È IL METODO DI INSTALLAZIONE PRINCIPALE" con riferimento al flusso ufficiale (`setup_portable_windows.cmd` / `install_windows.py --register-only` / `refresh_context_menu.cmd`) e spiegazione delle differenze (HKCR vs HKCU, path hardcoded, niente launcher `run_ocr.cmd`). Allineate anche le etichette di menu nel file.
  - `ocr_system/README.md`: sezione 5 aggiornata alla nuova etichetta e chiarito che la cartella `OCR` contiene JSON + MD + HTML + DOCX + PDF ricercabile; sezione 16 "Per Ghostscript (opzionale ma consigliato)" → "opzionale, non richiesto dal flusso di default" per coerenza con la scelta `--skip-text --output-type pdf`.
  - `STATO.md`: aggiornata voce "Come si prova su Windows" con la nuova etichetta, segnati come risolti/parzialmente affrontati i problemi 1 e 7, aggiunto questo diario e prossimo passo invariato (retry Gemini).
- **2026-04-24** — Test end-to-end reale su `Ricorso.PDF` (20 pagine). Nessuna modifica al codice. Esito: (a) fix problema 8 confermato sul Run 23/04 (PC vecchio con pikepdf 9.x); (b) Run 24/04 sul PC attuale fallisce con exit 3 di ocrmypdf per **Ghostscript mancante** — `gs`/`gswin64c` non in PATH; (c) utente conferma che il prompt rafforzato su italic genera falsi positivi e perde comunque corsivi reali: servirà detection euristica + font name PyMuPDF. Prossimo passo: installare Ghostscript e ripetere test. Aggiornato "Ultimo test end-to-end reale" e "Prossimo passo consigliato" in STATO.
- **2026-04-23** — Secondo batch tecnico. File toccati:
  - `ocr_system/ocr_core.py`: `call_gemini_json` — condizione `transient` ristretta a status whitelistati (429/500/502/503/504) + `ConnectionError`/`Timeout`, estratta costante `TRANSIENT_HTTP_STATUSES`, aggiunto log `ERROR` dedicato quando lo status è non transitorio (niente più retry mascheranti su API key/model id invalidi).
  - `ocr_system/prompts.py`: aggiunte due sezioni "Regole per inline_spans" (spezzare a ogni cambio di stile, concatenazione spans = content) e "Regole per style.alignment" (enfasi su center, right, justify; attenzione ai titoli centrati in atti amministrativi).
  - `ocr_system/exporters.py::export_docx`: i rami `list` e `table` spostati all'inizio del loop con `continue` → niente più paragrafo iniziale col `content` grezzo davanti a lista/tabella. Aggiunto anche `from document_model import spans_look_incoherent, spans_majority_style` in testa al file.
  - `ocr_system/exporters.py::_block_text_md`: rimossa la logica duplicata di truncation-check; ora usa gli helper condivisi di `document_model.py` e, quando collassa, applica il majority-style via `_style_wrap_md` invece di azzerare la formattazione.
  - `ocr_system/convert.py::setup_logger`: nuovo parametro opzionale `output_dir`; `main()` calcola `custom_out_dir` da `args.output_dir` e lo passa al logger. Log dedicato quando la cartella è personalizzata. `genera_output` ora usa `mkdir(parents=True, exist_ok=True)` per cartelle multilivello.
  - `ocr_system/document_model.py`: aggiunti helper pubblici `spans_look_incoherent(spans, content)` e `spans_majority_style(spans)` + costante `_SPAN_COVERAGE_THRESHOLD = 0.40`. `_normalize_block` usa i nuovi helper e, quando deve collassare, preserva i flag `bold/italic/underline/all_caps` dominanti (≥50% del testo degli spans pesato per lunghezza). Floor caratteri 20 → 5 per non sacrificare blocchi legittimi brevi.
  - Test logico ad-hoc eseguito sul modulo `document_model` (8 casi su blocchi coerenti, troncati, copertura 30/40/50/60%, blocchi brevi, vuoti, stili mixed): tutti passati. Nessun test automatico salvato come file.
  - `STATO.md`: problemi 2, 5, 6 segnati come risolti; 3 e 4 segnati come mitigati con rischi residui espliciti; aggiunto blocco "Verifiche manuali minime" con 5 controlli end-to-end da eseguire su Windows con venv + tesseract; nuovo prossimo passo consigliato.
