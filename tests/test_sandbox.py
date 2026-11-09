"""Game sandbox: the real firewall on an isolated ledger, and the story-mode orders it must decide."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List

import pytest
from fastapi.testclient import TestClient

from kadal_kural.api.main import create_app
from kadal_kural.config import AppSettings

# The five orders of story mode, in order, and what the firewall must decide for each.
# web/src/game/data.ts narrates these outcomes; this test keeps the two in step.
STORY = [
    ("குமரனுக்கு 20 கிலோ டைகர் பிரான் 500 ரேட்டு", "BOOKED"),
    ("செந்திலுக்கு 40 கிலோ வஞ்சரம் 740 ரேட்டு", "CREDIT_HOLD_BREACH"),
    ("குமரனுக்கு 20 கிலோ டைகர் பிரான் 60 ரேட்டு", "PENDING_CLARIFICATION"),
    ("புது கடைக்கு 30 கிலோ வஞ்சரம் 500 ரேட்டு", "PENDING_CLARIFICATION"),
    ("செந்திலுக்கு 10 கிலோ வஞ்சரம் 700 ரேட்டு", "BOOKED"),
]


@pytest.fixture
def client(tmp_path: Path) -> Any:
    with TestClient(create_app(AppSettings(db_path=str(tmp_path / "real.db")))) as test_client:
        yield test_client


def _statuses(client: TestClient, transcript: str) -> List[str]:
    response = client.post("/api/v1/sandbox/evaluate", json={"transcript": transcript})
    assert response.status_code == 200
    return [d["status"] for d in response.json()["decisions"]]


def test_story_orders_get_the_decisions_the_game_narrates(client: TestClient) -> None:
    client.post("/api/v1/sandbox/reset")
    assert [_statuses(client, t) for t, _ in STORY] == [[s] for _, s in STORY]


def test_sandbox_never_touches_the_real_ledger(client: TestClient) -> None:
    before = client.get("/api/v1/state").json()
    _statuses(client, STORY[0][0])
    after = client.get("/api/v1/state").json()
    assert after["events"] == before["events"] == []
    assert after["buyers"] == before["buyers"]


def test_sandbox_balances_move_and_reset_restores_them(client: TestClient) -> None:
    opening = client.post("/api/v1/sandbox/reset").json()["buyers"]
    moved = client.post("/api/v1/sandbox/evaluate", json={"transcript": STORY[0][0]}).json()["buyers"]
    kumaran = lambda bs: next(b for b in bs if b["canonical_name"] == "Kumaran Stores")["running_balance_inr"]  # noqa: E731
    assert kumaran(moved) == kumaran(opening) + 10_000
    assert kumaran(client.post("/api/v1/sandbox/reset").json()["buyers"]) == kumaran(opening)


def test_sandbox_rejects_oversized_input(client: TestClient) -> None:
    assert client.post("/api/v1/sandbox/evaluate", json={"transcript": "x" * 401}).status_code == 422


def test_sandbox_is_not_public(client: TestClient) -> None:
    proxied = {"Cf-Connecting-Ip": "203.0.113.7"}
    assert client.post("/api/v1/sandbox/evaluate", json={"transcript": STORY[0][0]}, headers=proxied).status_code == 403
