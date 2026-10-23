"""FastAPI application factory, dependency wiring, and real-time audit console."""

from __future__ import annotations

import base64
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from kadal_kural.config import AppSettings
from kadal_kural.domain.matcher import BilingualCatalogMatcher
from kadal_kural.domain.service import PreDispatchCreditFirewallService
from kadal_kural.infrastructure.gnani_client import GnaniArthaSpeechClient
from kadal_kural.infrastructure.persistence import AppendOnlyLedgerRepository


class UtteranceIngestRequest(BaseModel):
    transcript: str = Field(..., min_length=2)
    stt_latency_ms: float = Field(default=288.0, ge=0.0)
    synthesize_tts: bool = Field(default=False)


def create_app(settings: AppSettings | None = None) -> FastAPI:
    cfg = settings or AppSettings()
    matcher = BilingualCatalogMatcher(cfg.catalog_path)
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
    async def healthcheck() -> Dict[str, str]:
        return {"status": "ok", "domain": matcher.domain_id}

    @app.get("/api/v1/state")
    async def get_dashboard_state() -> Dict[str, Any]:
        return {
            "domain_title": matcher.domain_title,
            "confidence_threshold": cfg.confidence_threshold,
            **repo.fetch_dashboard_snapshot(),
        }

    @app.post("/api/v1/ingest")
    async def ingest_utterance(payload: UtteranceIngestRequest) -> Dict[str, Any]:
        decisions = firewall.evaluate_utterance(
            payload.transcript, stt_latency_ms=payload.stt_latency_ms
        )
        serialized = []
        for dec in decisions:
            item = dec.model_dump()
            if payload.synthesize_tts and cfg.gnani_api_key:
                telemetry = await speech_client.synthesize_timbre_v25(dec.tts_response_tamil)
                item["timbre_ttfb_ms"] = telemetry.ttfb_ms
                item["audio_wav_b64"] = base64.b64encode(telemetry.audio_wav_bytes).decode("ascii")
            serialized.append(item)
        return {
            "decisions": serialized,
            "snapshot": repo.fetch_dashboard_snapshot(),
        }

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
    body { font-family: system-ui, -apple-system, sans-serif; background: #0b0f19; color: #f8fafc; margin: 0; padding: 24px; }
    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #1e293b; padding-bottom: 16px; margin-bottom: 20px; }
    .badge { background: #0284c7; color: white; padding: 6px 12px; border-radius: 6px; font-weight: 700; font-size: 13px; }
    .grid { display: grid; grid-template-columns: 1fr 2fr; gap: 20px; }
    .card { background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 18px; }
    .btn { background: #2563eb; color: white; border: none; padding: 10px 14px; border-radius: 6px; cursor: pointer; font-weight: 600; margin-right: 8px; margin-bottom: 8px; }
    .btn-warn { background: #d97706; }
    .btn-muted { background: #475569; }
    .btn-danger { background: #dc2626; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 14px; }
    th, td { text-align: left; padding: 10px; border-bottom: 1px solid #1f2937; }
    .BOOKED, .BOOKED_AFTER_BARGE_IN { color: #4ade80; font-weight: 700; }
    .CREDIT_HOLD_BREACH { color: #f87171; font-weight: 700; }
    .PENDING_CLARIFICATION { color: #facc15; font-weight: 700; }
    .VOIDED_BY_UNDO { color: #a78bfa; font-weight: 700; }
    .alert-box { background: #1e1b4b; border-left: 4px solid #6366f1; padding: 12px; margin-top: 12px; border-radius: 6px; font-size: 15px; }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1 style="margin:0;">Kadal Kural (கடல் குரல்)</h1>
      <p style="margin:4px 0 0; color:#94a3b8;">Zero-Screen B2B Pre-Dispatch Credit Firewall · Powered by Gnani Prisma v2.5 & Timbre v2.5</p>
    </div>
    <span class="badge">CONFIDENCE GATE τ = 0.82 ACTIVE</span>
  </div>

  <div style="margin-bottom: 20px;">
    <button class="btn" onclick="runScreenshotTest()">▶ 1. Replay Playground Transcript (2 Trades)</button>
    <button class="btn btn-warn" onclick="runBargeInOverride()">⚡ 2. Barge-In Override ("செந்திலுக்கு 25 பாக்ஸ் மட்டும் போடு")</button>
    <button class="btn btn-muted" onclick="runUndoTest()">↩ 3. Voice Undo ("கடைசி ஆர்டர் கேன்சல்")</button>
    <button class="btn btn-danger" onclick="resetDemo()">↺ Reset Ledger</button>
  </div>

  <div id="ttsBanner" class="alert-box" style="display:none;"></div>

  <div class="grid">
    <div class="card">
      <h3 style="margin-top:0;">Buyer Credit Exposure</h3>
      <div id="buyersList"></div>
    </div>
    <div class="card">
      <h3 style="margin-top:0;">Append-Only Pre-Dispatch Audit Log</h3>
      <table>
        <thead>
          <tr><th>Time</th><th>Buyer</th><th>SKU</th><th>Qty × Rate</th><th>Value</th><th>Status</th><th>Conf</th></tr>
        </thead>
        <tbody id="eventsTable"></tbody>
      </table>
    </div>
  </div>

  <script>
    async function refresh() {
      const res = await fetch("/api/v1/state");
      const data = await res.json();
      renderState(data);
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
        </tr>
      `).join("");
    }
    async function sendTranscript(text) {
      const res = await fetch("/api/v1/ingest", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({transcript: text, stt_latency_ms: 288.0, synthesize_tts: false})
      });
      const out = await res.json();
      const banner = document.getElementById("ttsBanner");
      banner.style.display = "block";
      banner.innerHTML = out.decisions.map(r => `<strong>Timbre v2.5 Voice Output (${r.status}):</strong> ${r.tts_response_tamil}`).join("<hr style=\"border-color:#1e3a8a\"/>");
      renderState(out.snapshot);
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
      await fetch("/api/v1/reset", {method: "POST"});
      document.getElementById("ttsBanner").style.display = "none";
      refresh();
    }
    refresh();
  </script>
</body>
</html>"""

    return app

app = create_app()
