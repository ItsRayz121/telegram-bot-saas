"""Pure-logic tests for multiple submissions per member (Telegizer)."""
from types import SimpleNamespace

import pytest

from backend.engagement import EngagementError, _clean_multi_settings, submission_limits


def camp(**kw):
    base = dict(one_per_user=False, type="content", settings={})
    base.update(kw)
    return SimpleNamespace(**base)


def test_one_per_user_ignores_settings():
    assert submission_limits(camp(one_per_user=True, settings={"max_submissions": 9})) == (1, 1)


def test_raid_always_one():
    assert submission_limits(camp(type="raid")) == (1, 1)


def test_unlimited_default_and_required_clamped_to_max():
    assert submission_limits(camp()) == (1, None)
    assert submission_limits(camp(settings={"min_submissions": 5, "max_submissions": 3})) == (3, 3)
    assert submission_limits(camp(settings={"min_submissions": "x", "max_submissions": "y"})) == (1, None)


def test_clean_settings():
    out = _clean_multi_settings({"min_submissions": "", "max_submissions": "4", "keep": 1})
    assert out == {"max_submissions": 4, "keep": 1}
    with pytest.raises(EngagementError):
        _clean_multi_settings({"min_submissions": 5, "max_submissions": 2})
    with pytest.raises(EngagementError):
        _clean_multi_settings({"extra_submission_xp": "abc"})
