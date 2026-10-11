"""The dashboard preview (frontend/src/components/preview/previewText.js) must agree with what the bot
sends. Both sides read the same fixture: JS asserts fillTemplate == `expected`; this test asserts that
`expected` is exactly what WelcomeSystem's str.format produces, so the two cannot drift apart."""
import json
import pathlib

FIXTURE = pathlib.Path(__file__).resolve().parents[2] / "frontend/src/components/preview/fixtures/format_cases.json"


def test_fixture_matches_str_format():
    data = json.loads(FIXTURE.read_text(encoding="utf8"))
    for case in data["cases"]:
        assert case["template"].format(**data["vars"]) == case["expected"]


def test_unknown_placeholder_really_fails_in_the_bot():
    data = json.loads(FIXTURE.read_text(encoding="utf8"))
    for template in data["failing"]:
        try:
            template.format(**data["vars"])
        except KeyError:
            continue
        raise AssertionError("expected str.format to reject " + template)
