import unittest
from unittest.mock import Mock, patch
from premium5.timing import ReferenceTick, Governor, _CycleTimer, _CycleTimerSample


class GovernorTests(unittest.TestCase):

    # reset

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_reset_clears_real_mhz(self, mock_mono):
        g = Governor(4_190_000)
        g.advance(4_190_000)
        mock_mono.return_value = 1.0
        g.reset()
        self.assertEqual(g.real_mhz, 0.0)

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_reset_clears_potential_mhz(self, mock_mono):
        g = Governor(4_190_000)
        g.advance(4_190_000)
        mock_mono.return_value = 0.5
        g.batch()
        g.reset()
        self.assertEqual(g.potential_mhz, 0.0)

    # throttle

    @patch('premium5.timing.time.sleep')
    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_throttle_sleeps_correct_amount(self, mock_mono, mock_sleep):
        g = Governor(4_190_000)
        g.advance(4_190_000)
        mock_mono.return_value = 0.5
        g.throttle()
        mock_sleep.assert_called_once()
        delay = mock_sleep.call_args[0][0]
        self.assertAlmostEqual(delay, 0.5)

    @patch('premium5.timing.time.sleep')
    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_throttle_no_sleep_when_behind(self, mock_mono, mock_sleep):
        g = Governor(4_190_000)
        g.advance(4_190_000)
        mock_mono.return_value = 2.0
        g.throttle()
        mock_sleep.assert_called_once_with(0.0)

    # real_mhz

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_real_mhz_starts_at_zero(self, mock_mono):
        g = Governor(4_190_000)
        self.assertEqual(g.real_mhz, 0.0)

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_real_mhz_after_one_second(self, mock_mono):
        g = Governor(4_190_000)
        g.advance(4_190_000)
        mock_mono.return_value = 1.0
        self.assertAlmostEqual(g.real_mhz, 4.19)

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_real_mhz_half_speed(self, mock_mono):
        g = Governor(4_190_000)
        g.advance(2_095_000)
        mock_mono.return_value = 1.0
        self.assertAlmostEqual(g.real_mhz, 2.095)

    # potential_mhz

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_potential_mhz_starts_at_zero(self, mock_mono):
        g = Governor(4_190_000)
        self.assertEqual(g.potential_mhz, 0.0)

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_potential_mhz_after_batch(self, mock_mono):
        g = Governor(4_190_000)
        g.advance(4_190_000)
        mock_mono.return_value = 0.5
        g.batch()
        self.assertAlmostEqual(g.potential_mhz, 8.38)

    @patch('premium5.timing.time.sleep')
    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_potential_mhz_excludes_sleep(self, mock_mono, mock_sleep):
        g = Governor(4_190_000)

        # batch 1: advance cycles in 0.5s, then throttle sleeps to 1.0s
        g.advance(4_190_000)
        mock_mono.return_value = 0.5
        g.throttle()
        mock_mono.return_value = 1.0

        # batch 2: snapshot captures batch 1
        g.batch()

        # potential should reflect 0.5s of work, not 1.0s total
        self.assertAlmostEqual(g.potential_mhz, 8.38)

    # delay_seconds

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_delay_when_ahead_of_schedule(self, mock_mono):
        g = Governor(4_190_000)
        g.advance(4_190_000)
        mock_mono.return_value = 0.5
        self.assertAlmostEqual(g._delay_seconds(), 0.5)

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_delay_when_on_schedule(self, mock_mono):
        g = Governor(4_190_000)
        g.advance(4_190_000)
        mock_mono.return_value = 1.0
        self.assertEqual(g._delay_seconds(), 0.0)

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_delay_when_behind_schedule(self, mock_mono):
        g = Governor(4_190_000)
        g.advance(4_190_000)
        mock_mono.return_value = 2.0
        self.assertEqual(g._delay_seconds(), 0.0)


class ReferenceTickTests(unittest.TestCase):

    # ctor

    def test_rejects_system_clock_below_1mhz(self):
        with self.assertRaises(ValueError):
            ReferenceTick(500_000)

    def test_accepts_system_clock_at_1mhz(self):
        ReferenceTick(1_000_000)

    # add_listener

    def test_no_duplicate_listeners(self):
        rt = ReferenceTick(4_190_000)
        listener = type('L', (), {'tick_1mhz': lambda self, t: None})()
        rt.add_listener(listener)
        rt.add_listener(listener)
        self.assertEqual(len(rt._listeners), 1)

    # advance

    def test_fires_listener(self):
        rt = ReferenceTick(4_190_000)
        ticks = []
        class Listener:
            def tick_1mhz(self, t):
                ticks.append(t)
        rt.add_listener(Listener())

        for _ in range(4190):
            rt.advance(1)
        self.assertEqual(sum(ticks), 1000)

    def test_remainder_carried_across_calls(self):
        rt = ReferenceTick(4_190_000)
        ticks = []
        class Listener:
            def tick_1mhz(self, t):
                ticks.append(t)
        rt.add_listener(Listener())

        for _ in range(42):
            rt.advance(100)
        self.assertEqual(sum(ticks), 1002)

    def test_multiple_listeners(self):
        rt = ReferenceTick(4_190_000)
        ticks_a = []
        ticks_b = []
        class ListenerA:
            def tick_1mhz(self, t):
                ticks_a.append(t)
        class ListenerB:
            def tick_1mhz(self, t):
                ticks_b.append(t)
        rt.add_listener(ListenerA())
        rt.add_listener(ListenerB())

        for _ in range(4190):
            rt.advance(1)
        self.assertEqual(sum(ticks_a), 1000)
        self.assertEqual(sum(ticks_a), sum(ticks_b))


class CycleTimerTests(unittest.TestCase):

    # advance

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_new_timer_has_zero_cycles(self, mock_mono):
        t = _CycleTimer()
        self.assertEqual(t.total_cycles, 0)

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_advance_adds_cycles(self, mock_mono):
        t = _CycleTimer()
        t.advance(100)
        t.advance(200)
        self.assertEqual(t.total_cycles, 300)

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_advance_ignored_when_stopped(self, mock_mono):
        t = _CycleTimer()
        t.advance(100)
        t.stop()
        t.advance(200)
        self.assertEqual(t.total_cycles, 100)

    # stop

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_stop_freezes_mhz(self, mock_mono):
        t = _CycleTimer()
        t.advance(4_190_000)
        mock_mono.return_value = 1.0
        t.stop()
        self.assertAlmostEqual(t.mhz, 4.19)

    # reset

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_reset_clears_cycles(self, mock_mono):
        t = _CycleTimer()
        t.advance(100)
        t.reset()
        self.assertEqual(t.total_cycles, 0)

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_reset_clears_stopped(self, mock_mono):
        t = _CycleTimer()
        t.stop()
        t.reset()
        t.advance(100)
        self.assertEqual(t.total_cycles, 100)

    # start

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_start_clears_stopped_without_clearing_snapshot(self, mock_mono):
        t = _CycleTimer()
        t.advance(4_190_000)
        mock_mono.return_value = 1.0
        t.stop()
        t.snapshot()
        t.start()
        self.assertEqual(t.total_cycles, 0)
        self.assertAlmostEqual(t.snapshot_mhz, 4.19)

    # snapshot

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_snapshot_saves_interval(self, mock_mono):
        t = _CycleTimer()
        t.advance(4_190_000)
        mock_mono.return_value = 1.0
        t.snapshot()
        self.assertAlmostEqual(t.snapshot_mhz, 4.19)

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_snapshot_resets_running_timer(self, mock_mono):
        t = _CycleTimer()
        t.advance(1000)
        t.snapshot()
        self.assertEqual(t.total_cycles, 0)

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_snapshot_when_stopped_uses_stop_sample(self, mock_mono):
        t = _CycleTimer()
        t.advance(4_190_000)
        mock_mono.return_value = 1.0
        t.stop()
        t.snapshot()
        self.assertAlmostEqual(t.snapshot_mhz, 4.19)

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_snapshot_when_stopped_stays_stopped(self, mock_mono):
        t = _CycleTimer()
        t.advance(1000)
        t.stop()
        t.snapshot()
        t.advance(500)
        self.assertEqual(t.total_cycles, 1000)

    # snapshot_mhz

    @patch('premium5.timing.time.monotonic', return_value=0.0)
    def test_new_timer_snapshot_mhz_is_zero(self, mock_mono):
        t = _CycleTimer()
        self.assertEqual(t.snapshot_mhz, 0.0)


class CycleTimerSampleTests(unittest.TestCase):

    # mhz

    def test_zero_elapsed_returns_zero_mhz(self):
        s = _CycleTimerSample(cycles=1000, elapsed=0.0)
        self.assertEqual(s.mhz, 0.0)

    def test_zero_cycles_returns_zero_mhz(self):
        s = _CycleTimerSample(cycles=0, elapsed=1.0)
        self.assertEqual(s.mhz, 0.0)

    def test_mhz(self):
        s = _CycleTimerSample(cycles=4_190_000, elapsed=1.0)
        self.assertAlmostEqual(s.mhz, 4.19)

    def test_defaults_to_zero(self):
        s = _CycleTimerSample()
        self.assertEqual(s.mhz, 0.0)
