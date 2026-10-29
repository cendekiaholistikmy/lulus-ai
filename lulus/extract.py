"""Read figures from a text-based financial-statement PDF.

Every value keeps its source location (page and line) so the user can
trace it back. Labels that only match loosely are flagged for the user
to confirm instead of being silently accepted.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

AMOUNT_RE = re.compile(r"^(?P<label>.*?\S)\s+(?P<amount>\(?-?(?:RM\s?)?[\d,]*\d\)?|-)$")
TEXT_RE = re.compile(r"^(?P<label>[^:]{2,60}):\s*(?P<value>.+)$")
FUZZY_THRESHOLD = 0.86


@dataclass
class Value:
    concept: str
    label: str
    value: object
    page: int
    line: int
    raw: str
    confidence: float = 1.0

    @property
    def needs_confirmation(self) -> bool:
        return self.confidence < 1.0


@dataclass
class Extraction:
    source: str
    values: dict[str, Value] = field(default_factory=dict)
    sections: dict[str, tuple[int, int]] = field(default_factory=dict)
    unmatched: list[tuple[int, int, str]] = field(default_factory=list)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower().rstrip(":"))


def load_mapping(path: Path | None = None) -> dict:
    with open(path or DATA_DIR / "mapping.json", encoding="utf-8") as fh:
        return json.load(fh)


def parse_amount(token: str) -> int | None:
    """'1,234' -> 1234, '(1,234)' -> -1234, '-' -> 0."""
    token = token.strip()
    if token == "-":
        return 0
    negative = token.startswith("(") and token.endswith(")")
    digits = re.sub(r"[^\d-]", "", token)
    if not digits or digits == "-":
        return None
    value = int(digits)
    return -abs(value) if negative else value


def _lookup(label: str, table: dict[str, list[str]]) -> tuple[str | None, float]:
    """Return (concept, confidence). Exact label match = 1.0, close match < 1.0."""
    key = _norm(label)
    exact = {_norm(s): c for c, syns in table.items() for s in syns}
    if key in exact:
        return exact[key], 1.0
    best = difflib.get_close_matches(key, list(exact), n=1, cutoff=FUZZY_THRESHOLD)
    if best:
        ratio = difflib.SequenceMatcher(None, key, best[0]).ratio()
        return exact[best[0]], round(ratio, 2)
    return None, 0.0


def extract_lines(lines: list[tuple[int, int, str]], source: str = "<lines>",
                  mapping: dict | None = None) -> Extraction:
    """Extract values from (page, line_no, text) tuples."""
    mapping = mapping or load_mapping()
    out = Extraction(source=source)
    section_index = {_norm(s): name for name, syns in mapping["sections"].items() for s in syns}

    for page, line_no, text in lines:
        text = text.strip()
        if not text:
            continue
        if _norm(text) in section_index:
            out.sections.setdefault(section_index[_norm(text)], (page, line_no))
            continue
        m = TEXT_RE.match(text)
        if m:
            concept, conf = _lookup(m.group("label"), mapping["text"])
            if concept:
                out.values.setdefault(concept, Value(concept, m.group("label"), m.group("value").strip(),
                                                     page, line_no, text, conf))
                continue
        m = AMOUNT_RE.match(text)
        if m:
            concept, conf = _lookup(m.group("label"), mapping["amount"])
            amount = parse_amount(m.group("amount"))
            if concept and amount is not None:
                if concept not in out.values:
                    out.values[concept] = Value(concept, m.group("label"), amount, page, line_no, text, conf)
                continue
        out.unmatched.append((page, line_no, text))
    return out


def extract_pdf(path: str | Path, mapping: dict | None = None) -> Extraction:
    """Extract values from a text-based PDF. Scanned PDFs need OCR (roadmap)."""
    lines: list[tuple[int, int, str]] = []
    with pdfplumber.open(str(path)) as pdf:
        for p_index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for l_index, line in enumerate(text.splitlines(), start=1):
                lines.append((p_index, l_index, line))
    return extract_lines(lines, source=str(path), mapping=mapping)
