"use strict";
/* Kadal Kural desk client: live mic → /ws/live-audio, typed or sample orders → /api/v1/ingest. */

const MIC_RATE = Number(document.body.dataset.micRate) || 8000;
const $ = (id) => document.getElementById(id);

const STATUS = {
  BOOKED: { kind: "booked", label: "Booked" },
  BOOKED_AFTER_BARGE_IN: { kind: "booked", label: "Booked, corrected" },
  CREDIT_HOLD_BREACH: { kind: "hold", label: "Credit hold" },
  PENDING_CLARIFICATION: { kind: "ask", label: "Ask again" },
  VOIDED_BY_UNDO: { kind: "undone", label: "Undone" },
};
const statusOf = (s) => STATUS[s] || { kind: "undone", label: String(s || "Unknown") };

const TRIES = [
  { text: "குமரனுக்கு 20 கிலோ டைகர் பிரான் 500 ரேட்டு", why: "Within credit, so it books ₹10,000" },
  { text: "செந்திலுக்கு 40 கிலோ வஞ்சரம் 740 ரேட்டு", why: "Goes over Senthil's limit, so it is held" },
  { text: "செந்திலுக்கு 25 கிலோ மட்டும் போடு", why: "Correction after a hold: books the smaller order" },
  { text: "கடைசி ஆர்டர் கேன்சல்", why: "Voice undo: reverses the last booking" },
  { text: "செந்திலுக்கு 10 கிலோ வஞ்சரம் 700 குமரனுக்கு 20 கிலோ டைகர் பிரான் 500 ரேட்டு", why: "Two orders in one breath" },
  { text: "குமரனுக்கு 20 கிலோ டைகர் பிரான் 60 ரேட்டு", why: "₹60/kg is not a prawn price, so it asks again" },
];

const state = {
  ws: null, audioCtx: null, processor: null, micStream: null,
  listening: false, ttsQueue: [], currentAudio: null,
  level: 0, levelTarget: 0, lastEventId: 0, gate: 0.82, segmentAt: 0,
};

/* ---------- helpers ---------- */
function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
}
const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN");
const ms = (n) => (n || n === 0) && Number(n) > 0 ? Math.round(Number(n)).toLocaleString("en-IN") + " ms" : "–";

function toast(message, kind = "info") {
  const el = document.createElement("div");
  el.className = "toast";
  el.dataset.kind = kind;
  el.textContent = message;
  $("toasts").appendChild(el);
  setTimeout(() => el.remove(), kind === "error" ? 7000 : 4000);
}

function setMode(mode, text) {
  const line = $("modeLine");
  line.dataset.mode = mode;
  line.textContent = text;
}

function idleMode() {
  if (state.currentAudio) return;
  if (state.listening) setMode("listening", "Listening");
  else setMode("idle", "Ready");
}

/* ---------- reply playback (barge-in aware) ---------- */
function stopPlayback() {
  state.ttsQueue = [];
  const audio = state.currentAudio;
  if (audio) {
    audio.onended = audio.onerror = null;
    audio.pause();
    state.currentAudio = null;
  }
}

function playNext() {
  const b64 = state.ttsQueue.shift();
  if (!b64) { state.currentAudio = null; idleMode(); return; }
  const audio = new Audio("data:audio/wav;base64," + b64);
  state.currentAudio = audio;
  setMode("speaking", "Replying");
  audio.onended = () => { if (state.currentAudio === audio) playNext(); };
  audio.onerror = audio.onended;
  audio.play().catch(() => {
    if (state.currentAudio === audio) playNext();
  });
}

function playReplies(clips) {
  stopPlayback();
  state.ttsQueue = clips.filter(Boolean);
  playNext();
}

/* ---------- rendering ---------- */
function decisionWhy(d) {
  const kind = statusOf(d.status).kind;
  if (d.status === "VOIDED_BY_UNDO") return "Reversed the last booked order. The original entry stays in the ledger, struck through.";
  if (kind === "booked") return `Within credit. Balance now ${inr(d.projected_balance_inr)} of ${inr(d.credit_limit_inr)}.`;
  if (kind === "hold") return `${inr(d.excess_amount_inr)} over the credit limit. Not dispatched.`;
  if (d.confidence !== undefined && d.confidence < state.gate) {
    return `Confidence ${Math.round(d.confidence * 100)}% is below the ${Math.round(state.gate * 100)}% gate, so the trader is asked to repeat.`;
  }
  return "Could not read a complete order, so the trader is asked to repeat.";
}

function renderDecisions(decisions, timings) {
  const box = $("decisions");
  if (!decisions.length) { box.innerHTML = ""; return; }
  box.innerHTML = decisions.map((d, i) => {
    const st = statusOf(d.status);
    const hasTrade = d.buyer_name !== undefined && d.status !== "VOIDED_BY_UNDO" && d.quantity > 0;
    const fields = hasTrade ? `
      <dl class="fields">
        <div><dt>Buyer</dt><dd>${escapeHtml(d.buyer_name)}</dd></div>
        <div><dt>Item</dt><dd>${escapeHtml(d.sku_name)}</dd></div>
        <div><dt>Quantity</dt><dd>${escapeHtml(d.quantity)} ${escapeHtml(d.unit)}</dd></div>
        <div><dt>Rate</dt><dd>${inr(d.rate_inr)}/${escapeHtml(d.unit)}</dd></div>
        <div class="value"><dt>Value</dt><dd>${inr(d.trade_value_inr)}</dd></div>
      </dl>` : "";
    const playAttr = d.audio_wav_b64 ? "" : "disabled";
    const confPct = d.confidence === undefined ? null : Math.round(d.confidence * 100);
    const confPart = confPct === null ? "" : `<span>Confidence <strong>${confPct}%</strong></span>`;
    const tim = timings ? `
      <p class="timings">
        <span>Speech to text <strong>${timings.stt > 0 ? ms(timings.stt) : "typed order"}</strong></span>
        <span>Reply audio first byte <strong>${ms(d.timbre_ttfb_ms)}</strong></span>
        ${confPart}
      </p>` : "";
    return `
      <article class="decision is-new" data-kind="${st.kind}">
        <div class="decision-top">
          <span class="stamp" data-kind="${st.kind}">${escapeHtml(st.label)}</span>
          <span class="decision-why">${escapeHtml(decisionWhy(d))}</span>
        </div>
        ${fields}
        <div class="reply">
          <button class="play" type="button" data-clip="${i}" ${playAttr} aria-label="Play the spoken reply">
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2.5v11l9-5.5z"/></svg>
          </button>
          <p class="reply-text" lang="ta">${escapeHtml(d.tts_response_tamil)}</p>
        </div>
        ${tim}
      </article>`;
  }).join("");
  box.querySelectorAll(".play").forEach((btn) => {
    btn.addEventListener("click", () => playReplies([decisions[Number(btn.dataset.clip)].audio_wav_b64]));
  });
}

function setHeard(text, partial = false) {
  const el = $("heardText");
  el.classList.toggle("is-empty", !text);
  el.classList.toggle("is-partial", partial);
  el.textContent = text || "Waiting for the first order";
}

function renderBuyers(buyers, touched = new Set()) {
  let outstanding = 0, limit = 0;
  $("buyers").innerHTML = buyers.map((b) => {
    outstanding += b.running_balance_inr; limit += b.credit_limit_inr;
    const used = b.credit_limit_inr ? b.running_balance_inr / b.credit_limit_inr : 1;
    const left = Math.max(0, b.credit_limit_inr - b.running_balance_inr);
    const level = used >= 0.95 ? "critical" : used >= 0.8 ? "tight" : "ok";
    return `
      <li class="buyer${touched.has(b.buyer_id) ? " is-flash" : ""}">
        <div class="buyer-top">
          <p class="buyer-name">${escapeHtml(b.canonical_name)}<span lang="ta">${escapeHtml(b.tamil_speak_name)}</span></p>
          <p class="buyer-left">${inr(left)} left<span>${inr(b.running_balance_inr)} of ${inr(b.credit_limit_inr)}</span></p>
        </div>
        <div class="gauge" data-level="${level}" role="meter" aria-valuemin="0" aria-valuemax="${escapeHtml(b.credit_limit_inr)}"
             aria-valuenow="${escapeHtml(b.running_balance_inr)}" aria-label="${escapeHtml(b.canonical_name)} credit used">
          <div class="gauge-fill" style="width:${Math.min(100, used * 100).toFixed(1)}%"></div>
        </div>
      </li>`;
  }).join("");
  $("exposureTotal").textContent = `${inr(outstanding)} owed of ${inr(limit)}`;
  if (touched.size) setTimeout(() => document.querySelectorAll(".buyer.is-flash").forEach((n) => n.classList.remove("is-flash")), 1600);
}

function renderLedger(events) {
  const voided = new Set(events.filter((e) => e.voids_event_id).map((e) => Number(e.voids_event_id)));
  const maxId = events.reduce((m, e) => Math.max(m, e.event_id), 0);
  $("ledgerEmpty").hidden = events.length > 0;
  $("eventsTable").innerHTML = events.map((e) => {
    const st = statusOf(e.status);
    const conf = Math.round((e.confidence || 0) * 100);
    const upi = e.upi_link_visible && String(e.upi_payment_uri).startsWith("upi:")
      ? `<a class="pay" href="${escapeHtml(e.upi_payment_uri)}">UPI link</a>` : "–";
    const classes = [voided.has(e.event_id) ? "is-voided" : "", e.event_id > state.lastEventId && state.lastEventId ? "is-new" : ""].join(" ").trim();
    return `
      <tr class="${classes}">
        <td>${escapeHtml(e.created_at)}</td>
        <td class="heard" title="${escapeHtml(e.raw_utterance)}" lang="ta">${escapeHtml(e.raw_utterance)}</td>
        <td>${escapeHtml(e.buyer_name)}</td>
        <td>${escapeHtml(e.sku_name)}</td>
        <td class="num">${escapeHtml(e.quantity)} ${escapeHtml(e.unit)} × ${inr(e.rate_inr)}</td>
        <td class="num">${inr(e.trade_value_inr)}</td>
        <td><span class="status" data-kind="${st.kind}">${escapeHtml(st.label)}</span></td>
        <td><span class="conf${conf < state.gate * 100 ? " is-low" : ""}"><span class="conf-bar"><i style="width:${conf}%"></i></span>${conf}%</span></td>
        <td>${upi}</td>
      </tr>`;
  }).join("");
  state.lastEventId = Math.max(state.lastEventId, maxId);

  const count = (kind) => events.filter((e) => statusOf(e.status).kind === kind && !voided.has(e.event_id)).length;
  const bookedValue = events
    .filter((e) => statusOf(e.status).kind === "booked" && !voided.has(e.event_id))
    .reduce((s, e) => s + e.trade_value_inr, 0);
  $("tally").innerHTML = `
    <div><dt>Booked</dt><dd>${count("booked")}</dd></div>
    <div><dt>Value</dt><dd>${inr(bookedValue)}</dd></div>
    <div><dt>Held</dt><dd>${count("hold")}</dd></div>
    <div><dt>Asked again</dt><dd>${count("ask")}</dd></div>`;
}

function renderSnapshot(snapshot, decisions = []) {
  const touched = new Set(decisions.map((d) => d.buyer_id).filter(Boolean));
  renderBuyers(snapshot.buyers || [], touched);
  renderLedger(snapshot.events || []);
}

function showTurn(heard, decisions, snapshot, timings) {
  setHeard(heard);
  renderDecisions(decisions, timings);
  renderSnapshot(snapshot, decisions);
  playReplies(decisions.map((d) => d.audio_wav_b64));
  if (!decisions.some((d) => d.audio_wav_b64)) idleMode();
}

/* ---------- server calls ---------- */
async function refresh() {
  try {
    const res = await fetch("/api/v1/state");
    if (!res.ok) throw new Error(`State request failed (${res.status})`);
    const data = await res.json();
    state.gate = data.confidence_threshold;
    $("gateValue").textContent = Math.round(data.confidence_threshold * 100) + "%";
    $("gateStep").textContent = Math.round(data.confidence_threshold * 100) + "%";
    $("deskTitle").textContent = data.domain_title || "Credit desk";
    const speech = $("healthSpeech");
    speech.dataset.state = data.gnani_live_key_configured ? "ok" : "warn";
    speech.querySelector(".pill-text").textContent = data.gnani_live_key_configured
      ? "Gnani speech connected" : "Add a Gnani key for voice";
    const phone = $("healthPhone");
    phone.dataset.state = data.phone_channel_enabled ? "ok" : "off";
    phone.querySelector(".pill-text").textContent = data.phone_channel_enabled ? "Phone line on" : "Phone line off";
    renderSnapshot(data);
  } catch (err) {
    toast(`Could not load the ledger: ${err.message}. Check that the server is running.`, "error");
  }
}

async function sendTranscript(text) {
  const transcript = text.trim();
  if (transcript.length < 2) { toast("Type an order first."); return; }
  stopPlayback();
  setHeard(transcript);
  setMode("thinking", "Checking the order");
  try {
    const res = await fetch("/api/v1/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transcript, synthesize_tts: true }),
    });
    if (!res.ok) throw new Error(`the server answered ${res.status}`);
    const out = await res.json();
    showTurn(transcript, out.decisions, out.snapshot, { stt: 0 });
  } catch (err) {
    setMode("error", "Order not checked");
    toast(`Order not checked: ${err.message}.`, "error");
  }
}

/* ---------- live microphone ---------- */
function animateLevel() {
  state.level += (state.levelTarget - state.level) * 0.35;
  $("micBtn").style.setProperty("--level", state.level.toFixed(3));
  if (state.listening) requestAnimationFrame(animateLevel);
  else $("micBtn").style.setProperty("--level", "0");
}

function setMicUi(on) {
  state.listening = on;
  const btn = $("micBtn");
  btn.setAttribute("aria-pressed", String(on));
  $("micLabel").textContent = on ? "Stop listening" : "Start listening";
  if (on) requestAnimationFrame(animateLevel);
}

function stopMic(message) {
  const ws = state.ws;
  state.ws = null;
  if (ws && ws.readyState <= WebSocket.OPEN) ws.close();
  if (state.processor) state.processor.disconnect();
  if (state.audioCtx) state.audioCtx.close();
  if (state.micStream) state.micStream.getTracks().forEach((t) => t.stop());
  state.processor = state.audioCtx = state.micStream = null;
  state.levelTarget = 0;
  setMicUi(false);
  if (message) setMode("error", message); else idleMode();
}

function onSocketMessage(evt) {
  const msg = JSON.parse(evt.data);
  if (msg.type === "error") {
    toast(msg.message, "error");
    stopMic("Listening stopped");
  } else if (msg.type === "prisma_connected") {
    setMode("listening", "Listening");
  } else if (msg.type === "barge_in_and_segment") {
    stopPlayback(); // the trader is talking: cut the reply at once
    state.segmentAt = performance.now();
    setHeard(msg.segment_text, true);
    setMode("thinking", "Heard you. Checking the order");
  } else if (msg.type === "credit_decisions") {
    showTurn(msg.assembled_transcript, msg.decisions, msg.snapshot, { stt: msg.stt_latency_ms });
  }
}

async function startMic() {
  const btn = $("micBtn");
  btn.disabled = true;
  setMode("connecting", "Connecting to the speech service");
  try {
    state.micStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, sampleRate: MIC_RATE, echoCancellation: true, noiseSuppression: false },
    });
  } catch (err) {
    btn.disabled = false;
    const denied = err && (err.name === "NotAllowedError" || err.name === "SecurityError");
    stopMic(denied ? "Microphone blocked" : "No microphone found");
    toast(denied
      ? "Allow microphone access for this page in the browser's address bar, then press the microphone again."
      : "Connect a microphone, then press the microphone again.", "error");
    return;
  }

  state.audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: MIC_RATE });
  if (state.audioCtx.sampleRate !== MIC_RATE) {
    const actual = state.audioCtx.sampleRate;
    btn.disabled = false;
    stopMic("Browser not supported");
    toast(`This browser records at ${actual} Hz; the desk needs ${MIC_RATE} Hz. Use Chrome or Edge.`, "error");
    return;
  }

  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/ws/live-audio`);
  ws.binaryType = "arraybuffer";
  state.ws = ws;
  ws.onmessage = onSocketMessage;
  ws.onclose = () => { if (state.ws === ws) stopMic("Connection closed"); };
  ws.onerror = () => toast("Lost the connection to the desk server.", "error");

  const source = state.audioCtx.createMediaStreamSource(state.micStream);
  state.processor = state.audioCtx.createScriptProcessor(512, 1, 1);
  state.processor.onaudioprocess = (e) => {
    const input = e.inputBuffer.getChannelData(0);
    let sum = 0;
    const pcm16 = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) {
      const s = Math.max(-1, Math.min(1, input[i]));
      sum += s * s;
      pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    state.levelTarget = Math.min(1, Math.sqrt(sum / input.length) * 6);
    if (state.ws && state.ws.readyState === WebSocket.OPEN) state.ws.send(pcm16.buffer);
  };
  source.connect(state.processor);
  state.processor.connect(state.audioCtx.destination);
  btn.disabled = false;
  setMicUi(true);
}

function toggleMic() {
  if (state.listening || state.ws) stopMic();
  else startMic();
}

/* ---------- theme ---------- */
function applyTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}
function currentTheme() {
  const set = document.documentElement.dataset.theme;
  if (set) return set;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
try { applyTheme(localStorage.getItem("kk-theme")); } catch (_) { /* storage unavailable */ }

/* ---------- wiring ---------- */
$("tries").innerHTML = TRIES.map((t, i) => `
  <li><button class="try" type="button" data-try="${i}">
    <span class="try-text" lang="ta">${escapeHtml(t.text)}</span>
    <span class="try-why">${escapeHtml(t.why)}</span>
  </button></li>`).join("");
$("tries").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-try]");
  if (btn) sendTranscript(TRIES[Number(btn.dataset.try)].text);
});
$("micBtn").addEventListener("click", toggleMic);
$("typeForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = $("typeInput");
  sendTranscript(input.value);
  input.value = "";
});
$("resetBtn").addEventListener("click", async () => {
  stopPlayback();
  try {
    const res = await fetch("/api/v1/reset", { method: "POST" });
    if (!res.ok) throw new Error(String(res.status));
    state.lastEventId = 0;
    setHeard("");
    renderDecisions([]);
    idleMode();
    await refresh();
    toast("Balances reset to the opening ledger.");
  } catch (err) {
    toast(`Balances not reset: the server answered ${err.message}.`, "error");
  }
});
$("themeBtn").addEventListener("click", () => {
  const next = currentTheme() === "dark" ? "light" : "dark";
  applyTheme(next);
  try { localStorage.setItem("kk-theme", next); } catch (_) { /* storage unavailable */ }
});
document.addEventListener("keydown", (e) => {
  if (e.code !== "Space" || e.repeat) return;
  const t = e.target;
  if (t !== document.body && t !== document.documentElement) return; // typing or a focused control
  e.preventDefault();
  toggleMic();
});

refresh();
