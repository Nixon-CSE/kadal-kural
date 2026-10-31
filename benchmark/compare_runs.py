"""
Before/after comparison of two run_eval.py results CSVs scored on the *same* cached
transcripts (e.g. an older code version from a git worktree run with --analyze-only and a
shared --cache-dir). Refuses to compare runs whose transcripts differ.

Usage:
    python benchmark/compare_runs.py BEFORE.csv AFTER.csv --before-label pre-3C --after-label 3C
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

CLEAN = "clean"
Row = Dict[str, str]
CellKey = Tuple[str, str]  # (profile, snr label)


@dataclass(frozen=True)
class CellTotals:
    """Pooled gate outcomes for one group of rows."""

    trades: int
    gated_booked: int
    gated_errors: int
    gated_correct: int
    ungated_errors: int
    rate_correct: int
    unit_correct: int


def load_rows(path: Path) -> Dict[Tuple[str, str, str], Row]:
    with path.open(encoding="utf-8", newline="") as fh:
        return {(r["utterance_id"], r["profile"], r["snr_db"]): r for r in csv.DictReader(fh)}


def _int(row: Row, col: str) -> int:
    return int(row[col]) if row[col] else 0


def totals(rows: Sequence[Row]) -> CellTotals:
    scored = [r for r in rows if not r["error"]]
    return CellTotals(
        trades=sum(_int(r, "n_truth_trades") for r in scored),
        gated_booked=sum(_int(r, "gated_booked") for r in scored),
        gated_errors=sum(_int(r, "gated_silent_errors") for r in scored),
        gated_correct=sum(_int(r, "gated_correct_bookings") for r in scored),
        ungated_errors=sum(_int(r, "ungated_silent_errors") for r in scored),
        rate_correct=sum(_int(r, "rate_correct") for r in scored),
        unit_correct=sum(_int(r, "unit_correct") for r in scored),
    )


def _cell_label(key: CellKey) -> str:
    profile, snr = key
    return "clean (no noise)" if profile == CLEAN else f"{profile} @ {snr} dB"


def _arrow(before: int, after: int) -> str:
    return f"{before} → {after}" if before != after else f"{after}"


def _pct_arrow(before: int, after: int, trades: int) -> str:
    b, a = 100.0 * before / trades, 100.0 * after / trades
    return f"{b:.1f}% → {a:.1f}%" if before != after else f"{a:.1f}%"


def render_table(
    before: Dict[Tuple[str, str, str], Row],
    after: Dict[Tuple[str, str, str], Row],
    before_label: str,
    after_label: str,
) -> str:
    """Markdown table: one line per condition, plus the all-noisy roll-up."""
    if before.keys() != after.keys():
        raise ValueError("runs cover different items; score the same --conditions in both")
    mismatched = [k for k in before if before[k]["transcript"] != after[k]["transcript"]]
    if mismatched:
        raise ValueError(f"{len(mismatched)} item(s) were scored on different transcripts, e.g. {mismatched[0]}")

    cells: Dict[CellKey, List[Tuple[Row, Row]]] = {}
    for key in before:
        cells.setdefault((key[1], key[2]), []).append((before[key], after[key]))
    ordered = sorted(cells, key=lambda k: (k[0] != CLEAN, k[0], -float(k[1]) if k[1] != CLEAN else 0.0))
    noisy = [pair for key in ordered if key[0] != CLEAN for pair in cells[key]]

    lines = [
        f"| Condition | trades | silent errors, gate ON ({before_label} → {after_label}) "
        f"| correct bookings, gate ON | booked, gate ON | silent errors, gate OFF | rate correct | unit correct |",
        "|---|---|---|---|---|---|---|---|",
    ]

    def line(label: str, pairs: Sequence[Tuple[Row, Row]]) -> str:
        b, a = totals([p[0] for p in pairs]), totals([p[1] for p in pairs])
        return (
            f"| {label} | {a.trades} | {_arrow(b.gated_errors, a.gated_errors)} "
            f"| {_arrow(b.gated_correct, a.gated_correct)} | {_arrow(b.gated_booked, a.gated_booked)} "
            f"| {_arrow(b.ungated_errors, a.ungated_errors)} "
            f"| {_pct_arrow(b.rate_correct, a.rate_correct, a.trades)} "
            f"| {_pct_arrow(b.unit_correct, a.unit_correct, a.trades)} |"
        )

    lines += [line(_cell_label(key), cells[key]) for key in ordered]
    lines.append(line("**all noisy cells**", noisy))
    return "\n".join(lines)


def changed_items(
    before: Dict[Tuple[str, str, str], Row], after: Dict[Tuple[str, str, str], Row]
) -> List[str]:
    """Items whose gate-ON silent errors or correct bookings changed, for the evidence list."""
    out: List[str] = []
    for key in sorted(before):
        b, a = before[key], after[key]
        if (_int(b, "gated_silent_errors"), _int(b, "gated_correct_bookings")) != (
            _int(a, "gated_silent_errors"), _int(a, "gated_correct_bookings")
        ):
            out.append(
                f"`{key[0]}` @ {key[1]}/{key[2]}: silent errors {_int(b, 'gated_silent_errors')} → "
                f"{_int(a, 'gated_silent_errors')}, correct bookings {_int(b, 'gated_correct_bookings')} → "
                f"{_int(a, 'gated_correct_bookings')} — heard “{a['transcript']}”"
            )
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1] if __doc__ else None)
    p.add_argument("before", type=Path)
    p.add_argument("after", type=Path)
    p.add_argument("--before-label", default="before")
    p.add_argument("--after-label", default="after")
    p.add_argument("--list-changes", action="store_true", help="also list every item whose outcome changed")
    args = p.parse_args(argv)
    before, after = load_rows(args.before), load_rows(args.after)
    out = [render_table(before, after, args.before_label, args.after_label)]
    if args.list_changes:
        out += ["", *[f"- {c}" for c in changed_items(before, after)]]
    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
