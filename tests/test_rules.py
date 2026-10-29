from lulus.extract import extract_lines
from lulus.rules import keying_pattern, run


def test_keying_patterns():
    assert keying_pattern(1_248_500, 1_284_500) == "TRANSPOSITION"
    assert keying_pattern(1_284_600, 1_284_500) == "DIGIT"
    assert keying_pattern(-52_000, 52_000) == "SIGN"
    assert keying_pattern(1_285, 1_284_500) == "SCALE"
    assert keying_pattern(1_000, 2_345_678) is None
    assert keying_pattern(500, 500) is None


BALANCED = {
    "Property, plant and equipment": "1,000,000", "Total non-current assets": "1,000,000",
    "Inventories": "200,000", "Trade receivables": "150,000", "Cash and bank balances": "50,000",
    "Total current assets": "400,000", "Total assets": "1,400,000",
    "Share capital": "500,000", "Retained earnings": "784,500", "Total equity": "1,284,500",
    "Borrowings (non-current)": "60,000", "Total non-current liabilities": "60,000",
    "Trade payables": "40,000", "Borrowings (current)": "15,500", "Total current liabilities": "55,500",
    "Total liabilities": "115,500", "Total equity and liabilities": "1,400,000",
    "Revenue": "2,000,000", "Cost of sales": "(1,200,000)", "Gross profit": "800,000",
    "Other income": "10,000", "Administrative expenses": "(500,000)", "Finance costs": "(10,000)",
    "Profit before tax": "300,000", "Income tax expense": "(72,000)", "Profit for the year": "228,000",
}


def lines(overrides=None, declaration=True):
    rows = [(1, 1, "Company name: Contoh Sdn. Bhd."), (1, 2, "Registration no: 000000-X"),
            (1, 3, "Financial year end: 31 December 2025")]
    for i, (label, amount) in enumerate(BALANCED.items(), start=4):
        rows.append((1, i, f"{label} {(overrides or {}).get(label, amount)}"))
    if declaration:
        rows.append((3, 1, "STATUTORY DECLARATION"))
    return rows


def test_balanced_statement_has_no_issues():
    checks, issues = run(extract_lines(lines()))
    assert issues == []
    assert all(c.status == "pass" for c in checks)


def test_transposed_total_equity_is_pinpointed():
    _, issues = run(extract_lines(lines({"Total equity": "1,248,500"})))
    assert len(issues) == 1
    issue = issues[0]
    assert issue.field == "total_equity"
    assert issue.pattern == "TRANSPOSITION"
    assert issue.expected == 1_284_500
    assert set(issue.rule_ids) == {"SFP-04", "SFP-08"}


def test_flipped_sign_on_expense():
    _, issues = run(extract_lines(lines({"Cost of sales": "1,200,000"})))
    assert issues[0].field == "cost_of_sales" and issues[0].pattern == "SIGN"


def test_missing_declaration_and_missing_line():
    rows = [r for r in lines(declaration=False) if not r[2].startswith("Trade payables")]
    _, issues = run(extract_lines(rows))
    kinds = {(i.kind, i.field) for i in issues}
    assert ("missing_section", None) in kinds
    assert ("missing_field", "trade_payables") in kinds
