import socket

import pytest

from lulus.check import precheck
from lulus.offline import NetworkBlocked, NetworkGuard
from lulus.report import to_html, to_json
from tools.make_samples import make_demo


def test_demo_end_to_end(tmp_path):
    result = precheck(make_demo(tmp_path))
    titles = [x.title for x in result.explanations]
    assert "Total equity doesn't add up" in titles
    assert "The statutory declaration is missing" in titles
    equity = next(x for x in result.explanations if x.field == "total_equity")
    assert equity.expected == 1_284_500 and equity.source == "page 1, line 16"
    assert result.network_attempts == 0
    assert "lulus" in to_html(result) and '"errors": 2' in to_json(result)


def test_network_is_blocked_during_a_check():
    with NetworkGuard() as guard:
        with pytest.raises(NetworkBlocked):
            socket.create_connection(("example.com", 443), timeout=1)
    assert guard.attempts == 1
