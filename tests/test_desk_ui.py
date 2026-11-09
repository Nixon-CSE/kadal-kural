"""Desk UI: the built React app is served from api/static and talks only to real routes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kadal_kural.api.main import DESK_PAGES, STATIC_DIR, create_app
from kadal_kural.config import LIVE_MIC_SAMPLE_RATE, AppSettings

WEB_SRC = Path(__file__).resolve().parents[1] / "web" / "src"


@pytest.fixture
def client(tmp_path: Path) -> Any:
    with TestClient(create_app(AppSettings(db_path=str(tmp_path / "ui.db")))) as test_client:
        yield test_client


def _bundle_paths(html: str) -> list[str]:
    return re.findall(r'(?:src|href)="(/static/assets/[^"]+)"', html)


def test_page_injects_the_mic_rate(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert f'data-mic-rate="{LIVE_MIC_SAMPLE_RATE}"' in page.text
    assert "__MIC_RATE__" not in page.text
    assert '<div id="root">' in page.text


def test_every_built_asset_the_page_references_is_served(client: TestClient) -> None:
    paths = _bundle_paths(client.get("/").text)
    assert any(p.endswith(".js") for p in paths) and any(p.endswith(".css") for p in paths)
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path


def test_bundle_calls_only_routes_the_server_exposes(client: TestClient) -> None:
    bundle = "".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in (STATIC_DIR / "assets").glob("*.js")
    )
    routes = {getattr(r, "path", "") for r in cast(FastAPI, client.app).routes}
    for path in ("/api/v1/state", "/api/v1/ingest", "/api/v1/reset", "/ws/live-audio"):
        assert path in bundle and path in routes


def test_source_never_injects_raw_html() -> None:
    """Transcripts are speech-to-text output; React escapes them unless raw HTML is injected."""
    if not WEB_SRC.exists():
        pytest.skip("web/ source not present (installed package)")
    offenders = [str(p) for p in WEB_SRC.rglob("*.tsx") if "dangerouslySetInnerHTML" in p.read_text(encoding="utf-8")]
    assert offenders == []


def test_state_reports_whether_the_phone_line_is_on(tmp_path: Path) -> None:
    off = TestClient(create_app(AppSettings(db_path=str(tmp_path / "a.db"), phone_webhook_token="")))
    on = TestClient(create_app(AppSettings(db_path=str(tmp_path / "b.db"), phone_webhook_token="t")))
    with off, on:
        assert off.get("/api/v1/state").json()["phone_channel_enabled"] is False
        assert on.get("/api/v1/state").json()["phone_channel_enabled"] is True


@pytest.mark.parametrize("path", DESK_PAGES)
def test_every_desk_page_url_serves_the_app(client: TestClient, path: str) -> None:
    page = client.get(path)
    assert page.status_code == 200 and '<div id="root">' in page.text


def test_unknown_paths_are_still_404(client: TestClient) -> None:
    assert client.get("/no-such-page").status_code == 404
    assert client.get("/api/v1/nope").status_code == 404


def test_desk_pages_are_not_reachable_through_the_public_tunnel(client: TestClient) -> None:
    assert client.get("/ledger", headers={"Cf-Connecting-Ip": "203.0.113.7"}).status_code == 403
