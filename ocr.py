"""PDF -> text. Uses the embedded text layer when a page has one, EasyOCR otherwise.
OCR boxes are regrouped into visual lines (same-row boxes joined by two spaces).

CLI: python ocr.py file.pdf  ->  {"pages": [...], "device": "..."} on stdout
"""
import json
import os
import sys

import fitz  # pymupdf
import numpy as np

LANGS = os.environ.get("OCR_LANGS", "en,ms").split(",")
# OCR_GPU=0 forces CPU, OCR_GPU=1 requests CUDA (CPU fallback if absent), default auto.
GPU_MODE = os.environ.get("OCR_GPU", "auto").lower()
DPI = int(os.environ.get("OCR_DPI", "200"))
MIN_TEXT_CHARS = int(os.environ.get("OCR_MIN_TEXT", "80"))  # fewer chars on a page => treat as scanned
_reader = None


def reader():
    global _reader
    if _reader is None:
        import easyocr
        import torch
        cuda = torch.cuda.is_available()
        use_gpu = GPU_MODE == "1" or (GPU_MODE == "auto" and cuda)
        _reader = easyocr.Reader(LANGS, gpu=use_gpu and cuda)
    return _reader


def device_label():
    try:
        import torch
        if torch.cuda.is_available():
            return f"GPU · {torch.cuda.get_device_name(0)}"
    except Exception:
        pass
    return "CPU"


def _lines(results):
    items = []
    for box, text, conf in results:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        items.append(((min(ys) + max(ys)) / 2, max(ys) - min(ys), min(xs), text))
    items.sort()
    rows, cur, cy, ch = [], [], None, 0
    for y, h, x, t in items:
        if cur and abs(y - cy) <= 0.6 * max(h, ch):
            cur.append((x, t))
            cy = (cy + y) / 2
        else:
            if cur:
                rows.append(cur)
            cur, cy, ch = [(x, t)], y, h
    if cur:
        rows.append(cur)
    return [{"text": "  ".join(t for _, t in sorted(r)),
             "bbox": [min(x for x, _ in r), min(y for x, _ in r),
                      max(x for x, _ in r), max(y for x, _ in r)]} for r in rows]


def pdf_pages(path):
    pages = []
    with fitz.open(path) as doc:
        for p in doc:
            embedded = p.get_text("text", sort=True).strip()
            if len(embedded) >= MIN_TEXT_CHARS:
                blocks = []
                for block in p.get_text("blocks", sort=True):
                    x0, y0, x1, y1, text, *_ = block
                    if text.strip(): blocks.append({"text": text.strip(), "bbox": [x0, y0, x1, y1]})
                pages.append({"text": embedded, "blocks": blocks, "width": p.rect.width, "height": p.rect.height})
                continue
            pix = p.get_pixmap(dpi=DPI, colorspace=fitz.csRGB)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
            blocks = _lines(reader().readtext(img))
            pages.append({"text": "\n".join(b["text"] for b in blocks), "blocks": blocks,
                          "width": pix.width, "height": pix.height})
    return pages


def pdf_to_text(path):
    return "\n\n".join(p["text"] for p in pdf_pages(path))


if __name__ == "__main__":
    real_stdout, sys.stdout = sys.stdout, sys.stderr  # keep library progress output off the JSON channel
    pages = pdf_pages(sys.argv[1])
    real_stdout.write(json.dumps({"pages": pages, "device": device_label()}, ensure_ascii=False))
