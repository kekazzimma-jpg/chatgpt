# P7M Portable Extractor

Piccolo tool (Python) per:
- aprire uno o più file `.p7m` (da riga comando, dialog file, o drag&drop se disponibile),
- estrarre il PDF originale,
- mostrare le informazioni del certificato/firma digitale.

## Requisiti
- Python 3.10+
- OpenSSL installato e presente nel `PATH` (oppure variabile `OPENSSL_BIN`)
- Opzionale: `tkinterdnd2` per drag&drop nativo nell'interfaccia

## Avvio rapido
```bash
python p7m_tool.py
```

Oppure apri direttamente file da riga comando:
```bash
python p7m_tool.py documento1.pdf.p7m documento2.p7m -o estratti
```

I PDF vengono creati nella cartella `output_pdf` (o in quella scelta da GUI/parametro `-o`).

## Creare EXE portable (Windows)
### Metodo rapido (consigliato)
Da Windows, nella root del progetto:

```bat
build_exe.bat
```

Output atteso:
- `dist\p7m-portable.exe`

### Metodo manuale
```bash
pip install -r requirements.txt pyinstaller
pyinstaller --onefile --windowed --name p7m-portable p7m_tool.py
```

### Build automatica via GitHub Actions
È disponibile la workflow `.github/workflows/build-windows-exe.yml` (trigger manuale `workflow_dispatch`) che produce l'artefatto:
- `p7m-portable-windows` contenente `p7m-portable.exe`

> Nota: l'EXE Windows va generato in ambiente Windows (locale o CI Windows).

## Menu contestuale (Windows)
Nel file `windows/register_context_menu.reg` trovi un esempio per aggiungere la voce:
- **Apri con P7M Portable Extractor**

che passa il file selezionato all'app.

## Limitazioni
- L'estrazione usa `openssl smime -verify -noverify`: estrae il contenuto firmato ma non valida la catena trust online.
- Le informazioni mostrate sono quelle disponibili via `openssl pkcs7 -print_certs -text`.
