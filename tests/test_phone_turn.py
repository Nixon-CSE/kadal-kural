"""Phone channel (/api/v1/phone-turn): Gnani Agent Builder forwards caller turns to the same firewall."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from kadal_kural.api.main import create_app
from kadal_kural.config import CLARIFICATION_PROMPT_TAMIL, PHONE_TOKEN_HEADER, AppSettings
from kadal_kural.domain.models import LedgerEventStatus

TOKEN = "test-phone-token"
BOOKABLE = "குமரனுக்கு 20 கிலோ டைகர் பிரான் 500 ரேட்டு"
OVER_LIMIT = "செந்திலுக்கு 40 கிலோ வஞ்சரம் 740 ரேட்டு"
UNKNOWN_BUYER = "புது கடைக்கு 30 கிலோ வஞ்சரம் 500 ரேட்டு"


def _client(tmp_path: Path, token: str = TOKEN) -> TestClient:
    return TestClient(create_app(AppSettings(db_path=str(tmp_path / "phone.db"), phone_webhook_token=token)))


@pytest.fixture
def client(tmp_path: Path) -> Any:
    with _client(tmp_path) as test_client:
        yield test_client


def _turn(client: TestClient, body: Dict[str, Any], **headers: str) -> Any:
    return client.post("/api/v1/phone-turn", json=body, headers=headers or {PHONE_TOKEN_HEADER: TOKEN})


def test_bookable_trade_is_booked_and_reply_is_the_firewall_reply(client: TestClient) -> None:
    response = _turn(client, {"transcript": BOOKABLE, "conversation_id": "conv-1"})
    assert response.status_code == 200
    body = response.json()
    assert body["statuses"] == [LedgerEventStatus.BOOKED.value]
    assert body["booked_count"] == 1 and body["held_count"] == 0
    assert body["conversation_id"] == "conv-1"
    assert body["reply_text"]

    (event,) = client.get("/api/v1/state").json()["events"]
    assert event["status"] == LedgerEventStatus.BOOKED.value
    assert event["raw_utterance"] == BOOKABLE
    assert event["trade_value_inr"] == 10_000


def test_platform_placeholder_name_user_text_is_accepted(client: TestClient) -> None:
    response = _turn(client, {"user_text": BOOKABLE})
    assert response.status_code == 200
    assert response.json()["booked_count"] == 1


def test_credit_breach_is_held_not_booked(client: TestClient) -> None:
    body = _turn(client, {"transcript": OVER_LIMIT}).json()
    assert body["booked_count"] == 0 and body["held_count"] == 1
    assert body["statuses"] != [LedgerEventStatus.BOOKED.value]


def test_unknown_buyer_goes_to_clarification(client: TestClient) -> None:
    body = _turn(client, {"transcript": UNKNOWN_BUYER}).json()
    assert body["statuses"] == [LedgerEventStatus.PENDING_CLARIFICATION.value]
    assert body["reply_text"]


def test_turn_with_no_trade_still_gets_a_spoken_reply(client: TestClient) -> None:
    body = _turn(client, {"transcript": "ஹலோ யாரு பேசறது"}).json()
    assert body["statuses"] == []
    assert body["reply_text"] == CLARIFICATION_PROMPT_TAMIL


@pytest.mark.parametrize(
    "headers",
    [{}, {PHONE_TOKEN_HEADER: "wrong"}, {"Authorization": "Bearer wrong"}],
    ids=["missing", "wrong-header", "wrong-bearer"],
)
def test_rejects_requests_without_the_shared_token(client: TestClient, headers: Dict[str, str]) -> None:
    response = client.post("/api/v1/phone-turn", json={"transcript": BOOKABLE}, headers=headers)
    assert response.status_code == 401
    assert client.get("/api/v1/state").json()["events"] == []  # nothing written


def test_bearer_token_is_accepted(client: TestClient) -> None:
    response = client.post(
        "/api/v1/phone-turn", json={"transcript": BOOKABLE}, headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 200


def test_endpoint_is_disabled_when_no_token_is_configured(tmp_path: Path) -> None:
    with _client(tmp_path, token="") as client:
        response = client.post("/api/v1/phone-turn", json={"transcript": BOOKABLE})
    assert response.status_code == 503


def test_rejects_empty_transcript(client: TestClient) -> None:
    assert _turn(client, {"transcript": ""}).status_code == 422
