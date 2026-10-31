"""
Production FastAPI Gateway for Kadal Kural.
Exposes:
- Full-duplex WebSocket (/ws/live-audio) bridging Browser WebAudio 8kHz PCM <-> Gnani Prisma v2.5 & Timbre v2.5
- Real WAV file streaming endpoint (/api/v1/upload-wav)
- REST state & deterministic ingest endpoints (/api/v1/state, /api/v1/ingest)
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import wave
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import websockets
from websockets.exceptions import ConnectionClosed

from kadal_kural.config import LIVE_MIC_SAMPLE_RATE, WS_PING_INTERVAL_SEC, AppSettings
from kadal_kural.domain.matcher import BilingualCatalogMatcher
from kadal_kural.domain.service import PreDispatchCreditFirewallService
from kadal_kural.infrastructure.gnani_client import (
    GnaniArthaSpeechClient,
    GnaniConfigurationError,
    MultiSegmentTradeAssembler,
    PCM1024RingBufferPacer,
)
from kadal_kural.infrastructure.persistence import AppendOnlyLedgerRepository

logger = logging.getLogger(__name__)


class UtteranceIngestRequest(BaseModel):
    transcript: str = Field(..., min_length=2)
    stt_latency_ms: float = Field(default=288.0, ge=0.0)
    synthesize_tts: bool = Field(default=True)


def create_app(settings: Optional[AppSettings] = None) -> FastAPI:
    cfg = settings or AppSettings()
    matcher = BilingualCatalogMatcher(cfg.catalog_path, cfg.assumed_unit_confidence)
    repo = AppendOnlyLedgerRepository(cfg.db_path, list(matcher.buyers.values()))
    firewall = PreDispatchCreditFirewallService(cfg, matcher, repo)
    speech_client = GnaniArthaSpeechClient(cfg)

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
            **repo.fetch_dashboard_snapshot(),
        }

    @app.post("/api/v1/ingest")
    async def ingest_utterance(payload: UtteranceIngestRequest) -> Dict[str, Any]:
        decisions = firewall.evaluate_utterance(
            payload.transcript, stt_latency_ms=payload.stt_latency_ms
        )
        serialized = []
        has_key = bool(cfg.gnani_api_key and cfg.gnani_api_key != "your_gnani_api_key_here")
        for dec in decisions:
            item = dec.model_dump()
            if payload.synthesize_tts and has_key:
                telemetry = await speech_client.synthesize_timbre_v25(dec.tts_response_tamil)
                item["timbre_ttfb_ms"] = telemetry.ttfb_ms
                item["audio_wav_b64"] = base64.b64encode(telemetry.audio_wav_bytes).decode("ascii")
            serialized.append(item)
        return {
            "decisions": serialized,
            "snapshot": repo.fetch_dashboard_snapshot(),
        }

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

        async def _collect_segment(text: str, lat_ms: float) -> None:
            if text.strip():
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
                "snapshot": repo.fetch_dashboard_snapshot(),
            }

        decisions = firewall.evaluate_utterance(merged_transcript, stt_latency_ms=mean_lat)
        serialized = []
        for dec in decisions:
            item = dec.model_dump()
            telemetry = await speech_client.synthesize_timbre_v25(dec.tts_response_tamil)
            item["timbre_ttfb_ms"] = telemetry.ttfb_ms
            item["audio_wav_b64"] = base64.b64encode(telemetry.audio_wav_bytes).decode("ascii")
            serialized.append(item)

        return {
            "merged_transcript": merged_transcript,
            "stt_latency_ms": mean_lat,
            "decisions": serialized,
            "snapshot": repo.fetch_dashboard_snapshot(),
        }

    @app.websocket("/ws/live-audio")
    async def live_audio_websocket(client_ws: WebSocket) -> None:
        """
        Full-duplex live audio bridge:
        Browser Mic (8kHz 16-bit PCM) -> 1,024-byte RingBuffer -> Gnani Prisma v2.5 WS
        -> 1.5s TradeAssembler -> Credit Firewall -> Gnani Timbre v2.5 WS -> Browser Speaker.
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

        async def _on_assembled_utterance(merged_text: str, mean_stt_ms: float) -> None:
            decisions = firewall.evaluate_utterance(merged_text, stt_latency_ms=mean_stt_ms)
            out_decisions = []
            for dec in decisions:
                item = dec.model_dump()
                telemetry = await speech_client.synthesize_timbre_v25(dec.tts_response_tamil)
                item["timbre_ttfb_ms"] = telemetry.ttfb_ms
                item["audio_wav_b64"] = base64.b64encode(telemetry.audio_wav_bytes).decode("ascii")
                out_decisions.append(item)

            await client_ws.send_json(
                {
                    "type": "credit_decisions",
                    "assembled_transcript": merged_text,
                    "stt_latency_ms": mean_stt_ms,
                    "decisions": out_decisions,
                    "snapshot": repo.fetch_dashboard_snapshot(),
                }
            )

        assembler = MultiSegmentTradeAssembler(
            window_sec=cfg.assembler_window_sec,
            on_commit=_on_assembled_utterance,
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
                            evt = json.loads(raw_msg)
                            if evt.get("type") == "transcript":
                                seg_text = str(evt.get("text", "")).strip()
                                seg_lat = float(evt.get("latency", 0.0))
                                if seg_text:
                                    # Immediately tell browser to flush any playing TTS (Barge-In)
                                    speech_client.trigger_barge_in_abort()
                                    await client_ws.send_json(
                                        {
                                            "type": "barge_in_and_segment",
                                            "segment_text": seg_text,
                                            "stt_latency_ms": seg_lat,
                                        }
                                    )
                                    await assembler.ingest_segment(seg_text, seg_lat)
                    except ConnectionClosed:
                        return

                prisma_recv_task = asyncio.create_task(_prisma_to_client())
                try:
                    while True:
                        msg = await client_ws.receive()
                        if "bytes" in msg and msg["bytes"]:
                            for frame_1024 in pacer.push_bytes(msg["bytes"]):
                                await prisma_ws.send(frame_1024)
                        elif "text" in msg and msg["text"]:
                            ctrl = json.loads(msg["text"])
                            if ctrl.get("action") == "commit_now":
                                await assembler.flush_immediately()
                except WebSocketDisconnect:
                    pass
                finally:
                    prisma_recv_task.cancel()
        except Exception as exc:
            logger.exception("Live audio WebSocket error: %s", exc)
            try:
                await client_ws.send_json({"type": "error", "message": str(exc)})
            except Exception:
                pass

    @app.post("/api/v1/reset")
    async def reset_ledger() -> Dict[str, Any]:
        repo.reset_to_seed_state()
        firewall.held_context = None
        return {"status": "reset", "snapshot": repo.fetch_dashboard_snapshot()}

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Kadal Kural (கடல் குரல்) — B2B Pre-Dispatch Credit Firewall</title>
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; background: #090d16; color: #f8fafc; margin: 0; padding: 24px; }
    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #1e293b; padding-bottom: 16px; margin-bottom: 20px; }
    .badge { background: #0f172a; border: 1px solid #38bdf8; color: #38bdf8; padding: 6px 12px; border-radius: 6px; font-weight: 700; font-size: 12px; }
    .grid { display: grid; grid-template-columns: 360px 1fr; gap: 20px; }
    .card { background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 18px; }
    .btn { background: #2563eb; color: white; border: none; padding: 10px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; margin-right: 8px; margin-bottom: 8px; }
    .btn-mic { background: #16a34a; font-size: 15px; }
    .btn-mic.recording { background: #dc2626; animation: pulse 1.2s infinite; }
    .btn-warn { background: #d97706; }
    .btn-muted { background: #475569; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.65; } 100% { opacity: 1; } }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }
    th, td { text-align: left; padding: 10px; border-bottom: 1px solid #1f2937; }
    .BOOKED, .BOOKED_AFTER_BARGE_IN { color: #4ade80; font-weight: 700; }
    .CREDIT_HOLD_BREACH { color: #f87171; font-weight: 700; }
    .PENDING_CLARIFICATION { color: #facc15; font-weight: 700; }
    .VOIDED_BY_UNDO { color: #a78bfa; font-weight: 700; }
    .alert-box { background: #172554; border-left: 4px solid #38bdf8; padding: 14px; margin-bottom: 18px; border-radius: 6px; font-size: 14px; display: none; }
    .stream-bar { background: #0f172a; border: 1px solid #334155; padding: 10px 14px; border-radius: 6px; margin-bottom: 16px; font-size: 13px; color: #94a3b8; }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1 style="margin:0; font-size:24px;">Kadal Kural (கடல் குரல்) · Pre-Dispatch Credit Firewall</h1>
      <p style="margin:4px 0 0; color:#94a3b8; font-size:14px;">Live 8kHz 1,024-Byte Paced Streaming · Gnani Prisma v2.5 STT + Deterministic Engine + Timbre v2.5 TTS</p>
    </div>
    <span id="keyBadge" class="badge">CHECKING GNANI API KEY...</span>
  </div>

  <div style="margin-bottom: 12px;">
    <button id="micBtn" class="btn btn-mic" onclick="toggleLiveMic()">🎙️ Start Live 8kHz Microphone Stream (Prisma v2.5 + Timbre v2.5)</button>
    <button class="btn" onclick="runScreenshotTest()">▶ Replay Verified Transcript</button>
    <button class="btn btn-warn" onclick="runBargeInOverride()">⚡ Barge-In ("செந்திலுக்கு 25 பாக்ஸ் மட்டும் போடு")</button>
    <button class="btn btn-muted" onclick="runUndoTest()">↩ Voice Undo ("கடைசி ஆர்டர் கேன்சல்")</button>
    <button class="btn btn-muted" onclick="resetDemo()">↺ Reset</button>
  </div>

  <div id="streamStatus" class="stream-bar">
    <strong>Live Pipeline Telemetry:</strong> Idle. Click "Start Live 8kHz Microphone Stream" to open a real-time 1,024-byte PCM stream to Gnani Prisma v2.5.
  </div>

  <div id="ttsBanner" class="alert-box"></div>

  <div class="grid">
    <div class="card">
      <h3 style="margin-top:0;">Buyer Credit Exposure</h3>
      <div id="buyersList"></div>
    </div>
    <div class="card">
      <h3 style="margin-top:0;">Append-Only Pre-Dispatch Audit Log</h3>
      <table>
        <thead>
          <tr><th>Time</th><th>Buyer</th><th>SKU</th><th>Qty × Rate</th><th>Value</th><th>Status</th><th>Conf</th><th>UPI QR</th></tr>
        </thead>
        <tbody id="eventsTable"></tbody>
      </table>
    </div>
  </div>

  <script>
    let ws = null;
    let audioCtx = null;
    let processor = null;
    let micStream = null;
    let currentTtsAudio = null;

    async function refresh() {
      const res = await fetch("/api/v1/state");
      const data = await res.json();
      const badge = document.getElementById("keyBadge");
      if (data.gnani_live_key_configured) {
        badge.textContent = "LIVE GNANI ARTHA KEY ACTIVE · τ = " + data.confidence_threshold;
        badge.style.borderColor = "#4ade80";
        badge.style.color = "#4ade80";
      } else {
        badge.textContent = "ADD KADAL_GNANI_API_KEY IN .ENV FOR LIVE AUDIO";
        badge.style.borderColor = "#facc15";
        badge.style.color = "#facc15";
      }
      renderState(data);
    }

    function stopCurrentTtsPlayback() {
      if (currentTtsAudio) {
        currentTtsAudio.pause();
        currentTtsAudio.currentTime = 0;
        currentTtsAudio = null;
      }
    }

    function playBase64Wav(b64) {
      if (!b64) return;
      stopCurrentTtsPlayback();
      currentTtsAudio = new Audio("data:audio/wav;base64," + b64);
      currentTtsAudio.play().catch(err => console.warn("Audio play blocked:", err));
    }

    async function toggleLiveMic() {
      const btn = document.getElementById("micBtn");
      const statusEl = document.getElementById("streamStatus");
      if (ws) {
        ws.close();
        ws = null;
        if (processor) processor.disconnect();
        if (audioCtx) audioCtx.close();
        if (micStream) micStream.getTracks().forEach(t => t.stop());
        btn.classList.remove("recording");
        btn.textContent = "🎙️ Start Live 8kHz Microphone Stream (Prisma v2.5 + Timbre v2.5)";
        statusEl.innerHTML = "<strong>Live Pipeline Telemetry:</strong> Stream closed.";
        return;
      }

      const proto = location.protocol === "https:" ? "wss:" : "ws:";
      ws = new WebSocket(proto + "//" + location.host + "/ws/live-audio");
      ws.binaryType = "arraybuffer";

      ws.onmessage = (evt) => {
        const msg = JSON.parse(evt.data);
        if (msg.type === "error") {
          statusEl.innerHTML = `<span style="color:#f87171;"><strong>Error:</strong> ${msg.message}</span>`;
          toggleLiveMic();
          return;
        }
        if (msg.type === "prisma_connected") {
          statusEl.innerHTML = `<strong>Live Prisma v2.5 Session (${msg.session_id}):</strong> Streaming 8,000 Hz 16-bit mono PCM (1,024-byte frames)... Speak now in Tamil/Tanglish!`;
        }
        if (msg.type === "barge_in_and_segment") {
          stopCurrentTtsPlayback();
          statusEl.innerHTML = `<strong>VAD Segment (${msg.stt_latency_ms}ms):</strong> "${msg.segment_text}" <em>(Assembling 1.5s window...)</em>`;
        }
        if (msg.type === "credit_decisions") {
          const banner = document.getElementById("ttsBanner");
          banner.style.display = "block";
          banner.innerHTML = msg.decisions.map(r =>
            `<div><strong>[${r.status}] (STT: ${msg.stt_latency_ms}ms | Timbre TTFB: ${r.timbre_ttfb_ms || 0}ms):</strong> ${r.tts_response_tamil}</div>`
          ).join("<hr style='border-color:#1e3a8a'/>");
          renderState(msg.snapshot);
          const lastWithAudio = msg.decisions.find(d => d.audio_wav_b64);
          if (lastWithAudio) playBase64Wav(lastWithAudio.audio_wav_b64);
        }
      };

      micStream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, sampleRate: __MIC_RATE__, echoCancellation: true, noiseSuppression: false }
      });
      audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: __MIC_RATE__ });
      if (audioCtx.sampleRate !== __MIC_RATE__) {
        // The server declares x-sample-rate=__MIC_RATE__; streaming any other rate would be mis-transcribed.
        const actual = audioCtx.sampleRate;
        await audioCtx.close();
        micStream.getTracks().forEach(tr => tr.stop());
        ws.close();
        statusEl.textContent = `Browser mic runs at ${actual} Hz; this build requires __MIC_RATE__ Hz. Use Chrome.`;
        return;
      }
      const source = audioCtx.createMediaStreamSource(micStream);
      processor = audioCtx.createScriptProcessor(512, 1, 1);
      processor.onaudioprocess = (e) => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        const input = e.inputBuffer.getChannelData(0);
        const pcm16 = new Int16Array(input.length);
        for (let i = 0; i < input.length; i++) {
          const s = Math.max(-1, Math.min(1, input[i]));
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        ws.send(pcm16.buffer);
      };
      source.connect(processor);
      processor.connect(audioCtx.destination);
      btn.classList.add("recording");
      btn.textContent = "⏹ Stop Live Microphone Stream";
    }

    function renderState(data) {
      document.getElementById("buyersList").innerHTML = data.buyers.map(b => {
        const pct = Math.min(100, Math.round((b.running_balance_inr / b.credit_limit_inr) * 100));
        const color = pct > 90 ? "#ef4444" : "#22c55e";
        return `<div style="margin-bottom:16px;">
          <div style="display:flex;justify-content:space-between;">
            <strong>${b.canonical_name} (${b.tamil_speak_name})</strong>
            <span>₹${b.running_balance_inr.toLocaleString("en-IN")} / ₹${b.credit_limit_inr.toLocaleString("en-IN")}</span>
          </div>
          <div style="background:#1f2937;height:10px;border-radius:5px;margin-top:6px;">
            <div style="background:${color};width:${pct}%;height:10px;border-radius:5px;"></div>
          </div>
        </div>`;
      }).join("");

      document.getElementById("eventsTable").innerHTML = data.events.map(e => `
        <tr>
          <td>${e.created_at}</td>
          <td>${e.buyer_name}</td>
          <td>${e.sku_name}</td>
          <td>${e.quantity} ${e.unit} × ₹${e.rate_inr}</td>
          <td>₹${e.trade_value_inr.toLocaleString("en-IN")}</td>
          <td class="${e.status}">${e.status}</td>
          <td>${(e.confidence * 100).toFixed(0)}%</td>
          <td>${e.upi_payment_uri ? `<a href="${e.upi_payment_uri}" style="color:#38bdf8;">UPI Link</a>` : "-"}</td>
        </tr>
      `).join("");
    }

    async function sendTranscript(text) {
      stopCurrentTtsPlayback();
      const res = await fetch("/api/v1/ingest", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({transcript: text, stt_latency_ms: 288.0, synthesize_tts: true})
      });
      const out = await res.json();
      const banner = document.getElementById("ttsBanner");
      banner.style.display = "block";
      banner.innerHTML = out.decisions.map(r =>
        `<div><strong>[${r.status}] (Timbre TTFB: ${r.timbre_ttfb_ms || 0}ms):</strong> ${r.tts_response_tamil}</div>`
      ).join("<hr style='border-color:#1e3a8a'/>");
      renderState(out.snapshot);
      const lastWithAudio = out.decisions.find(d => d.audio_wav_b64);
      if (lastWithAudio) playBase64Wav(lastWithAudio.audio_wav_b64);
    }

    function runScreenshotTest() {
      sendTranscript("செந்தில் சீஃபுட்ஸ்க்கு 40 பாக்ஸ் எக்ஸ்போர்ட் வஞ்சரம் எழுநூற்றி 40 ரேட்டு குமரனுக்கு 60 கிலோ டைகர் ஃப்ராண்ட் ஐநூற்றி 60 ரேட்டு கிரெடிட்டில் ஏற்று");
    }
    function runBargeInOverride() {
      sendTranscript("செந்திலுக்கு 25 பாக்ஸ் மட்டும் போடு");
    }
    function runUndoTest() {
      sendTranscript("கடைசி ஆர்டர் கேன்சல்");
    }
    async function resetDemo() {
      stopCurrentTtsPlayback();
      await fetch("/api/v1/reset", {method: "POST"});
      document.getElementById("ttsBanner").style.display = "none";
      refresh();
    }
    refresh();
  </script>
</body>
</html>""".replace("__MIC_RATE__", str(LIVE_MIC_SAMPLE_RATE))

    return app


app = create_app()