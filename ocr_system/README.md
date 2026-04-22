# Sistema OCR adattivo → Markdown + HTML

Questo progetto converte automaticamente:
- PDF con testo selezionabile,
- PDF scansiti (testo raster o scritto a mano),
- PDF misti,
- immagini JPG/JPEG/PNG,

in **2 output** dentro una cartella `OCR` (creata accanto al file originale):
1. `nomefile.md` (ottimizzato per LLM)
2. `nomefile.html` (resa visuale il più fedele possibile)

## Strategia automatica

Lo script rileva il tipo di input:
- `pdf_digital`: usa testo selezionabile + preview pagina per migliorare struttura.
- `pdf_scanned`: usa OCR vision pagina per pagina.
- `pdf_mixed`: tratta il documento come vision multi-pagina per evitare perdita di blocchi raster.
- `image`: OCR vision diretto su immagine.

## Requisiti

- Python 3.10+
- API key Google AI Studio (`GOOGLE_API_KEY`)
- Modello impostato di default: `gemini-3.1-flash-lite` (override con `--model` o `GEMINI_MODEL`)

Installa dipendenze:

```bash
pip install -r requirements.txt
```

## Uso da terminale

```bash
python convert.py "C:\\path\\documento.pdf"
```

Opzioni:

```bash
python convert.py "file.pdf" --api-key "..." --model "gemini-3.1-flash-lite"
```

## Integrazione menu contestuale Windows

1. Copia questa cartella in `C:\OCR\` (oppure modifica il path nel `.reg`).
2. Installa dipendenze Python nell'ambiente usato dal comando `python`.
3. Fai doppio click su `install_windows_context_menu.reg` e conferma.
4. Da Esplora File: tasto destro su PDF/JPG/PNG → **Converti in MD + HTML (OCR)**.

## Note pratiche

- Per PDF molto lunghi, il costo token può salire: conviene usare batch pagine o chunking.
- Per documenti sensibili, valuta policy privacy prima di inviare file a API esterne.
- L'HTML è “fedele” ma non garantisce pixel-perfect su tutti i layout complessi.
