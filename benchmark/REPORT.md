# Kadal Kural — Noise & Silent-Error Benchmark

Generated 2026-11-01 by `benchmark/run_eval.py` — 45 utterances × conditions [clean,harbour:10,harbour:5,market:10,market:5,traffic:10,traffic:5,ice_crusher:10,ice_crusher:5] = 405 items.

## Method (read this before the numbers)

- **Speaker:** Gnani Timbre v2.5 synthesizes each corpus utterance (once, cached). This is a repeatable stand-in for a human speaker, not a recording of a trader: real accents, disfluencies and Lombard effect are **not** represented.
- **Noise:** *synthetic*, spectrally shaped beds (harbour/market/traffic/ice-crusher; see `benchmark/noise_profiles.py`), mixed at a target **RMS SNR** over the speech segment. A noise-only lead-in and tail at the same absolute level surround the speech so the VAD must end the utterance through the noise. These are not field recordings of a harbour.
- **Pipeline:** 8 kHz PCM, 1,024-byte paced frames → Prisma v2.5 → merge segments → normalizer → matcher → firewall on a fresh catalog-seeded ledger per utterance (τ = 0.82 with the gate; τ = 0 without).
- **WER:** `jiwer`. *Normalized* passes both sides through `normalize_hybrid_tamil_numerals` (the corpus spells numbers as words; Prisma emits digits, so *raw* WER is inflated by formatting). Means over utterances.
- **Entity accuracy:** pooled over ground-truth trades; extracted intents are matched to trades by best field overlap.
- **Silent Financial Error Rate (SFER):** booked trades (`BOOKED` / `BOOKED_AFTER_BARGE_IN`) that match no ground-truth trade, divided by ground-truth trades attempted. Omitted trades are not silent errors. Without the gate, structural checks (unresolved buyer/SKU/rate/qty) still block booking.
- **Latency:** *STT* is the latency Prisma reports per segment (mean per utterance); *firewall* is the measured wall time of `evaluate_utterance` (normalizer + matcher + decision + SQLite write). Per-stage spans come from `PipelineTelemetry` (see *Latency by pipeline stage*). Timbre time-to-first-byte and barge-in stop time are live measurements in the hand-maintained sections at the end.

## Results

| Condition | n | WER (norm.) | WER (raw) | buyer | SKU | qty | unit | rate | STT P50 / P95 ms | firewall P50 / P95 ms | SFER gate ON | SFER gate OFF |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| clean (no noise) | 45 | 10.2% | 25.9% | 100.0% | 97.1% | 97.1% | 97.1% | 97.1% | 266 / 8322 | 0.17 / 0.19 | 0.0% (0/70) | 0.0% (0/70) |
| harbour @ 10 dB | 45 | 11.8% | 27.5% | 100.0% | 97.1% | 97.1% | 97.1% | 95.7% | 214 / 297 | 0.16 / 0.19 | 0.0% (0/70) | 0.0% (0/70) |
| harbour @ 5 dB | 45 | 12.1% | 27.8% | 100.0% | 97.1% | 97.1% | 97.1% | 95.7% | 218 / 341 | 0.16 / 0.19 | 0.0% (0/70) | 0.0% (0/70) |
| market @ 10 dB | 45 | 12.8% | 28.3% | 100.0% | 97.1% | 97.1% | 97.1% | 97.1% | 208 / 306 | 0.17 / 0.24 | 0.0% (0/70) | 0.0% (0/70) |
| market @ 5 dB | 45 | 17.6% | 32.2% | 100.0% | 97.1% | 97.1% | 97.1% | 92.9% | 209 / 340 | 0.16 / 0.21 | 0.0% (0/70) | 0.0% (0/70) |
| traffic @ 10 dB | 45 | 11.1% | 26.7% | 100.0% | 97.1% | 97.1% | 97.1% | 95.7% | 223 / 361 | 0.16 / 0.20 | 0.0% (0/70) | 0.0% (0/70) |
| traffic @ 5 dB | 45 | 11.4% | 27.2% | 100.0% | 97.1% | 97.1% | 97.1% | 95.7% | 202 / 406 | 0.16 / 0.19 | 0.0% (0/70) | 0.0% (0/70) |
| ice_crusher @ 10 dB | 45 | 12.3% | 27.6% | 100.0% | 95.7% | 95.7% | 95.7% | 95.7% | 204 / 305 | 0.16 / 0.19 | 0.0% (0/70) | 0.0% (0/70) |
| ice_crusher @ 5 dB | 45 | 13.6% | 28.8% | 100.0% | 97.1% | 97.1% | 97.1% | 97.1% | 217 / 328 | 0.16 / 0.19 | 0.0% (0/70) | 0.0% (0/70) |

### Roll-up by SNR (all four noise profiles)

| Condition | n | WER (norm.) | WER (raw) | buyer | SKU | qty | unit | rate | STT P50 / P95 ms | firewall P50 / P95 ms | SFER gate ON | SFER gate OFF |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all profiles @ 10 dB | 180 | 12.0% | 27.5% | 100.0% | 96.8% | 96.8% | 96.8% | 96.1% | 212 / 317 | 0.16 / 0.20 | 0.0% (0/280) | 0.0% (0/280) |
| all profiles @ 5 dB | 180 | 13.7% | 29.0% | 100.0% | 97.1% | 97.1% | 97.1% | 95.4% | 215 / 346 | 0.16 / 0.19 | 0.0% (0/280) | 0.0% (0/280) |
| **all noisy cells** | 360 | 12.8% | 28.3% | 100.0% | 97.0% | 97.0% | 97.0% | 95.7% | 214 / 345 | 0.16 / 0.20 | 0.0% (0/560) | 0.0% (0/560) |

## Latency by pipeline stage

Every scored item, all conditions. *Client-observed* STT and *STT connect* exist only for transcripts recorded after client-side STT timing was added (cached transcripts carry only the Prisma-reported figure), so their n can be smaller. This benchmark synthesizes no replies, so Timbre first byte is not a stage here.

| Stage | measures | n | P50 ms | P95 ms |
|---|---|---|---|---|
| STT, Prisma-reported | the `latency` field Prisma attaches to each transcript (mean per utterance) | 405 | 216 | 350 |
| STT, client-observed | last audio frame sent → last final transcript received | 0 | — | — |
| STT connect | WebSocket open + handshake frame | 0 | — | — |
| normalize | numeral normalizer | 405 | 0.013 | 0.016 |
| match | clause split + buyer/SKU/unit/amount matching | 405 | 0.055 | 0.080 |
| decide | confidence gate + credit check + SQLite ledger write, every intent | 405 | 0.076 | 0.090 |

## Does the confidence gate help?

Without the gate there were **no** silent errors across 560 noisy trades, so this run cannot show a gate benefit (the pipeline made no confident mistakes to block).

### Threshold sensitivity (all noisy cells, in-sample)

τ was *not* tuned on a held-out set; this table is the same data the headline uses, so treat it as sensitivity, not as an out-of-sample claim.

| τ | booked | silent errors | SFER | correct bookings |
|---|---|---|---|---|
| 0.5 | 416 | 0 | 0.0% | 416 |
| 0.6 | 414 | 0 | 0.0% | 414 |
| 0.7 | 404 | 0 | 0.0% | 404 |
| 0.8 | 381 | 0 | 0.0% | 381 |
| 0.82 (production) | 381 | 0 | 0.0% | 381 |
| 0.9 | 368 | 0 | 0.0% | 368 |
| 0.95 | 332 | 0 | 0.0% | 332 |

## Failure modes

Across 360 noisy runs the weakest extracted entity was **rate** (95.7% correct) and the worst cell by normalized WER was **market @ 5 dB** (17.6%). 0 item(s) failed outright (API error or timeout) and are excluded from the averages. 12 item(s) (3.0%, clean and noisy alike) had a Prisma-reported STT latency of 10.3–10.4 s instead of the usual ~0.2 s. Replaying them with client-side timing showed an intermittent Prisma-side stall (no retries, no drain timeout, independent of the audio and its noise tail); the client really waits that long for the transcript. See *STT latency spikes* below. No silent error survived the gate in this run. Caveats: synthetic noise and a synthetic speaker bound how far these numbers transfer to a real harbour; the corpus uses two buyers and two SKUs, so entity accuracy is easier than it would be against a large catalog.

<!-- Hand-maintained sections below: run_eval.py keeps everything after this line. -->

## Before/after: Phase 3C fixes on the same transcripts

Both columns score the **same 405 cached Prisma transcripts** (recorded 2026-10-31 for the current corpus); only the scoring code differs, so every change below comes from the code, not from STT variance.

- **pre-3C:** commit `f6870a5` (normalizer, matcher, catalog and scoring as of the Task 3 sweep), with only `benchmark/corpus.py` and the text-hash-keyed `benchmark/run_eval.py` taken from `e02f535` so it reads the same cached transcripts. Results: `benchmark/results_pre3c.csv`.
- **current:** the case-ending strip (3C-1), SKU default unit with unit confidence (3C-2), and per-unit rate/quantity bands (3C-3). Results: `benchmark/results.csv`.

Reproduce from the repo root (no API calls; both runs read `benchmark/.cache`):

```bash
REPO=$(pwd)
git worktree add --detach /tmp/pre3c f6870a5
git -C /tmp/pre3c checkout e02f535 -- benchmark/corpus.py benchmark/run_eval.py
cd /tmp/pre3c && PYTHONPATH=src:. python benchmark/run_eval.py --analyze-only --conditions clean,harbour:10,harbour:5,market:10,market:5,traffic:10,traffic:5,ice_crusher:10,ice_crusher:5 --cache-dir "$REPO/benchmark/.cache" --out-dir /tmp/pre3c_out
cd "$REPO" && python benchmark/compare_runs.py /tmp/pre3c_out/results.csv benchmark/results.csv --before-label pre-3C --after-label current --list-changes
```

| Condition | trades | silent errors, gate ON (pre-3C → current) | correct bookings, gate ON | booked, gate ON | silent errors, gate OFF | rate correct | unit correct |
|---|---|---|---|---|---|---|---|
| clean (no noise) | 70 | 1 → 0 | 48 → 49 | 49 | 2 → 0 | 95.7% → 97.1% | 94.3% → 97.1% |
| harbour @ 10 dB | 70 | 1 → 0 | 48 | 49 → 48 | 1 → 0 | 95.7% | 94.3% → 97.1% |
| harbour @ 5 dB | 70 | 1 → 0 | 48 | 49 → 48 | 1 → 0 | 95.7% | 94.3% → 97.1% |
| ice_crusher @ 10 dB | 70 | 0 | 48 | 48 | 0 | 95.7% | 94.3% → 95.7% |
| ice_crusher @ 5 dB | 70 | 0 | 47 | 47 | 1 → 0 | 97.1% | 94.3% → 97.1% |
| market @ 10 dB | 70 | 1 → 0 | 49 | 50 → 49 | 1 → 0 | 97.1% | 94.3% → 97.1% |
| market @ 5 dB | 70 | 0 | 42 → 45 | 42 → 45 | 0 | 87.1% → 92.9% | 88.6% → 97.1% |
| traffic @ 10 dB | 70 | 1 → 0 | 47 → 48 | 48 | 2 → 0 | 94.3% → 95.7% | 94.3% → 97.1% |
| traffic @ 5 dB | 70 | 1 → 0 | 48 | 49 → 48 | 1 → 0 | 95.7% | 94.3% → 97.1% |
| **all noisy cells** | 560 | 5 → 0 | 377 → 381 | 382 → 381 | 7 → 0 | 94.8% → 95.7% | 93.6% → 97.0% |

Every item whose gate-ON outcome changed:

- `multi_02` @ market/5: silent errors 0 → 0, correct bookings 1 → 2 — heard “செந்திலுக்கு 10 கிலோ வஞ்சரம் 800 வேட்டு குமரனுக்கு 10 கிலோ வஞ்சரம் 800 வேட்டு”
- `multi_09` @ clean/clean: silent errors 1 → 0, correct bookings 0 → 1 — heard “செந்தில் சீஃபுட்ஸ் 15 கிலோ டைகர் பிரான் ஐநூற்றுக்கு 60 ரேட்டு குமரனுக்கு 60 கிலோ டைகர் பிரான் எழுநூற்றி 40 ரேட்டு”
- `multi_09` @ traffic/10: silent errors 1 → 0, correct bookings 0 → 1 — heard “செந்தில் சீபுத்க்கு 15 கிலோ டைகர் பிரான் ஐநூற்றுக்கு 60 ரேட்டு குமரனுக்கு 60 கிலோ டைகர் பிரான் எழுநூற்றி 40 ரேட்டு”
- `multi_13` @ market/5: silent errors 0 → 0, correct bookings 1 → 2 — heard “குமரனுக்கு 40 கிலோ எக்ஸ்போர்ட் வஞ்சரம் எழுநூற்றி 40 ரேக்கு செந்திலுக்கு 30 கிலோ டைகர் பிரான் நானூற்றி 50 ரேக்கு”
- `multi_21` @ market/5: silent errors 0 → 0, correct bookings 1 → 2 — heard “குமரனுக்கு 20 கிலோ டைகர் பிரான் 350 ரைட்டு குமரனுக்கு 10 கிலோ டைகர் பிரான் 500 ரைட்டு”
- `tanglish_02` @ harbour/10: silent errors 1 → 0, correct bookings 0 → 0 — heard “குமரன்க்கு முப்பத்தி கார் ஜப்ரான் 500 ரேட்டு”
- `tanglish_02` @ harbour/5: silent errors 1 → 0, correct bookings 0 → 0 — heard “குமரன்க்கு முப்பத்தி கார் ஜப்ரான் 500 ரேட்டு”
- `tanglish_02` @ market/10: silent errors 1 → 0, correct bookings 0 → 0 — heard “குமரனுக்கு முப்பத்தி கார் ஜப்ரான் 500 ரேட்டு”
- `tanglish_02` @ traffic/5: silent errors 1 → 0, correct bookings 0 → 0 — heard “குமரன்க்கு முப்பத்தி கார் ஜப்ரான் 500 ரேட்டு”

Reading it:

- With the gate ON, all 5 noisy silent errors and the 1 clean one are gone. Four were `tanglish_02` (spoken `kg` heard as `கார்`): pre-3C booked them as `box`; now the unit falls back to the prawn SKU's `kg` at 0.75 unit confidence, so they are held for confirmation rather than booked. Two were `multi_09` (`ஐநூற்று 60` heard as `ஐநூற்றுக்கு 60`): the case-ending strip now reads 560, so they book correctly (+1 correct booking each).
- The four `market @ 5 dB` items that gain correct bookings (`multi_02`, `multi_13`, `multi_20`, `multi_21`) were merged clauses: Prisma misheard the `ரேட்டு` terminator (`வேட்டு`, `ரேக்கு`, `ரைட்டு`), so two trades reached the parser as one. Pre-3C the first booked and the second silently vanished. A buyer name in the dative form now starts a new clause, so all four parse into their two true trades. `multi_20`'s second trade is correctly a credit hold (18,000 + 24,000 exceeds Senthil's 22,000 headroom), so it adds no booking. Its buyer came back as `செந்திலி சிவக்கு`, which is not an exact alias: it is recognised because the buyer resolver scores it 0.84 against the 0.82 bar, a narrow margin. A merge with no recognisable second buyer is still held whole by the leftover-number check.
- With the gate OFF, silent errors also fell 7 → 0: the fixes removed the confident mistakes themselves rather than only hiding them behind the gate.
- Consequence for the headline: this run has no silent errors with the gate on *or* off, so it cannot show a gate benefit (see "Does the confidence gate help?"). The threshold sweep shows only the gate's cost: at τ = 0.82 it books 381 correct trades against 416 at τ = 0.5 on the same transcripts.

## STT latency spikes (Prisma-side stalls)

**Finding:** the ~10 s STT outliers (12 of 405 items, 3.0%, at 10.3–10.4 s; P50 is ~0.2 s) are an **intermittent Prisma-side stall**, not a bug in our client. Evidence: `benchmark/stt_latency_diagnosis.jsonl`, produced by `scripts/diagnose_stt_latency.py`, which replays each item's exact benchmark audio (cached speech, same noise seed, lead-in and tail) with client-side timing for every Prisma event.

Run (2026-10-31, one stream at a time, 72 live streams): the 12 spiking items plus 12 controls (the same utterances under a condition that had not spiked), 3 repeats each.

| streams | n | attempts | connect P50 / P95 ms | final transcript after last audio frame, P50 / P95 ms | Prisma-reported latency, P50 / P95 ms | drain P50 / P95 ms |
|---|---|---|---|---|---|---|
| normal | 68 | 1 every time | 202 / 451 | −341 / −184 (arrives during the tail) | 191 / 241 | 367 / 367 |
| stalled | 4 | 1 every time | 216 / 261 | 9,907 / 10,011 | 10,370 / 10,432 | 10,220 / 10,346 |

Ruling out each candidate:

- **Retries:** every stream, stalled or not, connected on the first attempt (no retry warnings in the 306-call re-record either).
- **`_drain_open_utterances` timeout:** its budget is `gnani_read_timeout_sec` = 15 s and it raises on expiry, failing the item; no item failed. In the stalls the drain simply waited until Prisma's transcript arrived (~10.2 s).
- **Trailing noise holding end-of-speech open:** clean items with a digitally silent tail stall too (`single_04`, `single_12`, `multi_16` in the sweep; `single_02` clean here), and noisy ones usually don't.
- **The audio itself:** the 36 replays of the originally stalling items stalled once (`multi_07` @ ice_crusher/5); three of the four stalls hit control items that never stalled before (`single_12` @ harbour/10, `single_02` @ clean, `multi_07` @ market/10).
- **Prisma:** in every stall `speech_start` arrived on time and the connection was normal, then the final transcript came ~9.9 s after the audio ended, with Prisma's own `latency` field at ~10.4 s. All four stalls fell inside one ~2-minute window (08:55:34–08:57:26), interleaved with normal streams on the same client, which points to a transient server-side condition with a ~10 s fixed delay. The stalled transcripts were still correct.

Impact: when it happens, the trader waits ~10 s longer for the decision. Our side can only bound it (`gnani_read_timeout_sec`) or report it; the fix belongs to Prisma.

## Barge-in stop time (live Timbre)

Measured with `scripts/measure_barge_in.py` (raw trials: `benchmark/barge_in_trials.jsonl`). Each trial synthesizes the firewall's real credit-hold alert (221 characters) with live Timbre v2.5, waits for the first audio byte, triggers `trigger_barge_in_abort()` at a seeded-random point inside the measured streaming window, and records **abort → Timbre socket closed** (`SynthesisTelemetry.abort_to_close_ms`, from the trigger until `ws.close()` returns). Trials where Timbre finished streaming before the trigger don't count. 2026-10-31, one trial at a time.

| code | counted trials | abort → socket closed, P50 | P95 | max | trials ≥ 10 s |
|---|---|---|---|---|---|
| before: abort checked only when the next frame arrives | 24 (of 33) | 1,056.3 ms | 1,146.2 ms | 1,216.2 ms | 0 |
| + wait for next frame **or** abort (`asyncio.wait`, `FIRST_COMPLETED`) | 24 (of 33) | 1,077.9 ms | 8,673.4 ms | 10,002.8 ms | 2 |
| + cap the closing handshake (`TIMBRE_CLOSE_TIMEOUT_SEC` = 0.05 s) | 24 (of 25) | **52.3 ms** | **52.5 ms** | 52.6 ms | 0 |

What the numbers showed: the `FIRST_COMPLETED` change works (abort → `close()` called dropped to 0.2–1.6 ms in a split-timing check) and is covered by a mocked-socket test where the next frame never arrives, but live Timbre streams frames often enough that the next-frame wait was never the cost. The cost was the WebSocket closing handshake: Timbre answers our close frame ~1 s late and sometimes not at all, when `websockets`' default 10 s `close_timeout` expires (the two 10 s trials). Since an aborted stream is discarded, the client now waits at most 50 ms for that reply before dropping the connection, so the stop time is bounded by that cap.

Timbre first byte (request → first audio byte) from the same trials: P50 375 / P95 525 ms (before, n = 33), 305 / 471 ms (n = 33), 357 / 422 ms (final, n = 25).

## Known limitations

- **In-range quantity digit errors are not caught pre-booking.** A dropped or added quantity digit that stays inside the 1–1,000 kg band (50 → 5 kg, 5 → 50 kg) looks like a normal trade, so the gate books it. They are mitigated, after booking, by the spoken read-back (the reply states quantity, unit, product and amount) and voice undo (reverses the last booked trade), which rely on the trader noticing. A check against each buyer's order history is deferred. `tests/test_gate_fault_injection.py` keeps both cases as strict expected failures, so the suite flags any change in this behavior.

## Speech-start clipping: VAD threshold sweep

Prompted by a live mic test where `குமரனுக்கு` came back as `அமரனுக்கு`. **Lower thresholds showed no benefit on these recordings, and end-of-speech timeouts rise as the threshold falls, so the recommendation is to keep 0.78.** No default was changed. Recorded live 2026-11-01 (0.78 re-uses the 2026-10-31 recordings); same 225 items for each threshold: clean plus all four profiles at 5 dB. Results: `benchmark/vad_sweep/`; re-score any row with `run_eval.py --analyze-only --vad-threshold T --conditions clean,harbour:5,market:5,traffic:5,ice_crusher:5`.

| vad_threshold | buyer correct, clean | buyer correct, 5 dB | first word exact, clean | first word exact, 5 dB | no-transcript timeouts, first pass | items still failed after a re-run | first `speech_start` after stream start, P50 | false detections on speech-free audio |
|---|---|---|---|---|---|---|---|---|
| 0.78 (default) | 100.0% | 100.0% | 100.0% | 91.5% | 0 | 0 | not recorded for this set | 0 of 29 |
| 0.7 | 100.0% | 99.6% | 100.0% | 90.9% | 0 | 0 | 700 ms | 0 of 30 |
| 0.6 | 100.0% | 99.6% | 100.0% | 91.4% | 1 | 2 | 693 ms | 0 of 27 |
| 0.5 | 100.0% | 99.6% | 100.0% | 92.4% | 5 | 6 | 694 ms | 0 of 27 |

Accuracy covers the items that produced a transcript. *First word exact* excludes the Tanglish items, whose spelling legitimately differs. *False detections* counts any `speech_start` or transcript on digital silence or a 5 dB noise bed with the speech subtracted; streams lost to a Prisma server fault aren't counted. Of the items still failing, all but one (a timeout at 0.5) are Prisma server faults rather than threshold effects, so the correct-bookings gap they leave (237, 236, 234, 228) isn't a fair comparison and isn't used here.

Limits of this evidence:

- **The clipping did not reproduce here.** Every threshold, including 0.78, gets the first word of every clean item right. These are Timbre recordings with a clean onset and a 300 ms lead-in, so this sweep shows no gain from lowering the threshold; it cannot show lowering wouldn't help a real voice on a real mic. That needs the raw mic audio of a clipped utterance.
- **The header is honoured only at extremes.** In a mixed-order test (`extreme_thresholds.jsonl`: 20 streams each at 0.05 and 0.78, 16 at 0.99), 0.05 failed 16 of 20 streams, mostly with no transcript within 15 s, while 0.78 failed none and 0.99 failed 1 and still detected speech at normal timing. So Prisma reads the value, but across 0.5–0.99 speech is detected at about the same time.
- **Prisma was unstable during this run.** 40 of the 46 first-pass failures were Prisma's own `A child process terminated abruptly` frames, none of which appeared in the earlier 306-call recording, and stalls reached 10 of 20 streams at 0.78 in the mixed-order test (3% in the benchmark). Those failures are not attributed to any threshold; the table counts only what survived the re-run.

**Browser client:** with the real page code, a stubbed mic and a fake Prisma, frames go out at a steady 64 ms (1,024 bytes, max gap 64.3 ms over 38 frames), so nothing is dropped once capture runs, and a server test confirms bytes reach Prisma intact and in order. Frames are discarded only while the WebSocket isn't open. There is one real gap: "Speak now" appears when Prisma connects, but capture starts only once the mic is up (93 ms later with an instant stub; a real device or permission prompt adds an unmeasured amount). That can only clip the first words after pressing Start, not a later utterance. Chrome's echo cancellation and default auto gain could also soften an onset; a stub mic can't test that.

## Assembler: reply latency before and after

`to_first_audio_ms` from the gateway's JSON timing lines, measured with `scripts/measure_live_path.py` (real gateway, Prisma and Timbre; cached speech streamed over `/ws/live-audio` like the browser; 12 utterances; `benchmark/live_path_timing.jsonl`). The clock starts when the first STT segment arrives, so Prisma's own latency is not included.

| assembler | n | `to_first_audio_ms` P50 | P95 | min | max | `assemble` span P50 |
|---|---|---|---|---|---|---|
| before: fixed 1.5 s wait | 12 | 1,828 ms | 2,143 ms | 1,786 ms | 2,463 ms | 1,501.7 ms |
| after: commit complete trades at once | 12 | 392 ms | 508 ms | 301 ms | 528 ms | 1.3 ms |

What this costs: text that isn't a complete trade now waits 2.5 s instead of 1.5 s, including barge-in overrides and voice undo, and that value is a judgement call with no live pause data behind it. Every benchmark stream arrived as one Prisma segment, so these numbers don't exercise a trader pausing after a rate word mid-utterance: the next trade would become its own turn, and its arrival would barge in on the first reply.
