import unittest
from premium5.digital import Level, LogicOutput, LogicInput, Inverter


class LogicOutputTests(unittest.TestCase):

    def test_starts_floating(self):
        out = LogicOutput()
        self.assertTrue(out.floating)

    def test_set_high(self):
        out = LogicOutput()
        out.set_high()
        self.assertTrue(out.high)
        self.assertFalse(out.low)
        self.assertFalse(out.floating)

    def test_set_low(self):
        out = LogicOutput()
        out.set_low()
        self.assertTrue(out.low)
        self.assertFalse(out.high)
        self.assertFalse(out.floating)

    def test_set_floating(self):
        out = LogicOutput()
        out.set_high()
        out.set_floating()
        self.assertTrue(out.floating)

    def test_bind_pushes_current_state(self):
        out = LogicOutput()
        out.set_high()
        inp = LogicInput()
        out.bind(inp)
        self.assertTrue(inp.high)

    def test_state_change_pushes_to_bound_input(self):
        out = LogicOutput()
        inp = LogicInput()
        out.bind(inp)
        out.set_high()
        self.assertTrue(inp.high)
        out.set_low()
        self.assertTrue(inp.low)

    def test_no_push_when_state_unchanged(self):
        out = LogicOutput()
        inp = LogicInput()
        out.bind(inp)
        out.set_high()
        call_count = [0]
        inp.on_rising = lambda: call_count.__setitem__(0, call_count[0] + 1)
        out.set_high()  # same state, should not push
        self.assertEqual(call_count[0], 0)

    def test_set_level_high(self):
        out = LogicOutput()
        out.set_level(Level.HIGH)
        self.assertTrue(out.high)

    def test_set_level_low(self):
        out = LogicOutput()
        out.set_level(Level.LOW)
        self.assertTrue(out.low)

    def test_set_level_floating(self):
        out = LogicOutput()
        out.set_level(Level.FLOATING)
        self.assertTrue(out.floating)

    def test_set_level_pushes_to_bound_input(self):
        out = LogicOutput()
        inp = LogicInput()
        out.bind(inp)
        out.set_level(Level.HIGH)
        self.assertTrue(inp.high)

    def test_bind_multiple_inputs(self):
        out = LogicOutput()
        inp1 = LogicInput()
        inp2 = LogicInput()
        out.bind(inp1)
        out.bind(inp2)
        out.set_high()
        self.assertTrue(inp1.high)
        self.assertTrue(inp2.high)

    def test_bind_same_input_twice_does_not_duplicate(self):
        out = LogicOutput()
        inp = LogicInput()
        out.bind(inp)
        out.bind(inp)
        self.assertEqual(len(out._inputs), 1)

    def test_bind_pushes_current_state_to_each(self):
        out = LogicOutput()
        out.set_high()
        inp1 = LogicInput()
        inp2 = LogicInput()
        out.bind(inp1)
        out.bind(inp2)
        self.assertTrue(inp1.high)
        self.assertTrue(inp2.high)


class LogicInputTests(unittest.TestCase):

    def test_defaults_to_default_level(self):
        inp = LogicInput(pull_level=Level.HIGH)
        self.assertTrue(inp.high)

    def test_defaults_to_floating_when_no_pull_given(self):
        inp = LogicInput()
        self.assertTrue(inp.floating)

    def test_notify_high(self):
        inp = LogicInput()
        inp.notify(Level.HIGH)
        self.assertTrue(inp.high)

    def test_notify_low(self):
        inp = LogicInput(pull_level=Level.HIGH)
        inp.notify(Level.LOW)
        self.assertTrue(inp.low)

    def test_floating_resolves_to_default(self):
        inp = LogicInput(pull_level=Level.HIGH)
        inp.notify(Level.LOW)
        inp.notify(Level.FLOATING)
        self.assertTrue(inp.high)

    def test_set_pull_level_updates_resolved_level(self):
        inp = LogicInput(pull_level=Level.LOW)
        self.assertTrue(inp.low)
        inp.set_pull_level(Level.HIGH)
        self.assertTrue(inp.high)

    def test_set_pull_level_does_not_fire_callbacks(self):
        inp = LogicInput(pull_level=Level.LOW)
        calls = []
        inp.on_rising = lambda: calls.append('rising')
        inp.on_falling = lambda: calls.append('falling')
        inp.set_pull_level(Level.HIGH)
        self.assertEqual(calls, [])

    def test_set_pull_level_ignored_when_driven(self):
        inp = LogicInput(pull_level=Level.LOW)
        inp.notify(Level.LOW)
        inp.set_pull_level(Level.HIGH)
        self.assertTrue(inp.low)

    def test_on_rising_callback(self):
        inp = LogicInput()
        calls = []
        inp.on_rising = lambda: calls.append('rising')
        inp.notify(Level.HIGH)
        self.assertEqual(calls, ['rising'])

    def test_on_falling_callback(self):
        inp = LogicInput(pull_level=Level.HIGH)
        calls = []
        inp.on_falling = lambda: calls.append('falling')
        inp.notify(Level.LOW)
        self.assertEqual(calls, ['falling'])

    def test_no_callback_when_level_unchanged(self):
        inp = LogicInput()
        inp.notify(Level.HIGH)
        calls = []
        inp.on_rising = lambda: calls.append('rising')
        inp.notify(Level.HIGH)
        self.assertEqual(calls, [])

    def test_snapshot_frozen(self):
        inp = LogicInput()
        inp.notify(Level.HIGH)
        snap = inp.snapshot()
        self.assertTrue(snap.high)
        inp.notify(Level.LOW)
        self.assertTrue(snap.high)

    def test_snapshot_floating(self):
        inp = LogicInput()
        snap = inp.snapshot()
        self.assertTrue(snap.floating)

    def test_int_high_is_1(self):
        inp = LogicInput()
        inp.notify(Level.HIGH)
        self.assertEqual(int(inp), 1)

    def test_int_low_is_0(self):
        inp = LogicInput()
        self.assertEqual(int(inp), 0)

    def test_int_floating_is_0(self):
        inp = LogicInput(pull_level=Level.FLOATING)
        self.assertEqual(int(inp), 0)


class InverterTests(unittest.TestCase):

    def test_high_in_low_out(self):
        inv = Inverter()
        out = LogicOutput()
        recv = LogicInput()
        out.bind(inv.input)
        inv.output.bind(recv)
        out.set_high()
        self.assertTrue(recv.low)

    def test_low_in_high_out(self):
        inv = Inverter()
        out = LogicOutput()
        recv = LogicInput()
        out.bind(inv.input)
        inv.output.bind(recv)
        out.set_high()
        out.set_low()
        self.assertTrue(recv.high)
