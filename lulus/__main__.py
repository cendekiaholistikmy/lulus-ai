"""Command line: python -m lulus check statement.pdf --report report.html"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .check import precheck
from .explain import rm
from .report import write

ROOT = Path(__file__).resolve().parent.parent


def cmd_check(args: argparse.Namespace) -> int:
    result = precheck(args.pdf)
    print(f"lulus.ai {__version__} · {Path(args.pdf).name} · {result.rule_pack}")
    print(f"passed {result.passed} · warnings {result.warnings} · errors {result.errors} · "
          f"{result.seconds * 1000:.0f} ms · {result.network_attempts} network calls\n")
    for x in result.explanations:
        print(f"[{x.severity.upper()}] {x.title}")
        if isinstance(x.reported, int) and isinstance(x.expected, int):
            print(f"  Reported {rm(x.reported)} · Expected {rm(x.expected)}")
        print(f"  Why: {x.why}")
        if x.likely_cause:
            print(f"  Likely cause: {x.likely_cause}")
        if x.source:
            print(f"  Source: {x.source}")
        if x.suggested_fix:
            print(f"  Suggested fix (needs your approval): {x.suggested_fix}")
        print(f"  Rule: {', '.join(x.rule_ids)}\n")
    if args.report or args.json:
        write(result, args.report, args.json)
        print("Report written:", ", ".join(p for p in [args.report, args.json] if p))
    return 1 if result.errors else 0


def cmd_demo(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT))
    from tools.make_samples import make_demo
    pdf = make_demo(ROOT / "samples")
    args.pdf, args.report, args.json = str(pdf), str(ROOT / "results" / "demo_report.html"), None
    (ROOT / "results").mkdir(exist_ok=True)
    cmd_check(args)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lulus", description="Local-first pre-check for SSM MBRS filings.")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="pre-check a financial-statement PDF")
    c.add_argument("pdf")
    c.add_argument("--report", help="write an HTML report")
    c.add_argument("--json", help="write a JSON report")
    c.set_defaults(func=cmd_check)
    d = sub.add_parser("demo", help="generate a sample filing with an error and check it")
    d.set_defaults(func=cmd_demo)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
