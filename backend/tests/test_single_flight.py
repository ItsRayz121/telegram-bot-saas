"""Heavy admin sweeps must not run twice at once, and their size parameter must be clamped.

Run from the repo root:  python -m pytest backend/tests/test_single_flight.py
"""
import os
import threading

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from flask import Flask, jsonify

from backend.utils.single_flight import single_flight, clamp_sweep_limit


def test_second_concurrent_call_gets_409_and_lock_is_released():
    app = Flask(__name__)
    started, release = threading.Event(), threading.Event()

    @app.route("/sweep", methods=["POST"])
    @single_flight("t-sweep")
    def sweep():
        started.set()
        release.wait(5)
        return jsonify(ok=True)

    first = {}
    t = threading.Thread(target=lambda: first.setdefault("r", app.test_client().post("/sweep")))
    t.start()
    assert started.wait(5)
    second = app.test_client().post("/sweep")
    assert second.status_code == 409 and second.get_json()["code"] == "ALREADY_RUNNING"
    release.set()
    t.join(5)
    assert first["r"].status_code == 200
    started.clear()
    release.set()
    assert app.test_client().post("/sweep").status_code == 200   # usable again


def test_lock_is_released_when_the_job_raises():
    app = Flask(__name__)

    @app.route("/boom", methods=["POST"])
    @single_flight("t-boom")
    def boom():
        raise RuntimeError("x")

    c = app.test_client()
    assert c.post("/boom").status_code == 500
    assert c.post("/boom").status_code == 500   # 500 again, not 409


@pytest.mark.parametrize("raw,expected", [
    (None, 500), ("abc", 500), (0, 500), (-5, 500), ("25", 25), (10, 10), (10**9, 1000),
])
def test_clamp_sweep_limit(raw, expected):
    assert clamp_sweep_limit(raw) == expected
