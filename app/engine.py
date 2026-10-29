"""Taxonomy engine: everything comes from the SSM MBRS zip via Arelle.

Field list, labels, types, period types, enums, patterns, schemaRef URL — nothing is hardcoded per form.
"""
import os
import re
import tempfile
import threading
from xml.sax.saxutils import escape, quoteattr

from arelle import Cntlr, CntlrCmdLine, PackageManager, XbrlConst

LOCK = threading.RLock()  # Arelle is not thread-safe

NUMERIC = {"decimal", "integer", "nonNegativeInteger", "positiveInteger", "float", "double",
           "int", "long", "short", "nonPositiveInteger", "negativeInteger"}
FORMATS = {"date": r"\d{4}-\d{2}-\d{2}(?:[Tt].*)?", "gYear": r"\d{4}", "boolean": r"true|false|0|1"}


# ---------- taxonomy reading ----------
def _concepts_in_dts(mx):
    """Non-abstract concepts in presentation-tree order."""
    rs = mx.relationshipSet(XbrlConst.parentChild)
    out, seen = [], set()

    def walk(c):
        for r in rs.fromModelObject(c):
            t = r.toModelObject
            if t is not None and t.qname not in seen:
                seen.add(t.qname)
                if not t.isAbstract:
                    out.append(t)
                walk(t)

    for root in rs.rootConcepts:
        walk(root)
    return out


def _facets(cpt):
    f, t = {}, cpt.type
    while t is not None:
        for k, v in (t.facets or {}).items():
            if v and k not in f:
                f[k] = v
        t = t.typeDerivedFrom
        if isinstance(t, list):
            break
    return f


def _field(cpt):
    f, q = _facets(cpt), cpt.qname
    return {
        "id": f"{q.prefix}:{q.localName}",
        "prefix": q.prefix, "ns": q.namespaceURI, "local": q.localName,
        "label": (cpt.label(lang="en", fallbackToQname=False) or q.localName).replace(" [abstract]", "").strip(),
        "type": str(cpt.typeQname), "base": cpt.baseXsdType, "period": cpt.periodType,
        "enum": sorted(map(str, f["enumeration"])) if f.get("enumeration") else None,
        "pattern": str(f["pattern"].pattern) if f.get("pattern") else None,
        "length": f.get("length"), "minLength": f.get("minLength"), "maxLength": f.get("maxLength"),
        "textblock": "textBlockItemType" in str(cpt.typeQname),
        "unit": ("monetary" if cpt.isMonetary else "shares" if cpt.isShares else "pure")
                if cpt.baseXsdType in NUMERIC else None,
    }


class Taxonomy:
    def __init__(self, zip_path, offline=False):
        self.zip, self.offline = os.path.abspath(zip_path), offline
        with LOCK:
            self.c = Cntlr.Cntlr(logFileName="logToBuffer")
            self.c.webCache.workOffline = offline
            PackageManager.addPackage(self.c, self.zip)
            PackageManager.rebuildRemappings(self.c)
            self.eps = PackageManager.packagesConfig["packages"][-1]["entryPoints"]
        self._cache = {}

    def entries(self):
        return {k: v[0][2].replace("\xa0", " ") for k, v in self.eps.items()}

    def form(self, name):
        """{'key','url','desc','fields':[...]} for an entry point (cached)."""
        key = next((k for k in self.eps if k.lower() == name.lower()), None)
        if key is None:
            raise KeyError(name)
        if key not in self._cache:
            local, url, desc = self.eps[key][0]
            with LOCK:
                mx = self.c.modelManager.load(local)
                if mx is None:
                    raise RuntimeError("taxonomy load failed")
                fields = [_field(c) for c in _concepts_in_dts(mx)]
                mx.close()
            self._cache[key] = {"key": key, "url": url, "desc": desc, "fields": fields}
        return self._cache[key]


def defaults(form):
    """Values the taxonomy itself dictates: single-value enums, and the entry-point name where allowed."""
    out = {}
    for f in form["fields"]:
        e = f["enum"] or []
        if len(e) == 1:
            out[f["id"]] = e[0]
        elif form["key"] in e:
            out[f["id"]] = form["key"]
        if f["local"] == "NameAndVersionOfSoftwareUsedToGenerateXBRLFile":
            out[f["id"]] = "lulus.ai 1.0"
    return out


# ---------- value checks ----------
def check(f, v):
    """Return an error string or None."""
    s = str(v)
    if f["enum"] and s not in f["enum"]:
        return f"must be one of: {', '.join(f['enum'])}"
    base = f["base"].split(":")[-1]
    if base in FORMATS and not re.fullmatch(FORMATS[base], s):
        return {"date": "date must be YYYY-MM-DD", "gYear": "year must be YYYY"}.get(base, f"invalid {f['base']}")
    if base in NUMERIC and not re.fullmatch(r"-?\d+(\.\d+)?", s):
        return "must be numeric"
    if f["pattern"] and not re.fullmatch(f["pattern"], s):
        return f"must match {f['pattern']}"
    for k, fn in (("length", lambda n: len(s) == n), ("minLength", lambda n: len(s) >= n),
                  ("maxLength", lambda n: len(s) <= n)):
        if f.get(k) is not None and not fn(int(f[k])):
            return f"{k} {f[k]} violated"
    return None


# ---------- instance building ----------
def _xhtml(text):
    ps = "".join(f"<p>{escape(p)}</p>" for p in text.splitlines() if p.strip())
    return ('<?xml version="1.0" ?><html xmlns="http://www.w3.org/1999/xhtml"><head><title></title></head>'
            f"<body>{ps}</body></html>")


def build_instance(form, values, entity, period, monetary_unit="MYR"):
    by = {f["id"]: f for f in form["fields"]}
    s, e = period["start"], period["end"]
    # AR4's anniversary date is a fact in the instance. Its instant context
    # must be anchored to that fact's value, rather than the UI reporting
    # period end date. Fall back to the supplied period end for other forms.
    instant_date = e
    for field in form["fields"]:
        if field["local"] == "DateOfAnnualReturn" and values.get(field["id"]):
            candidate = str(values[field["id"]])[:10]
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
                instant_date = candidate
            break
    ctx = {"duration": (f"fromto_{s.replace('-', '')}_{e.replace('-', '')}",
                        f"<xbrli:startDate>{s}</xbrli:startDate><xbrli:endDate>{e}</xbrli:endDate>"),
           "instant": (f"asof_{instant_date.replace('-', '')}", f"<xbrli:instant>{instant_date}</xbrli:instant>")}
    ent = (f'<xbrli:entity><xbrli:identifier scheme={quoteattr(entity["scheme"])}>'
           f'{escape(str(entity["identifier"]))}</xbrli:identifier></xbrli:entity>')
    used, units, ns, facts = set(), set(), {}, []
    for q, v in values.items():
        if v in (None, "") or q not in by:
            continue
        f = by[q]
        ns[f["prefix"]] = f["ns"]
        used.add(f["period"])
        attrs = f'contextRef="{ctx[f["period"]][0]}"'
        if f["unit"]:
            u = monetary_unit if f["unit"] == "monetary" else f["unit"]
            units.add((f["unit"], u))
            attrs += f' unitRef="{u}" decimals="INF"'
        val = _xhtml(v) if f["textblock"] and not str(v).lstrip().startswith("<") else str(v)
        facts.append(f"<{q} {attrs}>{escape(val)}</{q}>")
    unit_xml = "".join(
        f'<xbrli:unit id="{u}"><xbrli:measure>{"iso4217:" if k == "monetary" else "xbrli:"}{u}</xbrli:measure></xbrli:unit>'
        for k, u in sorted(units))
    nsdecl = " ".join(f'xmlns:{p}="{u}"' for p, u in sorted(ns.items()))
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:link="http://www.xbrl.org/2003/linkbase" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" '
        f"{nsdecl}>\n"
        f'<link:schemaRef xlink:type="simple" xlink:href="{form["url"]}" />\n'
        + "".join(f'<xbrli:context id="{ctx[p][0]}">{ent}<xbrli:period>{ctx[p][1]}</xbrli:period></xbrli:context>\n'
                  for p in ("duration", "instant") if p in used)
        + (unit_xml + "\n" if unit_xml else "") + "\n".join(facts) + "\n</xbrli:xbrl>\n")


# ---------- Arelle validation ----------
def validate_instance(tax, inst_path):
    """Validate via Arelle's command-line entry point. Returns (problems, ignored_formula_errors)."""
    with LOCK:
        log = tempfile.NamedTemporaryFile(suffix=".log", delete=False).name
        args = ["--packages", tax.zip, "--file", inst_path, "--validate", "--logFile", log]
        if tax.offline:
            args.append("--workOffline")
        CntlrCmdLine.parseAndRun(args)
        text = open(log, encoding="utf-8", errors="replace").read()
        os.unlink(log)
    lines = [l for l in text.splitlines() if l.startswith("[") and not l.startswith(("[info]", "[]"))]
    # SSM formula files can reference the XML Schema type `xs:date` without
    # declaring the `xs` prefix. Arelle reports that taxonomy compile failure
    # before instance validation; it is not an error in the user's date value.
    xs_date_prefix_error = any(
        "XPST0081" in l and "prefix" in l.lower() and "xs:date" in l
        for l in lines
    )
    xs_date_parser_error = any("'xs:date' is not in list" in l for l in lines)
    formula_compile_noise = xs_date_prefix_error or xs_date_parser_error
    ignored = [
        l for l in lines
        if "XPST0003" in l
        or ("XPST0081" in l and "xs:date" in l)
        or "'xs:date' is not in list" in l
        or (formula_compile_noise and any(token in l for token in (
            "[parser:", "[debug]", "Traceback", "arelle/formula", "pyparsing",
            "formula_ssmt-ar-1965_2022-12-31.xml",
        )))
    ]
    return [l[:400] for l in lines if l not in ignored], len(ignored)
