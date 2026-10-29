"""Write the pre-check report as a self-contained HTML page and as JSON."""

from __future__ import annotations

import html
import json
from dataclasses import asdict
from pathlib import Path

from .check import Result
from .explain import rm

CSS = """
:root{--bg:#030A18;--card:#081A33;--line:#1B3A60;--ink:#F3F7FF;--body:#B4C3DF;--muted:#6F86AD;
--cyan:#1AB0FF;--amber:#FFB020;--red:#FF6B6B;--green:#22D3A0}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:40px 20px 64px}
.brand{font-weight:900;font-size:28px}.brand span{color:var(--cyan)}
.meta{color:var(--muted);font-size:14px;margin:4px 0 28px}
h1{font-size:36px;font-weight:900;text-transform:uppercase;margin:0 0 4px}
.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:24px 0 32px}
.tile{background:var(--card);border:2px solid var(--line);border-radius:8px;padding:18px 22px}
.tile b{display:block;font-size:44px;font-weight:900;line-height:1.1}
.tile.pass{border-color:var(--green)}.tile.pass span{color:var(--green)}
.tile.warn{border-color:var(--amber)}.tile.warn span{color:var(--amber)}
.tile.err{border-color:var(--red)}.tile.err span{color:var(--red)}
.tile span{font-weight:700;text-transform:uppercase;letter-spacing:1px;font-size:14px}
.issue{background:var(--card);border:1px solid var(--line);border-left:6px solid var(--red);border-radius:8px;
padding:20px 24px;margin:0 0 16px}
.issue.warning{border-left-color:var(--amber)}
.pill{display:inline-block;font-size:12px;font-weight:700;letter-spacing:1px;text-transform:uppercase;
padding:2px 10px;border-radius:999px;background:#3A1220;color:var(--red)}
.warning .pill{background:#3A2A08;color:var(--amber)}
.issue h2{font-size:22px;margin:10px 0 8px}
.nums{font-family:ui-monospace,Menlo,Consolas,monospace;color:var(--ink);margin:0 0 8px}
.issue p{margin:6px 0;color:var(--body)}.issue p b{color:var(--ink)}
.fix{background:#062A40;border:1px solid var(--cyan);border-radius:6px;padding:10px 14px;color:var(--ink)!important}
.rule{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px;color:var(--muted)}
.ok{color:var(--green);font-weight:700}
footer{margin-top:40px;color:var(--muted);font-size:13px;border-top:1px solid var(--line);padding-top:16px}
@media (max-width:640px){.tiles{grid-template-columns:1fr}}
"""


def to_html(result: Result) -> str:
    e = html.escape
    company = result.extraction.values.get("company_name")
    parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
             f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>lulus.ai pre-check report</title><style>{CSS}</style></head><body><div class='wrap'>",
             "<div class='brand'>lulus<span>.ai</span></div>",
             f"<div class='meta'>Pre-check report · {e(Path(result.source).name)}"
             f"{' · ' + e(str(company.value)) if company else ''} · rules: {e(result.rule_pack)}</div>",
             "<h1>Pre-check result</h1>",
             "<div class='tiles'>"
             f"<div class='tile pass'><span>Passed</span><b>{result.passed}</b></div>"
             f"<div class='tile warn'><span>Warnings</span><b>{result.warnings}</b></div>"
             f"<div class='tile err'><span>Errors</span><b>{result.errors}</b></div></div>"]
    if not result.explanations:
        parts.append("<p class='ok'>No issues found by this rule pack. Review the figures before submitting to mTool.</p>")
    for x in result.explanations:
        parts.append(f"<div class='issue {e(x.severity)}'><span class='pill'>{e(x.severity)}</span>"
                     f"<h2>{e(x.title)}</h2>")
        if isinstance(x.reported, int) and isinstance(x.expected, int):
            parts.append(f"<div class='nums'>Reported {e(rm(x.reported))} · Expected {e(rm(x.expected))}</div>")
        parts.append(f"<p><b>Why:</b> {e(x.why)}</p>")
        if x.likely_cause:
            parts.append(f"<p><b>Likely cause:</b> {e(x.likely_cause)}</p>")
        if x.source:
            parts.append(f"<p><b>Source:</b> {e(x.source)}</p>")
        if x.suggested_fix:
            parts.append(f"<p class='fix'><b>Suggested fix (needs your approval):</b> {e(x.suggested_fix)}</p>")
        parts.append(f"<p class='rule'>{e(', '.join(x.rule_ids))}: {e(' '.join(x.rule_text))}</p></div>")
    parts.append(f"<footer>Checked locally in {result.seconds * 1000:.0f} ms · {result.network_attempts} network calls · "
                 "lulus.ai never files anything; you approve every fix. Prototype rule pack: not SSM's official "
                 "formula linkbase.</footer></div></body></html>")
    return "".join(parts)


def to_json(result: Result) -> str:
    return json.dumps({
        "source": result.source,
        "rule_pack": result.rule_pack,
        "summary": {"passed": result.passed, "warnings": result.warnings, "errors": result.errors},
        "seconds": round(result.seconds, 4),
        "network_attempts": result.network_attempts,
        "issues": [asdict(x) for x in result.explanations],
    }, indent=2, ensure_ascii=False)


def write(result: Result, html_path: str | Path | None = None, json_path: str | Path | None = None) -> None:
    if html_path:
        Path(html_path).write_text(to_html(result), encoding="utf-8")
    if json_path:
        Path(json_path).write_text(to_json(result), encoding="utf-8")
