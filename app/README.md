# lulus.ai — MBRS Filer

PDF → text layer / EasyOCR → stage 1 regex → stage 2 gemma3:4b (grounded) → human review → Arelle-validated MBRS XBRL.
All field specs (labels, types, enums, patterns, period types, schemaRef) are read from `taxonomy.zip` via Arelle (parsed once, cached in `.cache/`).

```bash
ollama pull gemma3:4b
npm install
npm run dev               # http://localhost:5173
```

Requires `uv` and Node 20+. Production: `npm run build && npm start`.

Env: `MBRS_ZIP`, `MBRS_OFFLINE=1`, `MBRS_ENTITY_SCHEME`, `OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_EMBED_MODEL`, `OCR_LANGS` (default `en,ms`), `OCR_GPU=0|1`, `OCR_DPI`, `OCR_MIN_TEXT`.

Layout: `src/routes/+page.svelte` UI · `api/ocr` PDF → text (`ocr.py`) · `api/mbrs` entries/form/extract/validate (`bridge.py` → `extract.py`, `engine.py`) · `api/chat` assistant.
