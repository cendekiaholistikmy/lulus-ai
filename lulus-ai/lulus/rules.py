"""Deterministic rule engine. Only rules decide whether a check passes.

Equation rules have the form  lhs = rhs_1 + rhs_2 + ...  (expenses are
negative amounts, so subtraction is just addition of a negative value).

When an equation fails, the engine works out which field is most likely
wrong by combining two signals:
  * pattern: would correcting this field fix the gap with a recognisable
    keying mistake (swapped digits, one wrong digit, wrong sign, RM'000)?
  * consistency: fields that also appear in rules that PASS are less
    likely to be the culprit than fields only seen in failing rules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .extract import Extraction

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass
class Check:
    rule_id: str
    kind: str          # equation | required | section | sign | confidence
    status: str        # pass | fail | skipped
    severity: str = "error"
    fields: list[str] = field(default_factory=list)
    detail: dict = field(default_factory=dict)


@dataclass
class Issue:
    severity: str
    kind: str
    field: str | None
    rule_ids: list[str]
    reported: object = None
    expected: object = None
    pattern: str | None = None
    detail: dict = field(default_factory=dict)


def load_rules(path: Path | None = None) -> dict:
    with open(path or DATA_DIR / "sample_rules.json", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- patterns
def _digits(n: int) -> str:
    return str(abs(int(n)))


def keying_pattern(reported: int, expected: int) -> str | None:
    """Name the keying mistake that turns `expected` into `reported`, if any."""
    if reported == expected:
        return None
    if reported == -expected:
        return "SIGN"
    if expected != 0 and abs(reported * 1000 - expected) < 1000:
        return "SCALE"
    a, b = _digits(reported), _digits(expected)
    if len(a) == len(b) and (reported >= 0) == (expected >= 0):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]:
            return "TRANSPOSITION"
        if len(diff) == 1:
            return "DIGIT"
    return None


# ---------------------------------------------------------------- engine
def _terms(rule: dict) -> list[tuple[str, int]]:
    return [(rule["lhs"], 1)] + [(f, 1) for f in rule["rhs"]]


def _implied(rule: dict, values: dict[str, int], target: str) -> int:
    """Value `target` would need for the equation to hold."""
    lhs, rhs = rule["lhs"], rule["rhs"]
    if target == lhs:
        return sum(values[f] for f in rhs)
    return values[lhs] - sum(values[f] for f in rhs if f != target)


def run(extraction: Extraction, rules: dict | None = None) -> tuple[list[Check], list[Issue]]:
    rules = rules or load_rules()
    vals = extraction.values
    amounts = {k: v.value for k, v in vals.items() if isinstance(v.value, int)}
    checks: list[Check] = []
    issues: list[Issue] = []

    # 1. required text fields and amounts
    required_amounts = sorted({f for r in rules["equations"] for f in [r["lhs"], *r["rhs"]]})
    for req in rules["required_text"]:
        ok = req["field"] in vals
        checks.append(Check(req["id"], "required", "pass" if ok else "fail", "error", [req["field"]]))
        if not ok:
            issues.append(Issue("error", "missing_field", req["field"], [req["id"]]))
    for f in required_amounts:
        ok = f in amounts
        checks.append(Check(f"REQ-{f}", "required", "pass" if ok else "fail", "error", [f]))
        if not ok:
            issues.append(Issue("error", "missing_field", f, [f"REQ-{f}"]))

    # 2. required sections
    for sec in rules["required_sections"]:
        ok = sec["section"] in extraction.sections
        checks.append(Check(sec["id"], "section", "pass" if ok else "fail", sec["severity"], [],
                            {"section": sec["section"]}))
        if not ok:
            issues.append(Issue(sec["severity"], "missing_section", None, [sec["id"]],
                                detail={"section": sec["section"], "terse": sec["terse_message"],
                                        "basis": sec["basis"]}))

    # 3. equations
    eq_checks = []
    for rule in rules["equations"]:
        fields = [rule["lhs"], *rule["rhs"]]
        if any(f not in amounts for f in fields):
            eq_checks.append(Check(rule["id"], "equation", "skipped", rule["severity"], fields))
            continue
        gap = amounts[rule["lhs"]] - sum(amounts[f] for f in rule["rhs"])
        eq_checks.append(Check(rule["id"], "equation", "pass" if gap == 0 else "fail",
                               rule["severity"], fields, {"gap": gap}))
    checks.extend(eq_checks)

    by_id = {r["id"]: r for r in rules["equations"]}
    failing = [c for c in eq_checks if c.status == "fail"]
    passing = [c for c in eq_checks if c.status == "pass"]
    groups: dict[str, dict] = {}
    for chk in failing:
        rule = by_id[chk.rule_id]
        cands = []
        for f, _ in _terms(rule):
            implied = _implied(rule, amounts, f)
            pattern = keying_pattern(amounts[f], implied)
            score = (3 if pattern else 0)
            score += sum(1 for c in failing if f in c.fields)
            score -= 1.5 * sum(1 for c in passing if f in c.fields)
            cands.append((score, f == rule["lhs"], f, implied, pattern))
        best = max(cands, key=lambda c: c[:2])
        _, _, f, implied, pattern = best
        # other fields that explain the gap equally well: show them, don't hide the ambiguity
        alts = [c[2] for c in cands if c[0] == best[0] and c[2] != f and c[4]]
        g = groups.setdefault(f, {"rules": [], "implied": implied, "pattern": pattern, "alternatives": []})
        g["rules"].append(chk.rule_id)
        g["alternatives"] += [a for a in alts if a not in g["alternatives"]]
        if pattern and not g["pattern"]:
            g["pattern"], g["implied"] = pattern, implied
    for f, g in groups.items():
        issues.append(Issue("error", "equation", f, g["rules"], amounts[f], g["implied"], g["pattern"],
                            {"basis": [by_id[r]["basis"] for r in g["rules"]],
                             "alternatives": g["alternatives"]}))

    # 4. signs
    for rule in rules["signs"]:
        for f in rule["positive"] + rule["negative"]:
            if f not in amounts or amounts[f] == 0:
                continue
            want_pos = f in rule["positive"]
            ok = (amounts[f] > 0) == want_pos
            checks.append(Check(f"{rule['id']}-{f}", "sign", "pass" if ok else "fail", rule["severity"], [f]))
            if not ok and f not in groups:
                issues.append(Issue(rule["severity"], "sign", f, [rule["id"]], amounts[f], -amounts[f], "SIGN",
                                    {"basis": [rule["basis"]]}))

    # 5. extraction confidence
    for v in vals.values():
        if v.needs_confirmation:
            checks.append(Check(f"CONF-{v.concept}", "confidence", "fail", "warning", [v.concept]))
            issues.append(Issue("warning", "low_confidence", v.concept, [f"CONF-{v.concept}"], v.value,
                                detail={"label": v.label, "confidence": v.confidence}))

    return checks, issues
