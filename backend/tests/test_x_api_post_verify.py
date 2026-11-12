"""verify_post: the X-API content-submission check only ever says verified on a clear match."""
from unittest.mock import patch, MagicMock
from datetime import datetime

from backend import twitter_verify as tv

URL = "https://x.com/alice/status/1234567890123"


def _resp(tweets, code=200):
    r = MagicMock(status_code=code)
    r.json.return_value = {"tweets": tweets}
    return r


def _t(author="alice", created="Tue Dec 10 07:00:30 +0000 2024"):
    return {"author": {"userName": author}, "createdAt": created}


def _run(resp, handle="@Alice", since=None):
    with patch.object(tv, "_key", return_value="k"), patch.object(tv, "_get", return_value=resp):
        return tv.verify_post(URL, handle, since=since)[0]


def test_match_verified():
    assert _run(_resp([_t()])) == "verified"


def test_other_author_failed():
    assert _run(_resp([_t("bob")])) == "failed"


def test_older_than_campaign_failed():
    assert _run(_resp([_t()]), since=datetime(2025, 1, 1)) == "failed"


def test_newer_than_campaign_verified():
    assert _run(_resp([_t()]), since=datetime(2024, 12, 1)) == "verified"


def test_errors_are_unknown_never_failed():
    assert _run(_resp([], 200)) == "unknown"
    assert _run(_resp([_t()], 500)) == "unknown"
    assert _run(_resp([_t(created="garbage")]), since=datetime(2024, 1, 1)) == "unknown"
