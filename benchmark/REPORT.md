# Kadal Kural — Noise & Silent-Error Benchmark

Generated 2026-10-31 by `benchmark/run_eval.py` — 45 utterances × conditions [clean,harbour:10,harbour:5,market:10,market:5,traffic:10,traffic:5,ice_crusher:10,ice_crusher:5] = 405 items.

## Method (read this before the numbers)

- **Speaker:** Gnani Timbre v2.5 synthesizes each corpus utterance (once, cached). This is a repeatable stand-in for a human speaker, not a recording of a trader: real accents, disfluencies and Lombard effect are **not** represented.
- **Noise:** *synthetic*, spectrally shaped beds (harbour/market/traffic/ice-crusher; see `benchmark/noise_profiles.py`), mixed at a target **RMS SNR** over the speech segment. A noise-only lead-in and tail at the same absolute level surround the speech so the VAD must end the utterance through the noise. These are not field recordings of a harbour.
- **Pipeline:** 8 kHz PCM, 1,024-byte paced frames → Prisma v2.5 → merge segments → normalizer → matcher → firewall on a fresh catalog-seeded ledger per utterance (τ = 0.82 with the gate; τ = 0 without).
- **WER:** `jiwer`. *Normalized* passes both sides through `normalize_hybrid_tamil_numerals` (the corpus spells numbers as words; Prisma emits digits, so *raw* WER is inflated by formatting). Means over utterances.
- **Entity accuracy:** pooled over ground-truth trades; extracted intents are matched to trades by best field overlap.
- **Silent Financial Error Rate (SFER):** booked trades (`BOOKED` / `BOOKED_AFTER_BARGE_IN`) that match no ground-truth trade, divided by ground-truth trades attempted. Omitted trades are not silent errors. Without the gate, structural checks (unresolved buyer/SKU/rate/qty) still block booking.
- **Latency:** *STT* is the latency Prisma reports per segment (mean per utterance); *firewall* is the measured wall time of `evaluate_utterance` (normalizer + matcher + decision + SQLite write). Timbre time-to-first-byte and barge-in flush are measured in Task 4.

## Results

| Condition | n | WER (norm.) | WER (raw) | buyer | SKU | qty | unit | rate | STT P50 / P95 ms | firewall P50 / P95 ms | SFER gate ON | SFER gate OFF |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| clean (no noise) | 45 | 10.1% | 25.4% | 98.6% | 95.7% | 95.7% | 95.7% | 92.9% | 236 / 437 | 0.23 / 0.32 | 1.4% (1/70) | 2.9% (2/70) |
| harbour @ 10 dB | 45 | 10.0% | 26.0% | 98.6% | 97.1% | 97.1% | 95.7% | 97.1% | 210 / 402 | 0.13 / 0.15 | 1.4% (1/70) | 1.4% (1/70) |
| harbour @ 5 dB | 45 | 9.8% | 25.8% | 100.0% | 97.1% | 97.1% | 97.1% | 97.1% | 209 / 307 | 0.13 / 0.15 | 1.4% (1/70) | 1.4% (1/70) |
| market @ 10 dB | 45 | 16.4% | 32.1% | 98.6% | 97.1% | 97.1% | 95.7% | 95.7% | 205 / 3617 | 0.13 / 0.16 | 1.4% (1/70) | 1.4% (1/70) |
| market @ 5 dB | 45 | 21.4% | 35.8% | 97.1% | 92.9% | 92.9% | 94.3% | 91.4% | 217 / 383 | 0.12 / 0.16 | 1.4% (1/70) | 1.4% (1/70) |
| traffic @ 10 dB | 45 | 10.3% | 25.9% | 100.0% | 97.1% | 97.1% | 97.1% | 95.7% | 205 / 10316 | 0.12 / 0.15 | 1.4% (1/70) | 2.9% (2/70) |
| traffic @ 5 dB | 45 | 10.7% | 26.4% | 98.6% | 95.7% | 95.7% | 95.7% | 95.7% | 200 / 10055 | 0.13 / 0.15 | 1.4% (1/70) | 1.4% (1/70) |
| ice_crusher @ 10 dB | 45 | 13.3% | 28.7% | 98.6% | 94.3% | 95.7% | 95.7% | 95.7% | 200 / 1398 | 0.12 / 0.15 | 0.0% (0/70) | 1.4% (1/70) |
| ice_crusher @ 5 dB | 45 | 15.6% | 30.8% | 98.6% | 95.7% | 97.1% | 95.7% | 95.7% | 206 / 8327 | 0.12 / 0.16 | 0.0% (0/70) | 2.9% (2/70) |

### Roll-up by SNR (all four noise profiles)

| Condition | n | WER (norm.) | WER (raw) | buyer | SKU | qty | unit | rate | STT P50 / P95 ms | firewall P50 / P95 ms | SFER gate ON | SFER gate OFF |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all profiles @ 10 dB | 180 | 12.5% | 28.2% | 98.9% | 96.4% | 96.8% | 96.1% | 96.1% | 204 / 10085 | 0.12 / 0.15 | 1.1% (3/280) | 1.8% (5/280) |
| all profiles @ 5 dB | 180 | 14.4% | 29.7% | 98.6% | 95.4% | 95.7% | 95.7% | 95.0% | 206 / 10269 | 0.12 / 0.16 | 1.1% (3/280) | 1.8% (5/280) |
| **all noisy cells** | 360 | 13.5% | 28.9% | 98.8% | 95.9% | 96.2% | 95.9% | 95.5% | 206 / 10268 | 0.12 / 0.16 | 1.1% (6/560) | 1.8% (10/560) |

## Does the confidence gate help?

**Yes, measurably.** Across all noisy cells the gate (τ = 0.82) cut silent financial errors from 10 to 6 of 560 attempted trades (1.8% → 1.1%).

### Threshold sensitivity (all noisy cells, in-sample)

τ was *not* tuned on a held-out set; this table is the same data the headline uses, so treat it as sensitivity, not as an out-of-sample claim.

| τ | booked | silent errors | SFER | correct bookings |
|---|---|---|---|---|
| 0.5 | 419 | 10 | 1.8% | 409 |
| 0.6 | 415 | 10 | 1.8% | 405 |
| 0.7 | 407 | 6 | 1.1% | 401 |
| 0.8 | 389 | 6 | 1.1% | 383 |
| 0.82 (production) | 386 | 6 | 1.1% | 380 |
| 0.9 | 356 | 2 | 0.4% | 354 |
| 0.95 | 307 | 1 | 0.2% | 306 |

## Failure modes

Across 360 noisy runs the weakest extracted entity was **rate** (95.5% correct) and the worst cell by normalized WER was **market @ 5 dB** (21.4%). 0 item(s) failed outright (API error or timeout) and are excluded from the averages. Silent errors that survived the gate (confident but wrong), spoken → heard: `multi_09` @ clean/clean dB: “செந்தில் சீஃபுட்ஸ்க்கு பதினைந்து கிலோ டைகர் பிரான் ஐநூற்று 60 ரேட்டு குமரனுக்கு 60 கிலோ டைகர் பிரான் எழுநூற்றி 40 ரேட்டு” → “செந்தில் சீஃபுட்ஸ் 15 கிலோ டைகர் பிரான் ஐநூற்றுக்கு 60 ரேட்டு குமரனுக்கு 60 கிலோ டைகர் பிரான் எழுநூற்றி 40 ரேட்டு”; `tanglish_02` @ harbour/10 dB: “Kumaran ku muppathi kg Prawn 500 ரேட்டு” → “குமரன்க்கு முப்பத்தி கார் ஜப்ரான் 500 ரேட்டு”; `tanglish_02` @ harbour/5 dB: “Kumaran ku muppathi kg Prawn 500 ரேட்டு” → “குமரன்க்கு முப்பத்தி கார் ஜப்ரான் 500 ரேட்டு”. Caveats: synthetic noise and a synthetic speaker bound how far these numbers transfer to a real harbour; the corpus uses two buyers and two SKUs, so entity accuracy is easier than it would be against a large catalog.
