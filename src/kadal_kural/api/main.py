"""
Production FastAPI Gateway for Kadal Kural.
Exposes:
- Full-duplex WebSocket (/ws/live-audio) bridging Browser WebAudio 8kHz PCM <-> Gnani Prisma v2.5 & Timbre v2.5
- Real WAV file streaming endpoint (/api/v1/upload-wav)
- REST state & deterministic ingest endpoints (/api/v1/state, /api/v1/ingest)
- Phone channel for Gnani Agent Builder (/api/v1/phone-turn)
- Desk UI (/ and /static: index.html, app.css, app.js)
"""

from __future__ import annotations

import asyncio
import base64
import hmac
import io
import json
import logging
import re
import tempfile
import time
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterable, List, Mapping, Optional, Tuple
from urllib.parse import parse_qs

import websockets
from fastapi import (
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from websockets.exceptions import ConnectionClosed

from kadal_kural.api.edge import PublicEdgeGuard
from kadal_kural.api.security import (
    LocalOriginGuard,
    RequestSizeLimit,
    SecurityHeaders,
    SlidingWindowRateLimiter,
    client_address,
)
from kadal_kural.config import (
    ASSEMBLER_AWAITING_RATE_WINDOW_SEC,
    ASSEMBLER_INCOMPLETE_WINDOW_SEC,
    CLARIFICATION_PROMPT_TAMIL,
    LIVE_MIC_SAMPLE_RATE,
    PHONE_TOKEN_HEADER,
    TIMING_LOGGER_NAME,
    TIMING_PATH_INGEST,
    TIMING_PATH_LIVE_WS,
    TIMING_PATH_PHONE_AGENT,
    TIMING_PATH_UPLOAD_WAV,
    WS_PING_INTERVAL_SEC,
    AppSettings,
)
from kadal_kural.domain.calls import DEFAULT_CALL_GAP_SECONDS, group_phone_calls
from kadal_kural.domain.matcher import BilingualCatalogMatcher
from kadal_kural.domain.models import EntrySource, LedgerEventStatus, OrderChannel
from kadal_kural.domain.service import PreDispatchCreditFirewallService
from kadal_kural.infrastructure.gnani_client import (
    AssembledUtterance,
    GnaniArthaSpeechClient,
    GnaniConfigurationError,
    MultiSegmentTradeAssembler,
    PCM1024RingBufferPacer,
)
from kadal_kural.infrastructure.mic_capture import MicCaptureRecorder
from kadal_kural.infrastructure.persistence import AppendOnlyLedgerRepository
from kadal_kural.infrastructure.voice_turn import VoiceTurn, run_voice_turn

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
DESK_PAGES = ("/play", "/desk", "/ledger", "/buyers", "/insights", "/phone")


def _enable_timing_log() -> None:
    """
    Makes the per-utterance JSON timing lines reach a log. Under uvicorn the root logger has
    no handlers, so INFO records would be dropped; in that case the timing logger gets its own
    stderr handler that writes each record's message (one JSON object) as one line.
    """
    for name, fmt in ((TIMING_LOGGER_NAME, "%(message)s"), (PHONE_LOGGER_NAME, "PHONE %(message)s")):
        named = logging.getLogger(name)
        named.setLevel(logging.INFO)
        if not named.handlers and not logging.getLogger().handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(fmt))
            named.addHandler(handler)


def _decision_items(turn: VoiceTurn) -> List[Dict[str, Any]]:
    """Serializes each decision with its spoken reply (TTFB and WAV) when one was synthesized."""
    items: List[Dict[str, Any]] = []
    for decision, reply in zip(turn.evaluation.decisions, turn.replies, strict=True):
        item = decision.model_dump()
        if reply is not None:
            item["timbre_ttfb_ms"] = reply.ttfb_ms
            item["audio_wav_b64"] = base64.b64encode(reply.audio_wav_bytes).decode("ascii")
        items.append(item)
    if turn.prompt_reply is not None:  # nothing parsed: shown and played like a clarification
        items.append(
            {
                "status": LedgerEventStatus.PENDING_CLARIFICATION.value,
                "tts_response_tamil": CLARIFICATION_PROMPT_TAMIL,
                "timbre_ttfb_ms": turn.prompt_reply.ttfb_ms,
                "audio_wav_b64": base64.b64encode(turn.prompt_reply.audio_wav_bytes).decode("ascii"),
            }
        )
    return items


# Longest transcript accepted from any channel: a few orders in one breath fit in a fraction of it.
MAX_TRANSCRIPT_CHARS = 500
# Largest live-audio frame accepted from the browser (it sends 512-sample, 1 KB frames).
MAX_LIVE_FRAME_BYTES = 64 * 1024


class UtteranceIngestRequest(BaseModel):
    transcript: str = Field(..., min_length=2, max_length=MAX_TRANSCRIPT_CHARS)
    stt_latency_ms: float = Field(default=0.0, ge=0.0)  # only a caller-measured STT figure; no STT runs here
    synthesize_tts: bool = Field(default=True)


PHONE_TRANSCRIPT_KEYS = ("transcript", "user_text", "text")
# Field names an agent platform may use for the call it is forwarding, checked in this order.
PHONE_CALL_ID_KEYS = ("conversation_id", "call_id", "session_id", "callsid", "call_sid")
_CALL_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_UNFILLED_TEMPLATE = re.compile(r"^\s*\{\{.*\}\}\s*$")
PHONE_LOGGER_NAME = "kadal_kural.phone"
phone_logger = logging.getLogger(PHONE_LOGGER_NAME)


def parse_phone_fields(content_type: str, raw_body: bytes, query: Mapping[str, str]) -> Dict[str, str]:
    """
    Fields of one phone turn, however the agent platform sent them: a JSON object, a JSON string,
    form-urlencoded fields, a plain-text body, or query parameters (body wins over query).
    Platforms differ and some test consoles send no body at all, so this never raises.
    """
    fields: Dict[str, str] = {}
    text = raw_body.decode("utf-8", errors="replace").strip() if raw_body else ""
    ctype = content_type.split(";")[0].strip().lower()
    if text:
        parsed: Any = None
        if ctype == "application/x-www-form-urlencoded":
            parsed = {k: v[-1] for k, v in parse_qs(text, keep_blank_values=True).items()}
        else:
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = text if ctype in ("", "text/plain") else None
        if isinstance(parsed, dict):
            fields.update({str(k): str(v) for k, v in parsed.items() if v is not None and not isinstance(v, (dict, list))})
        elif isinstance(parsed, str):
            fields["transcript"] = parsed
    for key, value in query.items():
        fields.setdefault(key, value)
    return fields


_SECRET_HEADERS = frozenset({PHONE_TOKEN_HEADER.lower(), "authorization", "cookie"})


def phone_header_fields(headers: Iterable[Tuple[str, str]]) -> Dict[str, str]:
    """
    Transcript fields sent as HTTP headers (``transcript``, ``user_text``, ``text``, or with an
    ``x-`` prefix). Header values reach us as latin-1; UTF-8 text (Tamil) is restored from it.
    """
    found: Dict[str, str] = {}
    for name, value in headers:
        key = name.lower()
        key = key[2:] if key.startswith("x-") else key
        if key in PHONE_TRANSCRIPT_KEYS and key not in found:
            try:
                found[key] = value.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                found[key] = value
    return found


def phone_transcript(fields: Mapping[str, str]) -> Optional[str]:
    """The caller's words, or None when absent, too short, or an unfilled ``{{placeholder}}``."""
    for key in PHONE_TRANSCRIPT_KEYS:
        value = (fields.get(key) or "").strip()
        if len(value) >= 2 and not _UNFILLED_TEMPLATE.match(value):
            return value
    return None


def phone_call_id(fields: Mapping[str, str]) -> Optional[str]:
    """The call this turn belongs to, if the agent sent a plain id (an unfilled template is ignored)."""
    lowered = {k.lower(): v for k, v in fields.items()}
    for key in PHONE_CALL_ID_KEYS:
        value = (lowered.get(key) or "").strip()
        if value and _CALL_ID.match(value):
            return value
    return None


# Buyer fields the browser never needs; contact details stay on the server.
_PRIVATE_BUYER_FIELDS = frozenset({"phone_e164"})


def public_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    buyers = [{k: v for k, v in b.items() if k not in _PRIVATE_BUYER_FIELDS} for b in snapshot["buyers"]]
    return {**snapshot, "buyers": buyers}


class SandboxRequest(BaseModel):
    transcript: str = Field(..., min_length=2, max_length=400)


class PhoneTurnResponse(BaseModel):
    """What the agent speaks (``reply_text``) plus a compact, machine-readable summary."""

    reply_text: str
    booked_count: int
    held_count: int
    statuses: List[str]
    conversation_id: Optional[str] = None
    transcript_received: bool = True  # False: nothing usable arrived, so the reply asks to repeat


def phone_reply_text(turn: VoiceTurn) -> str:
    """Every turn answers: each decision's Tamil reply in order, or the clarification prompt."""
    replies = [d.tts_response_tamil for d in turn.evaluation.decisions if d.tts_response_tamil]
    return " ".join(replies) if replies else CLARIFICATION_PROMPT_TAMIL


def create_app(settings: Optional[AppSettings] = None) -> FastAPI:
    cfg = settings or AppSettings()
    _enable_timing_log()
    matcher = BilingualCatalogMatcher(cfg.catalog_path, cfg.assumed_unit_confidence)
    repo = AppendOnlyLedgerRepository(cfg.db_path, list(matcher.buyers.values()))
    firewall = PreDispatchCreditFirewallService(cfg, matcher, repo)
    speech_client = GnaniArthaSpeechClient(cfg)
    # Sandbox for the guided game: the same deterministic firewall on its own throwaway ledger,
    # so play never touches real balances. Requests are serialised; the state is shared.
    sandbox_repo = AppendOnlyLedgerRepository(
        str(Path(tempfile.mkdtemp(prefix="kadal-sandbox-")) / "sandbox.db"), list(matcher.buyers.values())
    )
    sandbox = PreDispatchCreditFirewallService(cfg, matcher, sandbox_repo)
    sandbox_lock = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = cfg
        app.state.firewall = firewall
        app.state.speech_client = speech_client
        yield

    app = FastAPI(
        title="Kadal Kural — B2B Pre-Dispatch Credit Firewall",
        version="1.0.0",
        lifespan=lifespan,
    )
    # Outermost last: security headers on every response, then the tunnel's path allow-list, then the
    # local browser checks (Host, cross-site), then body size limits closest to the routes.
    app.add_middleware(
        RequestSizeLimit,
        limits={"/api/v1/phone-turn": cfg.max_phone_body_bytes, "/api/v1/upload-wav": cfg.max_upload_bytes},
    )
    app.add_middleware(LocalOriginGuard, extra_hosts=cfg.allowed_hosts.split(","))
    if cfg.public_edge_guard:
        app.add_middleware(PublicEdgeGuard)
    app.add_middleware(SecurityHeaders)
    phone_limiter = SlidingWindowRateLimiter(cfg.phone_rate_limit_per_minute)

    @app.get("/healthz")
    async def healthcheck() -> Dict[str, Any]:
        has_key = bool(cfg.gnani_api_key and cfg.gnani_api_key != "your_gnani_api_key_here")
        return {
            "status": "ok",
            "domain": matcher.domain_id,
            "gnani_live_key_configured": has_key,
        }

    @app.get("/api/v1/state")
    async def get_dashboard_state() -> Dict[str, Any]:
        has_key = bool(cfg.gnani_api_key and cfg.gnani_api_key != "your_gnani_api_key_here")
        return {
            "domain_title": matcher.domain_title,
            "confidence_threshold": cfg.confidence_threshold,
            "gnani_live_key_configured": has_key,
            "phone_channel_enabled": bool(cfg.phone_webhook_token),
            **public_snapshot(repo.fetch_dashboard_snapshot()),
        }

    @app.get("/api/v1/calls")
    async def get_phone_calls(limit: int = Query(default=20, ge=1, le=100)) -> Dict[str, Any]:
        """
        The phone line's call log: phone-channel ledger entries grouped into calls, newest first.
        Grouped by the agent's call id when it sends one, else by gaps of more than five minutes.
        """
        entries = repo.fetch_channel_events(OrderChannel.PHONE)
        calls = [c.to_dict() for c in group_phone_calls(entries)]
        return {
            "phone_channel_enabled": bool(cfg.phone_webhook_token),
            "gap_seconds": DEFAULT_CALL_GAP_SECONDS,
            "summary": {
                "calls": len(calls),
                "entries": len(entries),
                "booked_value_inr": sum(c["booked_value_inr"] for c in calls),
            },
            "calls": calls[:limit],
        }

    @app.post("/api/v1/ingest")
    async def ingest_utterance(payload: UtteranceIngestRequest) -> Dict[str, Any]:
        has_key = bool(cfg.gnani_api_key and cfg.gnani_api_key != "your_gnani_api_key_here")
        turn = await run_voice_turn(
            firewall,
            speech_client,
            payload.transcript,
            path=TIMING_PATH_INGEST,
            decision_stt_latency_ms=payload.stt_latency_ms,
            synthesize=payload.synthesize_tts and has_key,
            source=EntrySource(channel=OrderChannel.TYPED),
        )
        return {
            "decisions": _decision_items(turn),
            "snapshot": public_snapshot(repo.fetch_dashboard_snapshot()),
        }

    def _require_phone_token(x_kadal_token: Optional[str], authorization: Optional[str]) -> None:
        expected = cfg.phone_webhook_token
        if not expected:
            raise HTTPException(status_code=503, detail="Phone channel is not configured")
        presented = x_kadal_token or ""
        if not presented and authorization and authorization.lower().startswith("bearer "):
            presented = authorization[len("bearer "):].strip()
        if not hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8")):
            raise HTTPException(status_code=401, detail="Invalid or missing phone channel token")

    @app.post("/api/v1/phone-turn", response_model=PhoneTurnResponse)
    async def phone_turn(
        request: Request,
        x_kadal_token: Optional[str] = Header(default=None, alias=PHONE_TOKEN_HEADER),
        authorization: Optional[str] = Header(default=None),
    ) -> PhoneTurnResponse:
        """
        Phone channel. Gnani Agent Builder handles the call (dialling, STT, TTS) and forwards
        each caller turn here; the same deterministic firewall books, holds or asks to repeat,
        and the agent speaks ``reply_text``. No Timbre synthesis runs here: the agent speaks.

        The token is checked before the body is read. The transcript may arrive as JSON, form
        fields or query parameters under ``transcript``, ``user_text`` or ``text``. A turn with
        no usable transcript still gets a 200 and the clarification prompt, and writes nothing.
        """
        retry_after = phone_limiter.check(client_address(request.scope))
        if retry_after is not None:  # checked before the token, so guessing it is rate limited too
            raise HTTPException(
                status_code=429, detail="Too many phone requests", headers={"Retry-After": str(int(retry_after) + 1)}
            )
        _require_phone_token(x_kadal_token, authorization)
        content_type = request.headers.get("content-type", "")
        raw = await request.body()
        if content_type.lower().startswith("multipart/form-data"):
            form = await request.form()
            fields = {k: v for k, v in form.items() if isinstance(v, str)}
            fields.update({k: v for k, v in request.query_params.items() if k not in fields})
        else:
            fields = parse_phone_fields(content_type, raw, request.query_params)
        header_fields = phone_header_fields(request.headers.items())
        for key, value in header_fields.items():
            fields.setdefault(key, value)  # a console that puts the field under Headers still works
        transcript = phone_transcript(fields)
        call_id = phone_call_id(fields)
        conversation_id = call_id
        phone_logger.info(
            "phone turn received: content_type=%s body_bytes=%d fields=%s from_headers=%s header_names=%s transcript=%s",
            content_type or "-", len(raw), sorted(fields), sorted(header_fields),
            sorted(k.lower() for k in request.headers if k.lower() not in _SECRET_HEADERS),
            "yes" if transcript else "MISSING",
        )
        if transcript is not None and len(transcript) > MAX_TRANSCRIPT_CHARS:
            raise HTTPException(status_code=422, detail=f"Transcript longer than {MAX_TRANSCRIPT_CHARS} characters")
        if transcript is None:
            return PhoneTurnResponse(
                reply_text=CLARIFICATION_PROMPT_TAMIL, booked_count=0, held_count=0, statuses=[],
                conversation_id=conversation_id, transcript_received=False,
            )
        turn = await run_voice_turn(
            firewall, speech_client, transcript, path=TIMING_PATH_PHONE_AGENT, synthesize=False,
            source=EntrySource(channel=OrderChannel.PHONE, call_id=call_id),
        )
        statuses = [d.status.value for d in turn.evaluation.decisions]
        booked = {LedgerEventStatus.BOOKED.value, LedgerEventStatus.BOOKED_AFTER_BARGE_IN.value}
        phone_logger.info("phone turn decided: conversation=%s statuses=%s", conversation_id or "-", ",".join(statuses) or "none")
        return PhoneTurnResponse(
            reply_text=phone_reply_text(turn),
            booked_count=sum(s in booked for s in statuses),
            held_count=sum(s not in booked for s in statuses),
            statuses=statuses,
            conversation_id=conversation_id,
        )

    @app.post("/api/v1/upload-wav")
    async def upload_and_stream_wav(file: UploadFile = File(...)) -> Dict[str, Any]:
        """
        Accepts a real 16-bit mono WAV file (8kHz or 16kHz), streams it in 1,024-byte
        paced frames to Gnani Prisma v2.5, runs the Credit Firewall, and synthesizes
        spoken Tamil responses via Gnani Timbre v2.5.
        """
        raw_bytes = await file.read()
        try:
            with wave.open(io.BytesIO(raw_bytes), "rb") as wf:
                sample_rate = wf.getframerate()
                channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                pcm_bytes = wf.readframes(wf.getnframes())
        except wave.Error as exc:
            raise HTTPException(status_code=400, detail=f"Invalid WAV file: {exc}") from exc

        if channels != 1 or sampwidth != 2 or sample_rate not in (8000, 16000):
            raise HTTPException(
                status_code=400,
                detail="WAV must be 16-bit mono PCM at 8000 Hz or 16000 Hz.",
            )

        segments: list[str] = []
        latencies: list[float] = []
        received_ns: list[int] = []

        async def _collect_segment(text: str, lat_ms: float) -> None:
            if text.strip():
                received_ns.append(time.perf_counter_ns())
                segments.append(text.strip())
                latencies.append(lat_ms)

        try:
            await speech_client.stream_pcm_to_prisma_v25(
                pcm_bytes,
                _collect_segment,
                sample_rate=sample_rate,
                lang_code="ta-IN",
                enable_boosting=True,
            )
        except GnaniConfigurationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        merged_transcript = " ".join(segments)
        mean_lat = round(sum(latencies) / max(1, len(latencies)), 1)
        if not merged_transcript:
            return {
                "merged_transcript": "",
                "decisions": [],
                "snapshot": public_snapshot(repo.fetch_dashboard_snapshot()),
            }

        turn = await run_voice_turn(
            firewall,
            speech_client,
            merged_transcript,
            path=TIMING_PATH_UPLOAD_WAV,
            stt_latencies_ms=latencies,
            first_segment_ns=received_ns[0],
            segment_received_ns=received_ns,
            source=EntrySource(channel=OrderChannel.AUDIO_FILE),
        )

        return {
            "merged_transcript": merged_transcript,
            "stt_latency_ms": mean_lat,
            "decisions": _decision_items(turn),
            "snapshot": public_snapshot(repo.fetch_dashboard_snapshot()),
        }

    @app.websocket("/ws/live-audio")
    async def live_audio_websocket(client_ws: WebSocket) -> None:
        """
        Full-duplex live audio bridge:
        Browser Mic (8kHz 16-bit PCM) -> 1,024-byte RingBuffer -> Gnani Prisma v2.5 WS
        -> TradeAssembler (commits complete trades at once) -> Credit Firewall -> Gnani Timbre v2.5 WS -> Browser Speaker.
        """
        await client_ws.accept()
        if not cfg.gnani_api_key or cfg.gnani_api_key == "your_gnani_api_key_here":
            await client_ws.send_json(
                {
                    "type": "error",
                    "message": "KADAL_GNANI_API_KEY is not set in .env. Add your Gnani API key and restart uvicorn.",
                }
            )
            await client_ws.close()
            return

        pacer = PCM1024RingBufferPacer()
        capture = (
            MicCaptureRecorder(Path(cfg.mic_capture_dir), LIVE_MIC_SAMPLE_RATE) if cfg.mic_capture_dir else None
        )
        if capture is not None:
            logger.info("Capturing raw mic audio to %s", capture.wav_path)
        prisma_headers = {
            "x-api-key-id": cfg.gnani_api_key,
            "lang_code": "ta-IN",
            "x-sample-rate": str(LIVE_MIC_SAMPLE_RATE),
            "x-format": "transcribe",
            "x-vad-threshold": str(cfg.vad_threshold),
            "x-min-speech-ms": str(cfg.min_speech_ms),
            "x-min-silence-ms": str(cfg.min_silence_ms),
            "x-enable-substitution": "true",
        }

        async def _on_assembled_utterance(utterance: AssembledUtterance) -> None:
            turn = await run_voice_turn(
                firewall,
                speech_client,
                utterance.text,
                path=TIMING_PATH_LIVE_WS,
                stt_latencies_ms=utterance.segment_latencies_ms,
                first_segment_ns=utterance.first_segment_ns,
                segment_received_ns=utterance.segment_received_ns,
                source=EntrySource(channel=OrderChannel.DESK_VOICE),
            )
            await client_ws.send_json(
                {
                    "type": "credit_decisions",
                    "assembled_transcript": utterance.text,
                    "stt_latency_ms": utterance.mean_stt_latency_ms,
                    "decisions": _decision_items(turn),
                    "snapshot": public_snapshot(repo.fetch_dashboard_snapshot()),
                }
            )

        assembler = MultiSegmentTradeAssembler(
            window_sec=ASSEMBLER_INCOMPLETE_WINDOW_SEC,
            on_commit=_on_assembled_utterance,
            is_complete=matcher.is_complete_utterance,
            awaits_rate=matcher.awaits_rate,
            awaiting_rate_window_sec=ASSEMBLER_AWAITING_RATE_WINDOW_SEC,
        )

        try:
            async with websockets.connect(
                cfg.prisma_ws_url,
                additional_headers=prisma_headers,
                ping_interval=WS_PING_INTERVAL_SEC,
            ) as prisma_ws:
                handshake = json.loads(await prisma_ws.recv())
                await prisma_ws.send(speech_client.build_runtime_settings_frame())
                await client_ws.send_json(
                    {
                        "type": "prisma_connected",
                        "session_id": handshake.get("id", "live"),
                    }
                )

                async def _prisma_to_client() -> None:
                    try:
                        async for raw_msg in prisma_ws:
                            received_ns = time.perf_counter_ns()
                            evt = json.loads(raw_msg)
                            if evt.get("type") == "transcript":
                                seg_text = str(evt.get("text", "")).strip()
                                seg_lat = float(evt.get("latency", 0.0))
                                if seg_text:
                                    if capture is not None:
                                        capture.mark_segment(seg_text, seg_lat)
                                    # Tell the browser to flush any playing TTS (Barge-In) before anything else
                                    speech_client.trigger_barge_in_abort()
                                    await client_ws.send_json(
                                        {
                                            "type": "barge_in_and_segment",
                                            "segment_text": seg_text,
                                            "stt_latency_ms": seg_lat,
                                        }
                                    )
                                    await assembler.ingest_segment(seg_text, seg_lat, received_ns)
                    except ConnectionClosed:
                        return

                prisma_recv_task = asyncio.create_task(_prisma_to_client())
                session_deadline = time.monotonic() + cfg.live_session_max_seconds
                try:
                    while True:
                        if time.monotonic() > session_deadline:
                            logger.info("Live audio session reached %d s; closing", cfg.live_session_max_seconds)
                            await client_ws.send_json(
                                {"type": "error", "message": "Session time limit reached. Press the microphone to start again."}
                            )
                            await client_ws.close(code=1000)
                            break
                        msg = await client_ws.receive()
                        if msg["type"] == "websocket.disconnect":  # receive() must not be called again
                            logger.info("Live audio client disconnected (code %s)", msg.get("code"))
                            break
                        if "bytes" in msg and msg["bytes"]:
                            if len(msg["bytes"]) > MAX_LIVE_FRAME_BYTES:
                                logger.warning("Live audio frame of %d bytes refused", len(msg["bytes"]))
                                await client_ws.close(code=1009)  # message too big
                                break
                            if capture is not None:
                                capture.write(msg["bytes"])
                            for frame_1024 in pacer.push_bytes(msg["bytes"]):
                                await prisma_ws.send(frame_1024)
                        elif "text" in msg and msg["text"]:
                            try:
                                ctrl = json.loads(msg["text"])
                            except ValueError:
                                logger.warning("Ignored a malformed live-audio control message")
                                continue
                            if isinstance(ctrl, dict) and ctrl.get("action") == "commit_now":
                                await assembler.flush_immediately()
                except WebSocketDisconnect as exc:
                    logger.info("Live audio client disconnected (code %s)", exc.code)
                finally:
                    prisma_recv_task.cancel()
                    await asyncio.gather(prisma_recv_task, return_exceptions=True)
                    await assembler.close()
        except Exception as exc:
            logger.exception("Live audio WebSocket error: %s", exc)
            try:
                await client_ws.send_json({"type": "error", "message": str(exc)})
            except Exception as send_exc:  # noqa: BLE001 - best-effort report on a dying socket
                logger.debug("Could not report the error to the client: %s", send_exc)
        finally:
            if capture is not None:
                capture.close()
                logger.info("Saved mic capture %s and %s", capture.wav_path, capture.sidecar_path)

    @app.post("/api/v1/sandbox/reset")
    async def sandbox_reset() -> Dict[str, Any]:
        async with sandbox_lock:
            sandbox_repo.reset_to_seed_state()
            sandbox.held_context = None
            return {"buyers": public_snapshot(sandbox_repo.fetch_dashboard_snapshot())["buyers"]}

    @app.post("/api/v1/sandbox/evaluate")
    async def sandbox_evaluate(payload: SandboxRequest) -> Dict[str, Any]:
        """Runs one utterance through the sandbox firewall (no speech, no real ledger)."""
        async with sandbox_lock:
            decisions = sandbox.evaluate_utterance(payload.transcript)
            return {
                "decisions": [d.model_dump(mode="json") for d in decisions],
                "buyers": public_snapshot(sandbox_repo.fetch_dashboard_snapshot())["buyers"],
            }

    @app.post("/api/v1/reset")
    async def reset_ledger() -> Dict[str, Any]:
        repo.reset_to_seed_state()
        firewall.held_context = None
        return {"status": "reset", "snapshot": public_snapshot(repo.fetch_dashboard_snapshot())}

    index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8").replace(
        "__MIC_RATE__", str(LIVE_MIC_SAMPLE_RATE)
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return index_html

    # Client-side routes of the desk app: each serves the same page so deep links and reloads work.
    for page_path in DESK_PAGES:
        app.add_api_route(page_path, index, methods=["GET"], response_class=HTMLResponse, include_in_schema=False)

    return app


app = create_app()
