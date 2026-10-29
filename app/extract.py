"""Gemma-based extraction and source-document validation for MBRS fields."""
import json
import os
import re

import requests

from engine import check

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:4b")


def _normalize(field, value):
    """Normalize Gemma's answer into the taxonomy's lexical form."""
    if value is None:
        return None
    value = str(value).strip()
    if not value or value.casefold() in {"null", "none", "n/a", "na", "-", "not stated"}:
        return None
    base = field["base"].split(":")[-1]
    if field.get("enum"):
        return next((item for item in field["enum"] if item.casefold() == value.casefold()), None)
    if base == "date":
        # Gemma is asked to normalize dates, but also accept a full ISO date
        # when an API response adds a time component.
        match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?:[Tt].*)?", value)
        return match.group(1) if match else value
    if base == "gYear":
        match = re.search(r"\b(?:19|20)\d{2}\b", value)
        return match.group(0) if match else value
    return value


def gemma_validate(text, fields, current):
    """Ask Gemma to extract missing values and verify existing values against OCR."""
    spec = []
    for field in fields:
        spec.append({
            "id": field["id"],
            "label": field["label"],
            "type": field["base"].split(":")[-1],
            "current_value": current.get(field["id"]),
            **({"allowed_values": field["enum"]} if field.get("enum") else {}),
            **({"required_pattern": field["pattern"]} if field.get("pattern") else {}),
        })

    prompt = (
        "You are validating an SSM Malaysia AR/XBRL filing against its source OCR.\n"
        "For every field, compare current_value with the OCR. If it matches the source, return it as value. "
        "If it is wrong and the correct value is explicitly present, return the corrected value. "
        "If current_value is empty, extract only when the source clearly supports one answer. Otherwise return null. "
        "Never infer missing facts. Preserve names and identifiers exactly. Return dates as YYYY-MM-DD and years as YYYY. "
        "Enums must use one exact allowed_values item. Return ONLY a JSON object mapping each field id to a string or null.\n\n"
        "FIELDS:\n" + json.dumps(spec, ensure_ascii=False) +
        "\n\nSOURCE OCR:\n" + (text or "")[:24000]
    )
    response = requests.post(f"{OLLAMA_URL}/api/chat", timeout=600, json={
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [{"role": "user", "content": prompt}],
    })
    response.raise_for_status()
    result = json.loads(response.json()["message"]["content"])
    values, invalid = {}, {}
    for field in fields:
        field_id = field["id"]
        proposed = _normalize(field, result.get(field_id))
        if proposed is None:
            continue
        issue = check(field, proposed)
        if issue:
            invalid[field_id] = issue
        else:
            values[field_id] = proposed
    return values, invalid, f"Gemma reviewed {len(fields)} fields; returned {len(values)} supported values"
