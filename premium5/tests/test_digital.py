import unittest
from premium5.digital import Level, LogicOutput, LogicInput, Inverter, Mux, Demux


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
        out.drives(inp)
        self.assertTrue(inp.high)

    def test_state_change_pushes_to_bound_input(self):
        out = LogicOutput()
        inp = LogicInput()
        out.drives(inp)
        out.set_high()
        self.assertTrue(inp.high)
        out.set_low()
        self.assertTrue(inp.low)

    def test_no_push_when_state_unchanged(self):
        out = LogicOutput()
        inp = LogicInput()
        out.drives(inp)
        out.set_high()
        call_count = [0]
        inp.on_rising(lambda: call_count.__setitem__(0, call_count[0] + 1))
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

    def test_toggle_from_low(self):
        out = LogicOutput(Level.LOW)
        out.toggle()
        self.assertTrue(out.high)

    def test_toggle_from_high(self):
        out = LogicOutput(Level.HIGH)
        out.toggle()
        self.assertTrue(out.low)

    def test_toggle_from_floating_stays_floating(self):
        out = LogicOutput(Level.FLOATING)
        out.toggle()
        self.assertTrue(out.floating)

    def test_set_level_pushes_to_bound_input(self):
        out = LogicOutput()
        inp = LogicInput()
        out.drives(inp)
        out.set_level(Level.HIGH)
        self.assertTrue(inp.high)

    def test_bind_multiple_inputs(self):
        out = LogicOutput()
        inp1 = LogicInput()
        inp2 = LogicInput()
        out.drives(inp1)
        out.drives(inp2)
        out.set_high()
        self.assertTrue(inp1.high)
        self.assertTrue(inp2.high)

    def test_bind_same_input_twice_does_not_duplicate(self):
        out = LogicOutput()
        inp = LogicInput()
        out.drives(inp)
        out.drives(inp)
        self.assertEqual(len(out._inputs), 1)

    def test_bind_pushes_current_state_to_each(self):
        out = LogicOutput()
        out.set_high()
        inp1 = LogicInput()
        inp2 = LogicInput()
        out.drives(inp1)
        out.drives(inp2)
        self.assertTrue(inp1.high)
        self.assertTrue(inp2.high)

    def test_drives_multiple_in_one_call(self):
        out = LogicOutput()
        inp1 = LogicInput()
        inp2 = LogicInput()
        out.drives(inp1, inp2)

        out.set_high()
        self.assertTrue(inp1.high)
        self.assertTrue(inp2.high)

    def test_drives_returns_self(self):
        out = LogicOutput()
        inp = LogicInput()

        result = out.drives(inp)
        self.assertIs(result, out)

    def test_follower_returns_logic_input(self):
        out = LogicOutput()

        follower = out.follower()
        self.assertIsInstance(follower, LogicInput)

    def test_follower_mirrors_level(self):
        out = LogicOutput(Level.HIGH)

        follower = out.follower()
        self.assertTrue(follower.high)

        out.set_low()
        self.assertTrue(follower.low)

    def test_follower_mirrors_floating(self):
        out = LogicOutput(Level.HIGH)

        follower = out.follower()
        out.set_floating()
        self.assertTrue(follower.floating)

    def test_inverted_returns_logic_output(self):
        out = LogicOutput()

        inv = out.inverted()
        self.assertIsInstance(inv, LogicOutput)

    def test_inverted_inverts_level(self):
        out = LogicOutput(Level.HIGH)

        inv = out.inverted()
        self.assertTrue(inv.low)

        out.set_low()
        self.assertTrue(inv.high)

    def test_inverted_floating_stays_floating(self):
        out = LogicOutput(Level.HIGH)

        inv = out.inverted()
        out.set_floating()
        self.assertTrue(inv.floating)


class LogicInputTests(unittest.TestCase):

    def test_defaults_to_default_level(self):
        inp = LogicInput(pull_level=Level.HIGH)
        self.assertTrue(inp.high)

    def test_defaults_to_floating_when_no_pull_given(self):
        inp = LogicInput()
        self.assertTrue(inp.floating)

    def test_level_returns_resolved_level(self):
        inp = LogicInput()
        self.assertEqual(inp.level, Level.FLOATING)
        inp.notify(Level.HIGH)
        self.assertEqual(inp.level, Level.HIGH)
        inp.notify(Level.LOW)
        self.assertEqual(inp.level, Level.LOW)

    def test_level_resolves_floating_to_pull(self):
        inp = LogicInput(pull_level=Level.HIGH)
        self.assertEqual(inp.level, Level.HIGH)
        inp.notify(Level.LOW)
        self.assertEqual(inp.level, Level.LOW)
        inp.notify(Level.FLOATING)
        self.assertEqual(inp.level, Level.HIGH)

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
        inp.on_rising(lambda: calls.append('rising'))
        inp.on_falling(lambda: calls.append('falling'))
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
        inp.on_rising(lambda: calls.append('rising'))
        inp.notify(Level.HIGH)
        self.assertEqual(calls, ['rising'])

    def test_on_falling_callback(self):
        inp = LogicInput(pull_level=Level.HIGH)
        calls = []
        inp.on_falling(lambda: calls.append('falling'))
        inp.notify(Level.LOW)
        self.assertEqual(calls, ['falling'])

    def test_no_callback_when_level_unchanged(self):
        inp = LogicInput()
        inp.notify(Level.HIGH)
        calls = []
        inp.on_rising(lambda: calls.append('rising'))
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

    def test_driver_returns_logic_output(self):
        inp = LogicInput()

        drv = inp.driver()
        self.assertIsInstance(drv, LogicOutput)

    def test_driver_drives_the_input(self):
        inp = LogicInput()

        drv = inp.driver()
        drv.set_high()
        self.assertTrue(inp.high)

        drv.set_low()
        self.assertTrue(inp.low)

    def test_driver_starts_at_current_level(self):
        inp = LogicInput(pull_level=Level.HIGH)

        drv = inp.driver()
        self.assertTrue(drv.high)

    def test_monitor_returns_logic_output(self):
        inp = LogicInput()

        mon = inp.monitor()
        self.assertIsInstance(mon, LogicOutput)

    def test_monitor_mirrors_level(self):
        inp = LogicInput()
        mon = inp.monitor()

        out = LogicOutput()
        out.drives(inp)

        out.set_high()
        self.assertTrue(mon.high)

        out.set_low()
        self.assertTrue(mon.low)

    def test_monitor_mirrors_floating(self):
        inp = LogicInput()
        mon = inp.monitor()

        out = LogicOutput(Level.HIGH)
        out.drives(inp)

        out.set_floating()
        self.assertTrue(mon.floating)

    def test_monitor_starts_at_current_level(self):
        inp = LogicInput(pull_level=Level.HIGH)

        mon = inp.monitor()
        self.assertTrue(mon.high)

    def test_on_floating_callback(self):
        inp = LogicInput(pull_level=Level.HIGH)
        calls = []
        inp.on_floating(lambda: calls.append('floating'))

        out = LogicOutput(Level.HIGH)
        out.drives(inp)

        out.set_floating()  # pull-up resolves to HIGH, no change
        self.assertEqual(calls, [])

        inp.set_pull_level(Level.FLOATING)  # set_pull_level doesn't fire callbacks
        self.assertEqual(calls, [])

    def test_on_floating_callback_fires(self):
        inp = LogicInput()
        calls = []
        inp.on_floating(lambda: calls.append('floating'))

        out = LogicOutput(Level.HIGH)
        out.drives(inp)

        out.set_floating()
        self.assertEqual(calls, ['floating'])

    def test_on_rising_returns_self(self):
        inp = LogicInput()

        result = inp.on_rising(lambda: None)
        self.assertIs(result, inp)

    def test_on_falling_returns_self(self):
        inp = LogicInput()

        result = inp.on_falling(lambda: None)
        self.assertIs(result, inp)

    def test_on_floating_returns_self(self):
        inp = LogicInput()

        result = inp.on_floating(lambda: None)
        self.assertIs(result, inp)


class InverterTests(unittest.TestCase):

    def test_inverts(self):
        inv = Inverter()
        signal = LogicOutput()
        signal.drives(inv.input)
        inverted_signal = LogicInput()
        inv.output.drives(inverted_signal)

        signal.set_high()
        self.assertTrue(inverted_signal.low)
        signal.set_low()
        self.assertTrue(inverted_signal.high)

    def test_floating_input_leaves_output_floating(self):
        inv = Inverter()
        self.assertTrue(inv.input.floating)
        self.assertTrue(inv.output.floating)

    def test_input_going_floating_makes_output_floating(self):
        inv = Inverter()
        signal = LogicOutput()
        signal.drives(inv.input)

        signal.set_high()
        self.assertTrue(inv.output.low)

        signal.set_floating()
        self.assertTrue(inv.output.floating)


class DemuxTests(unittest.TestCase):

    def test_default_routes_to_output_a(self):
        demux = Demux()
        signal = LogicOutput(Level.HIGH)
        signal.drives(demux.input)

        signal.set_low()
        self.assertTrue(demux.output_a.low)
        signal.set_high()
        self.assertTrue(demux.output_a.high)

        self.assertTrue(demux.output_b.floating)

    def test_select_low_routes_to_output_a(self):
        demux = Demux()
        select = LogicOutput(Level.LOW)
        select.drives(demux.select_in)
        signal = LogicOutput(Level.HIGH)
        signal.drives(demux.input)

        signal.set_low()
        self.assertTrue(demux.output_a.low)
        signal.set_high()
        self.assertTrue(demux.output_a.high)

        self.assertTrue(demux.output_b.floating)

    def test_select_high_routes_to_output_b(self):
        demux = Demux()
        select = LogicOutput(Level.HIGH)
        select.drives(demux.select_in)
        signal = LogicOutput(Level.HIGH)
        signal.drives(demux.input)

        signal.set_low()
        self.assertTrue(demux.output_b.low)
        signal.set_high()
        self.assertTrue(demux.output_b.high)

        self.assertTrue(demux.output_a.floating)

    def test_select_floating_routes_to_output_a(self):
        demux = Demux()
        select = LogicOutput(Level.FLOATING)
        select.drives(demux.select_in)
        self.assertTrue(demux.select_in.low)  # pulled down
        signal = LogicOutput(Level.HIGH)
        signal.drives(demux.input)

        signal.set_low()
        self.assertTrue(demux.output_a.low)
        signal.set_high()
        self.assertTrue(demux.output_a.high)

        self.assertTrue(demux.output_b.floating)

    def test_switching_pushes_current_levels(self):
        demux = Demux()
        select = LogicOutput(Level.LOW)
        select.drives(demux.select_in)
        signal = LogicOutput(Level.HIGH)
        signal.drives(demux.input)

        self.assertTrue(demux.output_a.high)
        self.assertTrue(demux.output_b.floating)

        select.set_high()

        self.assertTrue(demux.output_b.high)
        self.assertTrue(demux.output_a.floating)

    def test_input_going_floating_propagates_to_active_output(self):
        demux = Demux()
        signal = LogicOutput(Level.HIGH)
        signal.drives(demux.input)

        self.assertTrue(demux.output_a.high)

        signal.set_floating()
        self.assertTrue(demux.output_a.floating)

    def test_inactive_output_stays_floating_when_input_changes(self):
        demux = Demux()
        select = LogicOutput(Level.LOW)
        select.drives(demux.select_in)
        signal = LogicOutput(Level.HIGH)
        signal.drives(demux.input)

        self.assertTrue(demux.output_b.floating)

        signal.set_low()
        self.assertTrue(demux.output_b.floating)

        signal.set_floating()
        self.assertTrue(demux.output_b.floating)


class MuxTests(unittest.TestCase):

    def test_default_routes_input_a_to_output(self):
        mux = Mux()
        signal_a = LogicOutput(Level.HIGH)
        signal_a.drives(mux.input_a)
        signal_b = LogicOutput(Level.LOW)
        signal_b.drives(mux.input_b)

        self.assertTrue(mux.output.high)
        signal_a.set_low()
        self.assertTrue(mux.output.low)

    def test_select_low_routes_input_a_to_output(self):
        mux = Mux()
        select = LogicOutput(Level.LOW)
        select.drives(mux.select_in)
        signal_a = LogicOutput(Level.HIGH)
        signal_a.drives(mux.input_a)
        signal_b = LogicOutput(Level.LOW)
        signal_b.drives(mux.input_b)

        self.assertTrue(mux.output.high)
        signal_a.set_low()
        self.assertTrue(mux.output.low)

    def test_select_high_routes_input_b_to_output(self):
        mux = Mux()
        select = LogicOutput(Level.HIGH)
        select.drives(mux.select_in)
        signal_a = LogicOutput(Level.HIGH)
        signal_a.drives(mux.input_a)
        signal_b = LogicOutput(Level.LOW)
        signal_b.drives(mux.input_b)

        self.assertTrue(mux.output.low)
        signal_b.set_high()
        self.assertTrue(mux.output.high)

    def test_inactive_input_does_not_affect_output(self):
        mux = Mux()
        select = LogicOutput(Level.LOW)
        select.drives(mux.select_in)
        signal_a = LogicOutput(Level.HIGH)
        signal_a.drives(mux.input_a)
        signal_b = LogicOutput(Level.LOW)
        signal_b.drives(mux.input_b)

        self.assertTrue(mux.output.high)
        signal_b.set_high()  # input_b is inactive, should not affect output
        self.assertTrue(mux.output.high)
        signal_b.set_low()
        self.assertTrue(mux.output.high)

    def test_select_floating_routes_input_a(self):
        mux = Mux()
        select = LogicOutput(Level.FLOATING)
        select.drives(mux.select_in)
        self.assertTrue(mux.select_in.low)  # pulled down
        signal_a = LogicOutput(Level.HIGH)
        signal_a.drives(mux.input_a)

        self.assertTrue(mux.output.high)

    def test_switching_pushes_current_levels(self):
        mux = Mux()
        select = LogicOutput(Level.LOW)
        select.drives(mux.select_in)
        signal_a = LogicOutput(Level.HIGH)
        signal_a.drives(mux.input_a)
        signal_b = LogicOutput(Level.LOW)
        signal_b.drives(mux.input_b)

        self.assertTrue(mux.output.high)  # from input_a

        select.set_high()

        self.assertTrue(mux.output.low)  # now from input_b

    def test_active_input_going_floating_propagates_to_output(self):
        mux = Mux()
        signal_a = LogicOutput(Level.HIGH)
        signal_a.drives(mux.input_a)

        self.assertTrue(mux.output.high)

        signal_a.set_floating()
        self.assertTrue(mux.output.floating)

    def test_inactive_input_going_floating_does_not_affect_output(self):
        mux = Mux()
        select = LogicOutput(Level.LOW)
        select.drives(mux.select_in)
        signal_a = LogicOutput(Level.HIGH)
        signal_a.drives(mux.input_a)
        signal_b = LogicOutput(Level.HIGH)
        signal_b.drives(mux.input_b)

        self.assertTrue(mux.output.high)

        signal_b.set_floating()  # input_b is inactive
        self.assertTrue(mux.output.high)  # output unchanged


