"""Generate SYNTHETIC financial-statement PDFs, clean or with one seeded error.

All companies, names and numbers are invented. Each seeded file comes
with a ground-truth label so the benchmark can score lulus.ai exactly.

    python tools/make_samples.py            # writes samples/benchmark/*
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lulus.extract import load_mapping  # noqa: E402

KINDS = ["TRANSPOSITION", "DIGIT", "SIGN", "SCALE", "MISSING_FIELD", "MISSING_SECTION"]

SFP = [("ASSETS", None), ("ppe", 1), ("total_non_current_assets", 1), ("inventories", 1),
       ("trade_receivables", 1), ("cash", 1), ("total_current_assets", 1), ("total_assets", 1),
       ("EQUITY AND LIABILITIES", None), ("share_capital", 1), ("retained_earnings", 1), ("total_equity", 1),
       ("borrowings_non_current", 1), ("total_non_current_liabilities", 1), ("trade_payables", 1),
       ("borrowings_current", 1), ("total_current_liabilities", 1), ("total_liabilities", 1),
       ("total_equity_and_liabilities", 1)]
PL = [("revenue", 1), ("cost_of_sales", 1), ("gross_profit", 1), ("other_income", 1),
      ("administrative_expenses", 1), ("finance_costs", 1), ("profit_before_tax", 1),
      ("income_tax_expense", 1), ("profit_for_the_year", 1)]


def company(rng: random.Random) -> dict[str, int]:
    v: dict[str, int] = {}
    v["ppe"] = rng.randrange(400_000, 3_900_000)
    v["total_non_current_assets"] = v["ppe"]
    v["inventories"] = rng.randrange(60_000, 900_000)
    v["trade_receivables"] = rng.randrange(60_000, 900_000)
    v["cash"] = rng.randrange(20_000, 700_000)
    v["total_current_assets"] = v["inventories"] + v["trade_receivables"] + v["cash"]
    v["total_assets"] = v["total_non_current_assets"] + v["total_current_assets"]
    v["borrowings_non_current"] = rng.randrange(50_000, v["total_assets"] // 4)
    v["total_non_current_liabilities"] = v["borrowings_non_current"]
    v["trade_payables"] = rng.randrange(40_000, v["total_assets"] // 6)
    v["borrowings_current"] = rng.randrange(10_000, v["total_assets"] // 8)
    v["total_current_liabilities"] = v["trade_payables"] + v["borrowings_current"]
    v["total_liabilities"] = v["total_non_current_liabilities"] + v["total_current_liabilities"]
    v["total_equity"] = v["total_assets"] - v["total_liabilities"]
    v["share_capital"] = rng.randrange(100_000, max(v["total_equity"] // 2, 100_001))
    v["retained_earnings"] = v["total_equity"] - v["share_capital"]
    v["total_equity_and_liabilities"] = v["total_equity"] + v["total_liabilities"]
    v["revenue"] = rng.randrange(1_200_000, 9_800_000)
    v["cost_of_sales"] = -int(v["revenue"] * rng.uniform(0.45, 0.75))
    v["gross_profit"] = v["revenue"] + v["cost_of_sales"]
    v["other_income"] = rng.randrange(5_000, 120_000)
    v["administrative_expenses"] = -int(v["gross_profit"] * rng.uniform(0.3, 0.6))
    v["finance_costs"] = -rng.randrange(5_000, 90_000)
    v["profit_before_tax"] = (v["gross_profit"] + v["other_income"] + v["administrative_expenses"]
                              + v["finance_costs"])
    v["income_tax_expense"] = -int(max(v["profit_before_tax"], 0) * 0.24)
    v["profit_for_the_year"] = v["profit_before_tax"] + v["income_tax_expense"]
    return v


def fmt(n: int) -> str:
    if n == 0:
        return "-"
    return f"({abs(n):,})" if n < 0 else f"{n:,}"


def corrupt(kind: str, v: int, rng: random.Random) -> int:
    s = str(abs(v))
    sign = -1 if v < 0 else 1
    if kind == "TRANSPOSITION":
        pairs = [i for i in range(len(s) - 1) if s[i] != s[i + 1] and not (i == 0 and s[1] == "0")]
        i = rng.choice(pairs)
        return sign * int(s[:i] + s[i + 1] + s[i] + s[i + 2:])
    if kind == "DIGIT":
        i = rng.randrange(1, len(s))
        d = rng.choice([c for c in "0123456789" if c != s[i]])
        return sign * int(s[:i] + d + s[i + 1:])
    if kind == "SIGN":
        return -v
    if kind == "SCALE":
        return round(v / 1000)
    raise ValueError(kind)


def render(path: Path, values: dict[str, int], name: str, omit: str | None = None,
           include_declaration: bool = True, override: dict[str, int] | None = None) -> None:
    labels = {k: syns[0] for k, syns in load_mapping()["amount"].items()}
    override = override or {}
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4

    def page(title: str, rows: list, header: bool) -> None:
        y = height - 72
        c.setFont("Helvetica-Bold", 13)
        c.drawString(72, y, title)
        y -= 26
        c.setFont("Helvetica", 11)
        if header:
            for line in [f"Company name: {name}", "Registration no: 000000-X (synthetic)",
                         "Financial year end: 31 December 2025"]:
                c.drawString(72, y, line)
                y -= 18
            y -= 10
        for key, kind in rows:
            if kind is None:
                c.setFont("Helvetica-Bold", 11)
                c.drawString(72, y, key)
                c.setFont("Helvetica", 11)
            elif key != omit:
                c.drawString(72, y, labels[key])
                c.drawRightString(width - 72, y, fmt(override.get(key, values[key])))
            y -= 18
        c.showPage()

    page("STATEMENT OF FINANCIAL POSITION AS AT 31 DECEMBER 2025 (RM)", SFP, header=True)
    page("STATEMENT OF PROFIT OR LOSS FOR THE YEAR ENDED 31 DECEMBER 2025 (RM)", PL, header=False)
    if include_declaration:
        c.setFont("Helvetica-Bold", 13)
        c.drawString(72, height - 72, "STATUTORY DECLARATION")
        c.setFont("Helvetica", 11)
        c.drawString(72, height - 100, "I, the director primarily responsible for the financial management of the")
        c.drawString(72, height - 118, "company, declare that these financial statements are correct (synthetic sample).")
        c.showPage()
    c.save()


NUMERIC = [k for k, kind in SFP + PL if kind]


def make_set(out_dir: Path, clean: int = 10, per_kind: int = 10, seed: int = 2026) -> list[dict]:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    labels = []
    jobs = [("CLEAN", i) for i in range(clean)] + [(k, i) for k in KINDS for i in range(per_kind)]
    for n, (kind, i) in enumerate(jobs, start=1):
        values = company(rng)
        name = f"Contoh {n:03d} Sdn. Bhd."
        path = out_dir / f"filing_{n:03d}_{kind.lower()}.pdf"
        label = {"file": path.name, "kind": kind, "field": None, "original": None, "printed": None}
        if kind == "CLEAN":
            render(path, values, name)
        elif kind == "MISSING_SECTION":
            render(path, values, name, include_declaration=False)
            label["field"] = "statutory_declaration"
        elif kind == "MISSING_FIELD":
            f = rng.choice(NUMERIC)
            render(path, values, name, omit=f)
            label.update(field=f, original=values[f])
        else:
            candidates = [f for f in NUMERIC if abs(values[f]) >= 10_000]
            f = rng.choice(candidates)
            printed = corrupt(kind, values[f], rng)
            render(path, values, name, override={f: printed})
            label.update(field=f, original=values[f], printed=printed)
        labels.append(label)
    (out_dir / "labels.json").write_text(json.dumps(labels, indent=2), encoding="utf-8")
    return labels


def make_demo(out_dir: Path) -> Path:
    """The example used in the pitch: total equity typed 1,248,500 instead of 1,284,500."""
    out_dir.mkdir(parents=True, exist_ok=True)
    v = company(random.Random(7))
    # rebuild the balance sheet around the pitch example
    v["share_capital"], v["retained_earnings"] = 500_000, 784_500
    v["total_equity"] = 1_284_500
    v["total_liabilities"] = v["total_non_current_liabilities"] + v["total_current_liabilities"]
    v["total_equity_and_liabilities"] = v["total_equity"] + v["total_liabilities"]
    v["total_assets"] = v["total_equity_and_liabilities"]
    v["ppe"] = v["total_assets"] - v["total_current_assets"]
    v["total_non_current_assets"] = v["ppe"]
    path = out_dir / "demo_filing.pdf"
    render(path, v, "Contoh Demo Sdn. Bhd.", include_declaration=False, override={"total_equity": 1_248_500})
    return path


if __name__ == "__main__":
    labels = make_set(ROOT / "samples" / "benchmark")
    print(f"wrote {len(labels)} synthetic filings to samples/benchmark/")
    print("demo:", make_demo(ROOT / "samples"))
