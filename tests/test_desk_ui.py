"""Desk UI: served from api/static, wired to the API it calls, and every server value escaped."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kadal_kural.api.main import STATIC_DIR, create_app
from kadal_kural.config import LIVE_MIC_SAMPLE_RATE, AppSettings


@pytest.fixture
def client(tmp_path: Path) -> Any:
    with TestClient(create_app(AppSettings(db_path=str(tmp_path / "ui.db")))) as test_client:
        yield test_client


def test_page_and_assets_are_served(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert f'data-mic-rate="{LIVE_MIC_SAMPLE_RATE}"' in page.text
    assert "__MIC_RATE__" not in page.text
    for asset, kind in (("/static/app.js", "javascript"), ("/static/app.css", "css")):
        response = client.get(asset)
        assert response.status_code == 200
        assert kind in response.headers["content-type"]


def test_page_references_only_existing_element_ids() -> None:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    ids = set(re.findall(r'id="([^"]+)"', html))
    used = set(re.findall(r'\$\("([^"]+)"\)', script))
    assert used, "the script looks elements up with $(id)"
    assert used <= ids, f"missing in index.html: {sorted(used - ids)}"


def test_script_calls_the_endpoints_the_server_exposes(client: TestClient) -> None:
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    routes = {getattr(r, "path", "") for r in cast(FastAPI, client.app).routes}
    for path in ("/api/v1/state", "/api/v1/ingest", "/api/v1/reset", "/ws/live-audio"):
        assert path in script and path in routes


def test_every_server_value_in_markup_is_escaped_or_formatted() -> None:
    """Transcripts are speech-to-text output; any field placed in markup must go through escapeHtml."""
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    safe_wrappers = ("escapeHtml(", "inr(", "ms(", "Math.round(", "Math.min(", "statusOf(")
    literal_choice = re.compile(r"""^[^?]+\?\s*("[^"]*"|'[^']*')\s*:\s*("[^"]*"|'[^']*')$""")  # cond ? "a" : "b"
    for expr in re.findall(r"\$\{([^}]*\b(?:d|e|b|t|msg)\.[a-z_]+[^}]*)\}", script):
        expr = expr.strip()
        safe = expr.startswith(safe_wrappers) or "escapeHtml(" in expr or literal_choice.match(expr)
        assert safe, f"unescaped: ${{{expr}}}"


def test_state_reports_whether_the_phone_line_is_on(tmp_path: Path) -> None:
    off = TestClient(create_app(AppSettings(db_path=str(tmp_path / "a.db"), phone_webhook_token="")))
    on = TestClient(create_app(AppSettings(db_path=str(tmp_path / "b.db"), phone_webhook_token="t")))
    with off, on:
        assert off.get("/api/v1/state").json()["phone_channel_enabled"] is False
        assert on.get("/api/v1/state").json()["phone_channel_enabled"] is True
