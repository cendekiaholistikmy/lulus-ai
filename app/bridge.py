"""JSON bridge between SvelteKit and the Python engine.

stdin : {"cmd": "entries|form|extract|validate", ...}
stdout: one JSON object ({"error": "..."} on failure). All library noise goes to stderr.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
ZIP = os.environ.get("MBRS_ZIP", str(ROOT / "taxonomy.zip"))
OFFLINE = os.environ.get("MBRS_OFFLINE") == "1"
SCHEME = os.environ.get("MBRS_ENTITY_SCHEME", "http://www.ssm.com.my/entity")  # override if SSM requires another scheme
CACHE = ROOT / ".cache"
INSTANCE_DIR = ROOT / "output" / "instances"
STAMP = f"{int(os.path.getmtime(ZIP))}-{os.path.getsize(ZIP)}" if os.path.exists(ZIP) else "none"

_tax = None


def taxonomy():
    global _tax
    if _tax is None:
        from engine import Taxonomy
        _tax = Taxonomy(ZIP, OFFLINE)
    return _tax


def _cached(name, build):
    """Taxonomy parsing via Arelle is slow, so parsed results are cached per taxonomy.zip version."""
    path = CACHE / f"{STAMP}-{name}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = build()
    CACHE.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    return data


def get_form(entry):
    return _cached(f"form-{entry.lower()}", lambda: taxonomy().form(entry))


def public_form(entry):
    from engine import defaults
    form = get_form(entry)
    keep = ("id", "label", "base", "period", "enum", "pattern", "length", "minLength", "maxLength", "textblock", "unit")
    return {"key": form["key"], "desc": form["desc"], "defaults": defaults(form),
            "fields": [{k: f.get(k) for k in keep} for f in form["fields"]]}


def cmd_entries(_):
    return {"entries": _cached("entries", lambda: taxonomy().entries())}


def cmd_form(req):
    return public_form(req["entry"])


def cmd_extract(req):
    from extract import gemma_validate
    form = get_form(req["entry"])
    text = req.get("text") or ""
    current = {k: v for k, v in (req.get("values") or {}).items() if v}
    try:
        values, invalid, note = gemma_validate(text, form["fields"], current)
        return {"stage1": {}, "stage2": values, "invalid": invalid, "note": note}
    except Exception as e:
        return {"stage1": {}, "stage2": {}, "invalid": {}, "note": f"Gemma unavailable: {e}"}


def cmd_validate(req):
    from engine import build_instance, check, validate_instance
    form = get_form(req["entry"])
    by = {f["id"]: f for f in form["fields"]}
    values = {k: v for k, v in (req.get("values") or {}).items() if v not in (None, "")}
    errors = {k: e for k, v in values.items() if k in by and (e := check(by[k], v))}
    out = {"fieldErrors": errors, "problems": [], "ignored": 0, "xml": None}
    if errors or not values:
        return out
    entity = {"scheme": (req.get("entity") or {}).get("scheme") or SCHEME,
              "identifier": (req.get("entity") or {}).get("identifier")}
    period = req.get("period") or {}
    if not entity["identifier"] or not period.get("start") or not period.get("end"):
        return {**out, "error": "Entity identifier and reporting period are required."}
    xml = build_instance(form, values, entity, period)
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = INSTANCE_DIR / f"{req['entry']}-{stamp}"
    run_dir.mkdir()
    path = run_dir / "instance.xml"
    path.write_text(xml, encoding="utf-8")
    problems, ignored = validate_instance(SimpleNamespace(zip=ZIP, offline=OFFLINE), str(path))
    return {**out, "problems": problems, "ignored": ignored, "xml": xml,
            "instancePath": str(path)}


HANDLERS = {"entries": cmd_entries, "form": cmd_form, "extract": cmd_extract, "validate": cmd_validate}

if __name__ == "__main__":
    real_stdout, sys.stdout = sys.stdout, sys.stderr
    try:
        request = json.load(sys.stdin)
        result = HANDLERS[request["cmd"]](request)
    except Exception as e:
        result = {"error": f"{type(e).__name__}: {e}"}
    real_stdout.write(json.dumps(result, ensure_ascii=False))
    real_stdout.flush()
