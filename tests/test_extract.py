from lulus.extract import extract_lines, parse_amount


def test_parse_amount():
    assert parse_amount("1,234,567") == 1_234_567
    assert parse_amount("(1,234)") == -1_234
    assert parse_amount("RM 5,000") == 5_000
    assert parse_amount("-") == 0


def test_exact_english_and_malay_labels():
    ex = extract_lines([(1, 1, "Total assets 1,400,000"), (2, 7, "Hasil 2,000,000")])
    assert ex.values["total_assets"].value == 1_400_000
    assert ex.values["revenue"].value == 2_000_000
    assert (ex.values["revenue"].page, ex.values["revenue"].line) == (2, 7)
    assert not ex.values["total_assets"].needs_confirmation


def test_total_assets_not_confused_with_total_current_assets():
    ex = extract_lines([(1, 1, "Total current assets 400,000"), (1, 2, "Total assets 1,400,000")])
    assert ex.values["total_current_assets"].value == 400_000
    assert ex.values["total_assets"].value == 1_400_000


def test_loose_label_needs_confirmation():
    ex = extract_lines([(1, 1, "Trade receivable 150,000")])
    v = ex.values["trade_receivables"]
    assert v.value == 150_000 and v.needs_confirmation


def test_section_detection():
    ex = extract_lines([(3, 1, "STATUTORY DECLARATION")])
    assert ex.sections["statutory_declaration"] == (3, 1)
