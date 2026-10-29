"""Turn rule failures into plain-language explanations and suggested fixes.

This prototype uses deterministic templates, so every sentence is
traceable to a rule result. A small local language model can be plugged
in later through `LocalModelExplainer`; it may only rephrase, and if it
is unsure the raw rule is shown instead. The explainer never changes a
pass/fail result.
"""

from __future__ import annotations

from dataclasses import dataclass

from .extract import Extraction
from .rules import Issue


@dataclass
class Explanation:
    severity: str
    title: str
    field: str | None
    label: str
    reported: object
    expected: object
    why: str
    likely_cause: str | None
    suggested_fix: str | None
    rule_ids: list[str]
    rule_text: list[str]
    source: str | None
    pattern: str | None = None
    alternatives: tuple = ()

    @property
    def is_actionable(self) -> bool:
        """True when the issue names the field, the rule and a concrete fix."""
        return bool(self.rule_ids) and self.suggested_fix is not None and (self.field or self.title)


def rm(n: object) -> str:
    if not isinstance(n, int):
        return str(n)
    return f"RM ({abs(n):,})" if n < 0 else f"RM {n:,}"


def _swap_note(reported: int, expected: int) -> str:
    a, b = str(abs(reported)), str(abs(expected))
    i = next(i for i in range(len(a)) if a[i] != b[i])
    return f"{a[i]}{a[i + 1]} vs {b[i]}{b[i + 1]}"


CAUSES = {
    "TRANSPOSITION": lambda r, e: f"two digits look swapped when retyping ({_swap_note(r, e)}).",
    "DIGIT": lambda r, e: "one digit looks mistyped.",
    "SIGN": lambda r, e: "the sign looks flipped (brackets missing or added).",
    "SCALE": lambda r, e: "the figure looks 1,000 times too small. Was it typed in RM'000?",
}


_MAPPING = None


def _label(extraction: Extraction, concept: str | None) -> str:
    global _MAPPING
    if concept is None:
        return ""
    v = extraction.values.get(concept)
    if v:
        return v.label
    if _MAPPING is None:
        from .extract import load_mapping
        _MAPPING = load_mapping()
    syns = _MAPPING["amount"].get(concept) or _MAPPING["text"].get(concept)
    return syns[0] if syns else concept.replace("_", " ").capitalize()


def _source(extraction: Extraction, concept: str | None) -> str | None:
    v = extraction.values.get(concept) if concept else None
    return f"page {v.page}, line {v.line}" if v else None


def explain(issue: Issue, extraction: Extraction) -> Explanation:
    label = _label(extraction, issue.field)
    source = _source(extraction, issue.field)
    rule_text = issue.detail.get("basis", [])
    if isinstance(rule_text, str):
        rule_text = [rule_text]

    if issue.kind == "equation":
        gap = issue.reported - issue.expected
        cause = CAUSES[issue.pattern](issue.reported, issue.expected) if issue.pattern else None
        fix = f"Change {label} from {rm(issue.reported)} to {rm(issue.expected)}." if issue.pattern else None
        alts = [_label(extraction, a) for a in issue.detail.get("alternatives", [])]
        if cause and alts:
            cause += f" {' or '.join(alts)} could explain the gap equally well, so check {'it' if len(alts) == 1 else 'them'} too."
        return Explanation(
            "error", f"{label} doesn't add up", issue.field, label, issue.reported, issue.expected,
            f"{label} is reported as {rm(issue.reported)}, but the related figures imply {rm(issue.expected)}"
            f" (a difference of RM {abs(gap):,}).",
            cause or "lulus.ai can't pin down the keying mistake. Check the rule and the source figures.",
            fix, issue.rule_ids, rule_text, source, issue.pattern,
            tuple(issue.detail.get("alternatives", [])))

    if issue.kind == "sign":
        return Explanation(
            issue.severity, f"{label} has an unexpected sign", issue.field, label, issue.reported, issue.expected,
            f"{label} is {rm(issue.reported)}, but this line is normally shown "
            f"{'in brackets (negative)' if issue.expected < 0 else 'as a positive amount'}.",
            CAUSES["SIGN"](0, 0), f"Change {label} to {rm(issue.expected)} if the sign is wrong.",
            issue.rule_ids, rule_text, source, "SIGN")

    if issue.kind == "missing_field":
        return Explanation(
            "error", f"{label} is missing", issue.field, label, None, None,
            f"No value for {label} was found in the statement.",
            "the line may be missing, misspelt, or placed on a page that was not uploaded.",
            f"Add {label} to the statement. If the company has none, report it as 0 (or '-').",
            issue.rule_ids, [f"{label} must be reported."], None)

    if issue.kind == "missing_section":
        name = issue.detail["section"].replace("_", " ")
        return Explanation(
            "error", f"The {name} is missing", None, name.title(), None, None,
            f"The filing has no {name} section. A validator would typically flag this tersely, "
            f"e.g. “{issue.detail['terse']}”.",
            "the declaration page was not included in the uploaded statements.",
            f"Add the signed {name} page (with the declarant's details) and run the check again.",
            issue.rule_ids, [issue.detail["basis"]], None)

    if issue.kind == "low_confidence":
        return Explanation(
            "warning", f"Please confirm: {label}", issue.field, label, issue.reported, None,
            f"The line “{issue.detail['label']}” was matched to {label} with "
            f"{issue.detail['confidence']:.0%} confidence.",
            "the label wording differs from the expected wording.",
            f"Confirm that “{issue.detail['label']}” is {label}, or correct the mapping.",
            issue.rule_ids, ["Uncertain values must be confirmed by the user."], source)

    raise ValueError(f"unknown issue kind: {issue.kind}")


class LocalModelExplainer:  # pragma: no cover - roadmap hook
    """Placeholder for a small open-weights model that rephrases explanations.

    Contract: input is an Explanation built from rule results; output may only
    rewrite `why` and `likely_cause`. If the model's confidence is low, the
    template explanation (and raw rule) is returned unchanged.
    """

    def __call__(self, explanation: Explanation) -> Explanation:
        raise NotImplementedError("Local model explainer is on the roadmap (Phase 2).")
