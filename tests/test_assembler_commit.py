"""The assembler commits complete trades at once and waits for fragments, on a fake clock."""

from __future__ import annotations

import asyncio
from typing import List

import pytest

from kadal_kural.config import ASSEMBLER_INCOMPLETE_WINDOW_SEC, NS_PER_MS, AppSettings
from kadal_kural.domain.matcher import BilingualCatalogMatcher
from kadal_kural.infrastructure.gnani_client import AssembledUtterance, MultiSegmentTradeAssembler

COMPLETE = "குமரனுக்கு 5 கிலோ டைகர் பிரான் 560 ரேட்டு"


class FakeTime:
    """A nanosecond clock plus a sleep that only ends when the test advances past its deadline."""

    def __init__(self) -> None:
        self.now_ns = 1_000 * NS_PER_MS
        self.waits: List[float] = []
        self._sleepers: List[tuple[int, asyncio.Event]] = []

    def __call__(self) -> int:
        return self.now_ns

    async def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        wake = asyncio.Event()
        self._sleepers.append((self.now_ns + int(seconds * 1000) * NS_PER_MS, wake))
        await wake.wait()

    async def advance_ms(self, ms: int) -> None:
        self.now_ns += ms * NS_PER_MS
        for deadline, wake in self._sleepers:
            if deadline <= self.now_ns:
                wake.set()
        await asyncio.sleep(0)  # let woken tasks run
        await asyncio.sleep(0)
        await asyncio.sleep(0)


@pytest.fixture(scope="module")
def matcher() -> BilingualCatalogMatcher:
    return BilingualCatalogMatcher(AppSettings().catalog_path)


def _assembler(matcher: BilingualCatalogMatcher, time_: FakeTime, committed: List[AssembledUtterance]) -> MultiSegmentTradeAssembler:
    async def _commit(utterance: AssembledUtterance) -> None:
        committed.append(utterance)

    return MultiSegmentTradeAssembler(
        ASSEMBLER_INCOMPLETE_WINDOW_SEC, _commit, clock=time_,
        is_complete=matcher.is_complete_utterance, sleep=time_.sleep,
    )


async def test_complete_trade_commits_without_waiting(matcher: BilingualCatalogMatcher) -> None:
    time_ = FakeTime()
    committed: List[AssembledUtterance] = []
    assembler = _assembler(matcher, time_, committed)
    received = time_()
    await assembler.ingest_segment(COMPLETE, 180.0)
    await asyncio.sleep(0)
    assert time_.waits == []
    assert [u.text for u in committed] == [COMPLETE]
    assert time_() - committed[0].first_segment_ns == 0 and committed[0].first_segment_ns == received


async def test_fragment_waits_the_longer_window_then_commits(matcher: BilingualCatalogMatcher) -> None:
    time_ = FakeTime()
    committed: List[AssembledUtterance] = []
    assembler = _assembler(matcher, time_, committed)
    await assembler.ingest_segment("குமரனுக்கு 5 கிலோ டைகர் பிரான்", 180.0)
    await asyncio.sleep(0)
    assert time_.waits == [ASSEMBLER_INCOMPLETE_WINDOW_SEC]
    await time_.advance_ms(int(ASSEMBLER_INCOMPLETE_WINDOW_SEC * 1000) - 1)
    assert committed == []
    await time_.advance_ms(1)
    assert [u.text for u in committed] == ["குமரனுக்கு 5 கிலோ டைகர் பிரான்"]


async def test_segment_that_completes_the_text_commits_at_once(matcher: BilingualCatalogMatcher) -> None:
    time_ = FakeTime()
    committed: List[AssembledUtterance] = []
    assembler = _assembler(matcher, time_, committed)
    await assembler.ingest_segment("குமரனுக்கு 5 கிலோ", 180.0)
    await time_.advance_ms(700)
    await assembler.ingest_segment("டைகர் பிரான் 560 ரேட்டு", 200.0)
    await asyncio.sleep(0)
    assert [u.text for u in committed] == [COMPLETE]
    assert committed[0].segment_latencies_ms == (180.0, 200.0)
    await time_.advance_ms(10_000)  # the cancelled wait never commits anything again
    assert len(committed) == 1


@pytest.mark.parametrize(
    ("text", "complete"),
    [
        (COMPLETE, True),
        ("குமரனுக்கு 5 கிலோ டைகர் பிரான் ரேட்டு 560", True),
        ("செந்திலுக்கு 10 கிலோ வஞ்சரம் 800 ரேட்டு குமரனுக்கு 5 கிலோ டைகர் பிரான் 560 ரேட்டு", True),
        ("குமரனுக்கு 5 கிலோ டைகர் பிரான் 560", False),  # no terminator
        ("குமரனுக்கு 5 கிலோ டைகர் பிரான் ரேட்டு", False),  # terminator, no rate
        ("செந்திலுக்கு 10 கிலோ வஞ்சரம் 800 ரேட்டு குமரனுக்கு 5 கிலோ", False),  # second trade unfinished
        ("செந்திலுக்கு 25 கிலோ மட்டும் போடு", False),  # barge-in override
        ("கடைசி ஆர்டர் கேன்சல்", False),  # voice undo
        ("", False),
    ],
)
def test_what_counts_as_complete(text: str, complete: bool, matcher: BilingualCatalogMatcher) -> None:
    assert matcher.is_complete_utterance(text) is complete
