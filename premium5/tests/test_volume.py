import unittest

from premium5.volume import VolumeKnob


class VolumeKnobTests(unittest.TestCase):
    def setUp(self):
        self.knob = VolumeKnob()

    def test_initial_state(self):
        self.assertTrue(self.knob.phase_a_out.low)
        self.assertTrue(self.knob.phase_b_out.low)

    def test_up_clocks_two_transitions(self):
        # starts at state 0: (0, 0)
        self.knob.up()
        self._tick_one_transition()
        # state 1: (1, 0)
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.low)
        self._tick_one_transition()
        # state 2: (1, 1)
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.high)

    def test_down_clocks_two_transitions(self):
        # starts at state 0: (0, 0)
        self.knob.down()
        self._tick_one_transition()
        # state 3: (0, 1)
        self.assertTrue(self.knob.phase_a_out.low)
        self.assertTrue(self.knob.phase_b_out.high)
        self._tick_one_transition()
        # state 2: (1, 1)
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.high)

    def test_transitions_respect_timing(self):
        self.knob.up()
        # first transition fires immediately
        self.knob.tick_1mhz(1)
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.low)
        # one tick short of the next transition
        self.knob.tick_1mhz(VolumeKnob.TICKS_PER_TRANSITION - 1)
        # still at state 1
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.low)
        # one more tick triggers the second transition
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
        # first up: state 0 -> 1 -> 2
        self.knob.up()
        self._tick_one_transition()
        self._tick_one_transition()
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.high)
        # second up: state 2 -> 3 -> 0
        self.knob.up()
        self._tick_one_transition()
        # state 3: (0, 1)
        self.assertTrue(self.knob.phase_a_out.low)
        self.assertTrue(self.knob.phase_b_out.high)
        self._tick_one_transition()
        # state 0: (0, 0) - wrapped
        self.assertTrue(self.knob.phase_a_out.low)
        self.assertTrue(self.knob.phase_b_out.low)

    def test_consecutive_down_wraps(self):
        # first down: state 0 -> 3 -> 2
        self.knob.down()
        self._tick_one_transition()
        self._tick_one_transition()
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.high)
        # second down: state 2 -> 1 -> 0
        self.knob.down()
        self._tick_one_transition()
        # state 1: (1, 0)
        self.assertTrue(self.knob.phase_a_out.high)
        self.assertTrue(self.knob.phase_b_out.low)
        self._tick_one_transition()
        # state 0: (0, 0) - wrapped
        self.assertTrue(self.knob.phase_a_out.low)
        self.assertTrue(self.knob.phase_b_out.low)

    def _tick_one_transition(self):
        self.knob.tick_1mhz(VolumeKnob.TICKS_PER_TRANSITION)
