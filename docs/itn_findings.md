# Prisma v2.5 findings

Raw evidence for the Tamil ITN work lives in `tamil_itn_probe_results.jsonl`
(`scripts/probe_tamil_itn.py`). This file records what the benchmark work added.

## Gate redesign

### Does Prisma report confidence? No.

One raw `transcript` event, logged in full by `scripts/probe_prisma_confidence.py`
(clean `single_01`, live call 2026-10-31):

```
{'type': 'transcript', 'text': 'செந்திலுக்கு 25 பாக்ஸ் வஞ்சரம் 250 ரேட்டு',
 'audio_duration_ms': 3456.0, 'segment_id': '...-seg-1', 'segment_index': 1,
 'utterance_id': 'u39cd3082', 'is_final': True, 'latency': 174,
 'timestamp': '2026-10-31T00:40:53.196123+00:00',
 'output': {'literal': 'செந்திலுக்கு இருபத்தைந்து பாக்ஸ் வஞ்சரம் இருநூற்று ஐம்பது ரேட்டு'}}
```

There is no per-word or per-segment confidence field. This is one event from one
utterance, so a field that only appears for some audio cannot be ruled out; the client
now logs every raw event at DEBUG so it would show up. `output.literal` is the same
text with numbers spelled as words. It is not a confidence, but it is a second rendering
of the numbers that could be cross-checked against `text`; that is not used yet.

Consequence: a misheard amount cannot be flagged from STT confidence. The gate has to
judge quantity and rate by plausibility (catalog ranges), described below.
