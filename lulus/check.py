"""One call that runs the whole pre-check: extract, rules, explain."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .explain import Explanation, explain
from .extract import Extraction, extract_pdf
from .offline import NetworkGuard
from .rules import Check, load_rules, run


@dataclass
class Result:
    source: str
    rule_pack: str
    extraction: Extraction
    checks: list[Check]
    explanations: list[Explanation]
    seconds: float
    network_attempts: int

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == "pass")

    @property
    def errors(self) -> int:
        return sum(1 for e in self.explanations if e.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for e in self.explanations if e.severity == "warning")


SEVERITY_ORDER = {"error": 0, "warning": 1}


def precheck(pdf_path: str | Path, rules_path: Path | None = None) -> Result:
    rules = load_rules(rules_path)
    start = time.perf_counter()
    with NetworkGuard() as guard:
        extraction = extract_pdf(pdf_path)
        checks, issues = run(extraction, rules)
        explanations = sorted((explain(i, extraction) for i in issues),
                              key=lambda e: (SEVERITY_ORDER.get(e.severity, 9), e.title))
    return Result(str(pdf_path), f"{rules['pack']} v{rules['version']} (modelled on {rules['modelled_on']})",
                  extraction, checks, explanations, time.perf_counter() - start, guard.attempts)
