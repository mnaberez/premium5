import unittest

from premium5.volume import VolumeKnob


class VolumeKnobTests(unittest.TestCase):
    def setUp(self):
        self.knob = VolumeKnob()

    def _tick_one_transition(self):
        self.knob.tick_1mhz(VolumeKnob.STATE_HOLD_TICKS)

    def test_initial_state(self):
        self.assertTrue(self.knob.phase_a_out.low)
        self.assertTrue(self.knob.phase_b_out.low)

    def test_up_clocks_two_transitions(self):
        # starts at (0, 0)
        self.knob.up()
        self._tick_one_transition()
        # (1, 0)
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.low)
        self._tick_one_transition()
        # (1, 1)
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.high)

    def test_down_clocks_two_transitions(self):
        # starts at (0, 0)
        self.knob.down()
        self._tick_one_transition()
        # (0, 1)
        self.assertTrue(self.knob.phase_a_out.low)
        self.assertTrue(self.knob.phase_b_out.high)
        self._tick_one_transition()
        # (1, 1)
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.high)

    def test_transitions_respect_timing(self):
        self.knob.up()
        # first transition fires on tick 1
        self.knob.tick_1mhz(1)
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.low)
        # still held one tick before the hold period ends
        self.knob.tick_1mhz(VolumeKnob.STATE_HOLD_TICKS - 2)
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.low)
        # hold period ends, step popped
        self.knob.tick_1mhz(1)
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.low)
        # next step fires
        self.knob.tick_1mhz(1)
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.high)

    def test_stops_after_transitions_complete(self):
        self.knob.up()
        self._tick_one_transition()
        self._tick_one_transition()
        # record state after detent completes
        a_after = self.knob.phase_a_out.high
        b_after = self.knob.phase_b_out.high
        # tick more, nothing should change
        self._tick_one_transition()
        self.assertEqual(self.knob.phase_a_out.high, a_after)
        self.assertEqual(self.knob.phase_b_out.high, b_after)

    def test_consecutive_up_wraps(self):
        # first up: (0,0) -> (1,0) -> (1,1)
        self.knob.up()
        self._tick_one_transition()
        self._tick_one_transition()
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.high)
        # second up: (1,1) -> (0,1) -> (0,0)
        self.knob.up()
        self._tick_one_transition()
        # (0, 1)
        self.assertTrue(self.knob.phase_a_out.low)
        self.assertTrue(self.knob.phase_b_out.high)
        self._tick_one_transition()
        # (0, 0) - wrapped
        self.assertTrue(self.knob.phase_a_out.low)
        self.assertTrue(self.knob.phase_b_out.low)

    def test_consecutive_down_wraps(self):
        # first down: (0,0) -> (0,1) -> (1,1)
        self.knob.down()
        self._tick_one_transition()
        self._tick_one_transition()
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.high)
        # second down: (1,1) -> (1,0) -> (0,0)
        self.knob.down()
        self._tick_one_transition()
        # (1, 0)
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.low)
        self._tick_one_transition()
        # (0, 0) - wrapped
        self.assertTrue(self.knob.phase_a_out.low)
        self.assertTrue(self.knob.phase_b_out.low)

    def test_queued_up_then_down(self):
        # queue up and down without ticking
        self.knob.up()    # enqueues (1,0), (1,1)
        self.knob.down()  # enqueues (1,0), (0,0)
        # nothing has changed yet
        self.assertTrue(self.knob.phase_a_out.low)
        self.assertTrue(self.knob.phase_b_out.low)
        # tick through all 4 queued states
        self._tick_one_transition()
        # (1, 0)
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.low)
        self._tick_one_transition()
        # (1, 1)
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.high)
        self._tick_one_transition()
        # (1, 0) - back down
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.low)
        self._tick_one_transition()
        # (0, 0) - back to start
        self.assertTrue(self.knob.phase_a_out.low)
        self.assertTrue(self.knob.phase_b_out.low)
