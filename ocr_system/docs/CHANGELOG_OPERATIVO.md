# CHANGELOG OPERATIVO

## Stato corrente
- Rifattorizzazione modulare completata.
- JSON intermedio introdotto e centralizzato.
- DOCX generato da JSON (non da HTML).
- PDF ricercabile reso obbligatorio nel flusso.

## Problemi incontrati (storico sintetico)
1. Errore modello Gemini non trovato (404)
   - Soluzione: risoluzione model-id contro lista modelli disponibile.
2. HTML troncato o pesante
   - Soluzione: sanitizzazione e architettura exporter separati.
3. Errori temporanei Gemini (503)
   - Soluzione: retry/backoff nel core API.
4. Setup PowerShell bloccato
   - Soluzione: setup via CMD.

## Cosa monitorare ogni run
- tempi run
- qualità JSON blocchi/inline_spans
- presenza PDF ricercabile
- warning OCR
