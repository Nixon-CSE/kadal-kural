"""Phone channel (/api/v1/phone-turn): Gnani Agent Builder forwards caller turns to the same firewall."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from kadal_kural.api.main import create_app, parse_phone_fields
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


def _assert_asks_again_and_writes_nothing(client: TestClient, response: Any) -> None:
    assert response.status_code == 200
    body = response.json()
    assert body["transcript_received"] is False
    assert body["reply_text"] == CLARIFICATION_PROMPT_TAMIL
    assert body["statuses"] == [] and body["booked_count"] == 0
    assert client.get("/api/v1/state").json()["events"] == []


@pytest.mark.parametrize(
    "body",
    [{"transcript": ""}, {"transcript": "{{user_text}}"}, {"user_text": " {{ user_text }} "}, {}],
    ids=["empty", "unfilled-template", "unfilled-template-spaced", "no-field"],
)
def test_unusable_transcript_asks_again(client: TestClient, body: Dict[str, Any]) -> None:
    _assert_asks_again_and_writes_nothing(client, _turn(client, body))


def test_request_with_no_body_asks_again(client: TestClient) -> None:
    """Gnani's 'Test API Request' button sent a POST with no body at all."""
    response = client.post("/api/v1/phone-turn", headers={PHONE_TOKEN_HEADER: TOKEN})
    _assert_asks_again_and_writes_nothing(client, response)


def test_token_is_checked_before_the_body(client: TestClient) -> None:
    assert client.post("/api/v1/phone-turn").status_code == 401


def test_form_encoded_body_is_accepted(client: TestClient) -> None:
    response = client.post(
        "/api/v1/phone-turn", data={"user_text": BOOKABLE}, headers={PHONE_TOKEN_HEADER: TOKEN}
    )
    assert response.status_code == 200 and response.json()["booked_count"] == 1


def test_query_parameters_are_accepted(client: TestClient) -> None:
    response = client.post(
        "/api/v1/phone-turn", params={"transcript": BOOKABLE}, headers={PHONE_TOKEN_HEADER: TOKEN}
    )
    assert response.status_code == 200 and response.json()["booked_count"] == 1


def test_plain_text_body_is_the_transcript(client: TestClient) -> None:
    response = client.post(
        "/api/v1/phone-turn",
        content=BOOKABLE.encode("utf-8"),
        headers={PHONE_TOKEN_HEADER: TOKEN, "Content-Type": "text/plain; charset=utf-8"},
    )
    assert response.status_code == 200 and response.json()["booked_count"] == 1


def test_json_body_without_content_type_is_accepted(client: TestClient) -> None:
    response = client.post(
        "/api/v1/phone-turn",
        content=json.dumps({"transcript": BOOKABLE}).encode("utf-8"),
        headers={PHONE_TOKEN_HEADER: TOKEN, "Content-Type": ""},
    )
    assert response.status_code == 200 and response.json()["booked_count"] == 1


@pytest.mark.parametrize(
    "content_type,raw,query,expected",
    [
        ("application/json", b'{"transcript": "x y", "n": 3, "nested": {"a": 1}}', {}, {"transcript": "x y", "n": "3"}),
        ("application/json", b'"just text"', {}, {"transcript": "just text"}),
        ("application/x-www-form-urlencoded", "user_text=அ+ஆ".encode(), {}, {"user_text": "அ ஆ"}),
        ("text/plain", "குமரன்".encode(), {"conversation_id": "c1"}, {"transcript": "குமரன்", "conversation_id": "c1"}),
        ("application/json", b"not json", {"text": "q"}, {"text": "q"}),
        ("", b"", {}, {}),
    ],
    ids=["json", "json-string", "form", "plain-text-and-query", "broken-json", "empty"],
)
def test_parse_phone_fields(content_type: str, raw: bytes, query: Dict[str, str], expected: Dict[str, str]) -> None:
    assert parse_phone_fields(content_type, raw, query) == expected


def test_transcript_sent_as_a_header_is_accepted(client: TestClient) -> None:
    """A console that puts the field under Headers instead of Body (UTF-8 Tamil in a header)."""
    response = client.post(
        "/api/v1/phone-turn",
        headers=[(PHONE_TOKEN_HEADER.encode(), TOKEN.encode()), (b"transcript", BOOKABLE.encode("utf-8"))],
        json={},
    )
    assert response.status_code == 200 and response.json()["booked_count"] == 1


def test_body_wins_over_header(client: TestClient) -> None:
    response = client.post(
        "/api/v1/phone-turn",
        headers=[(PHONE_TOKEN_HEADER.encode(), TOKEN.encode()), (b"x-transcript", b"garbage words")],
        json={"transcript": BOOKABLE},
    )
    assert response.json()["booked_count"] == 1


def test_phone_header_fields_never_include_secrets() -> None:
    from kadal_kural.api.main import phone_header_fields

    found = phone_header_fields([("X-Kadal-Token", "secret"), ("Authorization", "Bearer s"), ("X-Text", "hi")])
    assert found == {"text": "hi"}
