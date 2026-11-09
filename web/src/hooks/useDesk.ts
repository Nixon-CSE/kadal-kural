import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { api, type Decision, type DeskState, type LiveMessage, type Snapshot } from "@/lib/api";
import { inr, statusOf, type Kind } from "@/lib/format";

export type Mode = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "error";

export interface Turn {
  id: number;
  at: Date;
  heard: string;
  partial: boolean;
  source: "voice" | "typed";
  decisions: Decision[];
  sttMs: number;
  ttfbMs: number;
}

/** Pipeline stage the last turn reached: 0 idle, 1 heard … 5 recorded and replied. */
export type Stage = 0 | 1 | 2 | 3 | 4 | 5;

const MIC_RATE = Number(document.body.dataset.micRate) || 8000;
/** How often the desk checks for orders placed by phone (the agent calls the server, not this page). */
const PHONE_POLL_MS = 4000;

export function useDesk() {
  const [desk, setDesk] = useState<DeskState | null>(null);
  const [mode, setMode] = useState<Mode>("idle");
  const [modeText, setModeText] = useState("Ready");
  const [listening, setListening] = useState(false);
  const [turn, setTurn] = useState<Turn | null>(null);
  const [history, setHistory] = useState<Turn[]>([]);
  const [stage, setStage] = useState<Stage>(0);
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const [newIds, setNewIds] = useState<Set<number>>(new Set());

  /** 0..1 microphone level, read by the 3D orb every frame without re-rendering React. */
  const level = useRef(0);
  const audio = useRef<{ ws: WebSocket | null; ctx: AudioContext | null; proc: ScriptProcessorNode | null; stream: MediaStream | null }>({
    ws: null, ctx: null, proc: null, stream: null,
  });
  const player = useRef<{ queue: string[]; current: HTMLAudioElement | null }>({ queue: [], current: null });
  const turnId = useRef(0);
  const lastEventId = useRef(0);
  const stageTimers = useRef<number[]>([]);
  const listeningRef = useRef(false);

  const idle = useCallback(() => {
    if (player.current.current) return;
    if (listeningRef.current) { setMode("listening"); setModeText("Listening"); }
    else { setMode("idle"); setModeText("Ready"); }
  }, []);

  const applySnapshot = useCallback((snap: Snapshot, decisions: Decision[] = []) => {
    const fresh = new Set(snap.events.filter((e) => e.event_id > lastEventId.current).map((e) => e.event_id));
    if (lastEventId.current > 0) setNewIds(fresh);
    lastEventId.current = Math.max(lastEventId.current, ...snap.events.map((e) => e.event_id), 0);
    setTouched(new Set(decisions.map((d) => d.buyer_id).filter(Boolean) as string[]));
    setDesk((prev) => (prev ? { ...prev, ...snap } : prev));
  }, []);

  const refresh = useCallback(async () => {
    try {
      const state = await api.state();
      lastEventId.current = Math.max(0, ...state.events.map((e) => e.event_id));
      setDesk(state);
    } catch (err) {
      toast.error(`Could not load the ledger: ${(err as Error).message}. Check that the server is running.`);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  /* ---------- phone line: orders placed through the Gnani agent appear without a reload ---------- */
  const phoneOn = !!desk?.phone_channel_enabled;
  useEffect(() => {
    if (!phoneOn) return;
    let stopped = false;
    let inFlight = false;
    const tick = async () => {
      if (inFlight || document.visibilityState !== "visible") return;
      inFlight = true;
      try {
        const state = await api.state();
        if (stopped) return;
        const fresh = state.events.filter((e) => e.event_id > lastEventId.current);
        // Only phone entries are applied here: the desk's own turns land through their own response,
        // and applying them early would steal their highlight.
        const phone = fresh.filter((e) => e.channel === "phone");
        if (!phone.length) return;
        applySnapshot(state);
        for (const e of [...phone].reverse()) {
          const st = statusOf(e.status);
          const what = st.kind === "undone" ? "Last booking undone" : `${e.buyer_name}, ${inr(e.trade_value_inr)}`;
          toast.message(`Phone order: ${st.label}`, { description: `${what} · “${e.raw_utterance}”` });
        }
      } catch {
        /* the next tick retries; a server that stays down is reported by the next desk action */
      } finally {
        inFlight = false;
      }
    };
    const id = window.setInterval(() => void tick(), PHONE_POLL_MS);
    return () => { stopped = true; window.clearInterval(id); };
  }, [phoneOn, applySnapshot]);

  /* ---------- reply playback (stops the instant the trader talks) ---------- */
  const stopPlayback = useCallback(() => {
    const p = player.current;
    p.queue = [];
    if (p.current) { p.current.onended = p.current.onerror = null; p.current.pause(); p.current = null; }
  }, []);

  const playNext = useCallback(() => {
    const p = player.current;
    const b64 = p.queue.shift();
    if (!b64) { p.current = null; idle(); return; }
    const el = new Audio("data:audio/wav;base64," + b64);
    p.current = el;
    setMode("speaking"); setModeText("Replying");
    const next = () => { if (p.current === el) playNext(); };
    el.onended = next;
    el.onerror = next;
    el.play().catch(() => { if (p.current === el) playNext(); });
  }, [idle]);

  const play = useCallback((clips: (string | undefined)[]) => {
    stopPlayback();
    player.current.queue = clips.filter(Boolean) as string[];
    playNext();
  }, [playNext, stopPlayback]);

  /* ---------- pipeline animation ---------- */
  const runPipeline = useCallback((from: Stage) => {
    stageTimers.current.forEach(clearTimeout);
    stageTimers.current = [];
    setStage(from);
    for (let s = from + 1; s <= 5; s++) {
      stageTimers.current.push(window.setTimeout(() => setStage(s as Stage), (s - from) * 160));
    }
  }, []);

  const landTurn = useCallback((heard: string, decisions: Decision[], snapshot: Snapshot, source: Turn["source"], sttMs: number) => {
    const t: Turn = {
      id: ++turnId.current, at: new Date(), heard, partial: false, source, decisions, sttMs,
      ttfbMs: Math.max(0, ...decisions.map((d) => d.timbre_ttfb_ms || 0)),
    };
    setTurn(t);
    setHistory((h) => [...h.slice(-29), t]);
    applySnapshot(snapshot, decisions);
    runPipeline(source === "voice" ? 1 : 2);
    const kinds = new Set<Kind>(decisions.map((d) => statusOf(d.status).kind));
    if (kinds.has("hold")) toast.error("Credit hold: the order was not dispatched.");
    play(decisions.map((d) => d.audio_wav_b64));
    if (!decisions.some((d) => d.audio_wav_b64)) idle();
  }, [applySnapshot, idle, play, runPipeline]);

  /* ---------- typed or sample order ---------- */
  const sendTranscript = useCallback(async (text: string) => {
    const transcript = text.trim();
    if (transcript.length < 2) { toast("Type an order first."); return; }
    stopPlayback();
    setTurn({ id: ++turnId.current, at: new Date(), heard: transcript, partial: true, source: "typed", decisions: [], sttMs: 0, ttfbMs: 0 });
    setMode("thinking"); setModeText("Checking the order");
    try {
      const out = await api.ingest(transcript);
      landTurn(transcript, out.decisions, out.snapshot, "typed", 0);
    } catch (err) {
      setMode("error"); setModeText("Order not checked");
      toast.error(`Order not checked: ${(err as Error).message}.`);
    }
  }, [landTurn, stopPlayback]);

  /* ---------- live microphone ---------- */
  const stopMic = useCallback((message?: string) => {
    const a = audio.current;
    const ws = a.ws; a.ws = null;
    if (ws && ws.readyState <= WebSocket.OPEN) ws.close();
    a.proc?.disconnect(); void a.ctx?.close(); a.stream?.getTracks().forEach((t) => t.stop());
    a.proc = null; a.ctx = null; a.stream = null;
    level.current = 0;
    listeningRef.current = false; setListening(false);
    if (message) { setMode("error"); setModeText(message); } else idle();
  }, [idle]);

  const onMessage = useCallback((evt: MessageEvent) => {
    const msg = JSON.parse(evt.data as string) as LiveMessage;
    if (msg.type === "error") { toast.error(msg.message); stopMic("Listening stopped"); }
    else if (msg.type === "prisma_connected") { setMode("listening"); setModeText("Listening"); }
    else if (msg.type === "barge_in_and_segment") {
      stopPlayback();
      setTurn((t) => ({ id: t?.partial ? t.id : ++turnId.current, at: new Date(), heard: msg.segment_text, partial: true, source: "voice", decisions: [], sttMs: msg.stt_latency_ms, ttfbMs: 0 }));
      setStage(1);
      setMode("thinking"); setModeText("Heard you. Checking the order");
    } else if (msg.type === "credit_decisions") {
      landTurn(msg.assembled_transcript, msg.decisions, msg.snapshot, "voice", msg.stt_latency_ms);
    }
  }, [landTurn, stopMic, stopPlayback]);

  const startMic = useCallback(async () => {
    setMode("connecting"); setModeText("Connecting to the speech service");
    const a = audio.current;
    try {
      a.stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, sampleRate: MIC_RATE, echoCancellation: true, noiseSuppression: false },
      });
    } catch (err) {
      const denied = (err as DOMException)?.name === "NotAllowedError" || (err as DOMException)?.name === "SecurityError";
      stopMic(denied ? "Microphone blocked" : "No microphone found");
      toast.error(denied
        ? "Allow microphone access for this page in the address bar, then press the microphone again."
        : "Connect a microphone, then press the microphone again.");
      return;
    }
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    a.ctx = new Ctx({ sampleRate: MIC_RATE });
    if (a.ctx.sampleRate !== MIC_RATE) {
      const actual = a.ctx.sampleRate;
      stopMic("Browser not supported");
      toast.error(`This browser records at ${actual} Hz; the desk needs ${MIC_RATE} Hz. Use Chrome or Edge.`);
      return;
    }
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${location.host}/ws/live-audio`);
    ws.binaryType = "arraybuffer";
    a.ws = ws;
    ws.onmessage = onMessage;
    ws.onclose = () => { if (audio.current.ws === ws) stopMic("Connection closed"); };
    ws.onerror = () => toast.error("Lost the connection to the desk server.");

    const source = a.ctx.createMediaStreamSource(a.stream);
    a.proc = a.ctx.createScriptProcessor(512, 1, 1);
    a.proc.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      const pcm = new Int16Array(input.length);
      let sum = 0;
      for (let i = 0; i < input.length; i++) {
        const s = Math.max(-1, Math.min(1, input[i]));
        sum += s * s;
        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      level.current = Math.min(1, Math.sqrt(sum / input.length) * 6);
      if (audio.current.ws?.readyState === WebSocket.OPEN) audio.current.ws.send(pcm.buffer);
    };
    source.connect(a.proc);
    a.proc.connect(a.ctx.destination);
    listeningRef.current = true; setListening(true);
  }, [onMessage, stopMic]);

  const toggleMic = useCallback(() => {
    if (listeningRef.current || audio.current.ws) stopMic(); else void startMic();
  }, [startMic, stopMic]);

  const reset = useCallback(async () => {
    stopPlayback();
    try {
      await api.reset();
      lastEventId.current = 0;
      setTurn(null); setHistory([]); setStage(0); setNewIds(new Set());
      idle();
      await refresh();
      toast.success("Balances reset to the opening ledger.");
    } catch (err) {
      toast.error(`Balances not reset: ${(err as Error).message}.`);
    }
  }, [idle, refresh, stopPlayback]);

  useEffect(() => () => { stopMic(); stageTimers.current.forEach(clearTimeout); }, [stopMic]);

  return {
    desk, mode, modeText, listening, turn, history, stage, touched, newIds, level,
    toggleMic, sendTranscript, reset, play, refresh,
  };
}

export type DeskApi = ReturnType<typeof useDesk>;
