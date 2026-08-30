"""Tests for the frame_watch-driven mid-game region-flip detector."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

DAEMON_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DAEMON_DIR))

from achievementbox.region_watch import (  # noqa: E402
    RegionMonitor, classify_frame_rate)


class ClassifyFrameRateTest(unittest.TestCase):
    def test_ntsc_band(self):
        for rate in (55.0, 59.7, 60.3, 74.9):
            self.assertEqual(classify_frame_rate(rate), "NTSC", rate)

    def test_pal_band(self):
        for rate in (40.0, 49.7, 50.3, 54.9):
            self.assertEqual(classify_frame_rate(rate), "PAL", rate)

    def test_no_verdict_below_forty(self):
        # v-interrupts disabled (loading screens) or pre-frame_watch
        # gateware: a frozen counter must never produce a verdict.
        for rate in (0.0, 12.0, 39.9):
            self.assertIsNone(classify_frame_rate(rate), rate)

    def test_no_verdict_above_seventy_five(self):
        # something other than vblank is reading the vector address
        for rate in (75.0, 120.0, 512.0):
            self.assertIsNone(classify_frame_rate(rate), rate)


def feed_rate(mon: RegionMonitor, rate_hz: float, samples: int,
              start_count: int = 0, start_time: float = 100.0,
              interval: float = 0.5) -> list[bool]:
    """Feed `samples` counter readings simulating a steady frame rate."""
    results = []
    count, now = start_count, start_time
    for _ in range(samples):
        results.append(mon.feed(count & 0xFF, now))
        count += round(rate_hz * interval)
        now += interval
    return results


class RegionMonitorTest(unittest.TestCase):
    def test_steady_ntsc_never_trips(self):
        mon = RegionMonitor(expected="NTSC", debounce=4)
        self.assertNotIn(True, feed_rate(mon, 60.0, 40))
        self.assertFalse(mon.tripped)

    def test_pal_flip_trips_after_debounce(self):
        mon = RegionMonitor(expected="NTSC", debounce=4)
        self.assertNotIn(True, feed_rate(mon, 60.0, 10))
        # switch flipped: 50Hz cadence from here on. First PAL delta is
        # sample 11; the fourth consecutive PAL verdict trips.
        results = feed_rate(mon, 50.0, 6, start_count=300, start_time=200.0)
        self.assertEqual(results.index(True), 4)  # primes on sample 1
        self.assertTrue(mon.tripped)

    def test_trips_exactly_once(self):
        mon = RegionMonitor(expected="NTSC", debounce=2)
        results = feed_rate(mon, 50.0, 12)
        self.assertEqual(results.count(True), 1)
        # tripped stays latched; further samples return False
        self.assertFalse(mon.feed(0, 1000.0))
        self.assertTrue(mon.tripped)

    def test_no_verdict_resets_streak(self):
        mon = RegionMonitor(expected="NTSC", debounce=3)
        now = [100.0]
        count = [0]

        def step(rate):
            count[0] += round(rate * 0.5)
            now[0] += 0.5
            return mon.feed(count[0] & 0xFF, now[0])

        mon.feed(0, now[0])  # prime
        self.assertFalse(step(50.0))
        self.assertFalse(step(50.0))
        self.assertFalse(step(0.0))    # frozen counter: no verdict, reset
        self.assertFalse(step(50.0))
        self.assertFalse(step(50.0))
        self.assertTrue(step(50.0))    # fresh streak of 3 trips

    def test_first_sample_only_primes(self):
        mon = RegionMonitor(expected="NTSC", debounce=1)
        self.assertFalse(mon.feed(200, 100.0))
        self.assertFalse(mon.tripped)

    def test_counter_wraparound(self):
        # 8-bit counter wraps every ~4s at 60Hz; deltas are mod 256
        mon = RegionMonitor(expected="NTSC", debounce=4)
        self.assertNotIn(True, feed_rate(mon, 60.0, 40, start_count=250))
        self.assertFalse(mon.tripped)

    def test_bad_clock_sample_is_ignored(self):
        mon = RegionMonitor(expected="NTSC", debounce=2)
        mon.feed(0, 100.0)
        self.assertFalse(mon.feed(25, 100.0))   # dt == 0: no verdict
        self.assertFalse(mon.feed(50, 99.0))    # clock went backwards
        self.assertFalse(mon.tripped)

    def test_pal_console_expected_pal_never_trips(self):
        mon = RegionMonitor(expected="PAL", debounce=4)
        self.assertNotIn(True, feed_rate(mon, 50.0, 40))
        self.assertFalse(mon.tripped)


if __name__ == "__main__":
    unittest.main()


def _feed_cadence(mon, rates, seconds=1.0):
    """Drive the monitor at the given per-second frame rates."""
    count, now, trips = 0, 0.0, []
    for rate in rates:
        count = (count + round(rate * seconds)) % 256
        now += seconds
        trips.append(mon.feed(count, now))
    return trips


class LearnedBaselineTest(unittest.TestCase):
    """Without an explicit `expected`, the monitor adopts the first real
    verdict as its baseline. Its job is spotting a *change* of region,
    not enforcing one, and the $A10001 latch is not reliably readable at
    session start -- the running game may not have touched it yet."""

    def test_steady_pal_console_never_trips(self):
        mon = RegionMonitor()
        self.assertEqual(_feed_cadence(mon, [50.0] * 20), [False] * 20)
        self.assertFalse(mon.tripped)

    def test_steady_ntsc_console_never_trips(self):
        mon = RegionMonitor()
        self.assertEqual(_feed_cadence(mon, [60.0] * 20), [False] * 20)
        self.assertFalse(mon.tripped)

    def test_flip_away_from_learned_baseline_trips(self):
        mon = RegionMonitor(debounce=4)
        trips = _feed_cadence(mon, [50.0] * 6 + [60.0] * 6)
        self.assertTrue(any(trips), "a PAL->NTSC flip must trip")
        self.assertEqual(trips.count(True), 1, "trips exactly once")

    def test_no_verdict_samples_do_not_become_the_baseline(self):
        """Boot and loading screens disable v-interrupts, yielding rates
        below the classifier's floor. Latching one of those as the
        baseline would make the first real verdict look like a flip."""
        mon = RegionMonitor(debounce=4)
        trips = _feed_cadence(mon, [20.0, 25.0, 33.0] + [50.0] * 12)
        self.assertFalse(any(trips))
        self.assertFalse(mon.tripped)

    def test_explicit_expected_still_honoured(self):
        """Callers that know the region can still say so."""
        mon = RegionMonitor(expected="NTSC", debounce=4)
        self.assertTrue(any(_feed_cadence(mon, [50.0] * 6)))
