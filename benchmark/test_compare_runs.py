"""Before/after comparison of two results CSVs scored on the same transcripts."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

import pytest

from benchmark.compare_runs import changed_items, load_rows, render_table
from benchmark.run_eval import CSV_COLUMNS


def _write(path: Path, rows: List[Dict[str, object]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow({c: r.get(c, "") for c in CSV_COLUMNS})
    return path


def _row(profile: str, snr: str, transcript: str, errors: int, correct: int) -> Dict[str, object]:
    return {
        "utterance_id": "u1", "profile": profile, "snr_db": snr, "n_truth_trades": 1,
        "gated_booked": errors + correct, "gated_silent_errors": errors, "gated_correct_bookings": correct,
        "ungated_silent_errors": errors, "rate_correct": correct, "unit_correct": 1, "transcript": transcript,
    }


def test_table_shows_before_and_after_per_condition(tmp_path: Path) -> None:
    before = load_rows(_write(tmp_path / "b.csv", [_row("harbour", "10", "heard", 1, 0)]))
    after = load_rows(_write(tmp_path / "a.csv", [_row("harbour", "10", "heard", 0, 1)]))
    table = render_table(before, after, "old", "new")
    assert "| harbour @ 10 dB | 1 | 1 → 0 | 0 → 1 | 1 | 1 → 0 | 0.0% → 100.0% | 100.0% |" in table
    assert "| **all noisy cells** | 1 | 1 → 0 |" in table
    assert changed_items(before, after) == [
        "`u1` @ harbour/10: silent errors 1 → 0, correct bookings 0 → 1 — heard “heard”"
    ]


def test_refuses_runs_scored_on_different_transcripts(tmp_path: Path) -> None:
    before = load_rows(_write(tmp_path / "b.csv", [_row("harbour", "10", "one", 0, 1)]))
    after = load_rows(_write(tmp_path / "a.csv", [_row("harbour", "10", "two", 0, 1)]))
    with pytest.raises(ValueError, match="different transcripts"):
        render_table(before, after, "old", "new")
