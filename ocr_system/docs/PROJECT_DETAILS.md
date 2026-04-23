# PROJECT DETAILS

## Obiettivo
Rendere il sistema OCR riusabile e stabile, con JSON intermedio come fonte unica di verità.

## Componenti
- convert.py: orchestrazione e gestione output/errori
- ocr_core.py: OCR Gemini + parsing JSON robusto + fallback
- document_model.py: normalizzazione schema e degradazione blocchi sconosciuti
- exporters.py: exporter separati
- prompts.py: prompt OCR strutturato

## Flusso tecnico
1. Lettura input
2. OCR con Gemini verso JSON strutturato
3. Normalizzazione documento
4. Esportazione per formato
5. Report errori senza perdere output disponibili

## Invarianti UX mantenute
- menu contestuale
- .env
- output in cartella OCR
- supporto Windows
