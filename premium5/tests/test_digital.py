import unittest
from premium5.digital import Level, LogicOutput, LogicInput, Inverter, Demux, CSI30Demux


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

    def test_inverts(self):
        inv = Inverter()

        signal = LogicOutput()
        signal.bind(inv.input)

        inverted_signal = LogicInput()
        inv.output.bind(inverted_signal)

        signal.set_high()
        self.assertTrue(inverted_signal.low)
        signal.set_low()
        self.assertTrue(inverted_signal.high)


class DemuxTests(unittest.TestCase):

    def test_default_routes_to_output_a(self):
        mux = Demux()
        signal = LogicOutput(Level.HIGH)
        signal.bind(mux.input)

        signal.set_low()
        self.assertTrue(mux.output_a.low)
        signal.set_high()
        self.assertTrue(mux.output_a.high)

        self.assertTrue(mux.output_b.floating)

    def test_select_low_routes_to_output_a(self):
        mux = Demux()
        select = LogicOutput(Level.LOW)
        select.bind(mux.select)
        signal = LogicOutput(Level.HIGH)
        signal.bind(mux.input)

        signal.set_low()
        self.assertTrue(mux.output_a.low)
        signal.set_high()
        self.assertTrue(mux.output_a.high)

        self.assertTrue(mux.output_b.floating)

    def test_select_high_routes_to_output_b(self):
        mux = Demux()
        select = LogicOutput(Level.HIGH)
        select.bind(mux.select)
        signal = LogicOutput(Level.HIGH)
        signal.bind(mux.input)

        signal.set_low()
        self.assertTrue(mux.output_b.low)
        signal.set_high()
        self.assertTrue(mux.output_b.high)

        self.assertTrue(mux.output_a.floating)

    def test_select_floating_routes_to_output_a(self):
        mux = Demux()
        select = LogicOutput(Level.FLOATING)
        select.bind(mux.select)
        self.assertTrue(mux.select.low)  # pulled down
        signal = LogicOutput(Level.HIGH)
        signal.bind(mux.input)

        signal.set_low()
        self.assertTrue(mux.output_a.low)
        signal.set_high()
        self.assertTrue(mux.output_a.high)

        self.assertTrue(mux.output_b.floating)

    def test_switching_pushes_current_levels(self):
        mux = Demux()
        select = LogicOutput(Level.LOW)
        select.bind(mux.select)
        signal = LogicOutput(Level.HIGH)
        signal.bind(mux.input)

        self.assertTrue(mux.output_a.high)
        self.assertTrue(mux.output_b.floating)

        select.set_high()

        self.assertTrue(mux.output_b.high)
        self.assertTrue(mux.output_a.floating)


class CSI30DemuxTests(unittest.TestCase):

    def test_ctor_routes_to_upd(self):
        mux = CSI30Demux()
        csi30_clk_out = LogicOutput(Level.HIGH)
        csi30_clk_out.bind(mux.clk_from_csi30_in)
        csi30_dat_out = LogicOutput(Level.LOW)
        csi30_dat_out.bind(mux.dat_from_csi30_in)

        csi30_clk_out.set_low()
        self.assertTrue(mux.clk_to_upd_out.low)
        csi30_clk_out.set_high()
        self.assertTrue(mux.clk_to_upd_out.high)

        csi30_dat_out.set_low()
        self.assertTrue(mux.dat_to_upd_out.low)
        csi30_dat_out.set_high()
        self.assertTrue(mux.dat_to_upd_out.high)

        self.assertTrue(mux.clk_to_fis_out.floating)
        self.assertTrue(mux.dat_to_fis_out.floating)

    def test_p43_floating_routes_to_upd(self):
        mux = CSI30Demux()
        p43_out = LogicOutput(Level.FLOATING)
        p43_out.bind(mux.p43_in)
        self.assertTrue(mux.p43_in.low)  # pulled down
        csi30_clk_out = LogicOutput(Level.HIGH)
        csi30_clk_out.bind(mux.clk_from_csi30_in)
        csi30_dat_out = LogicOutput(Level.LOW)
        csi30_dat_out.bind(mux.dat_from_csi30_in)

        csi30_clk_out.set_low()
        self.assertTrue(mux.clk_to_upd_out.low)
        csi30_clk_out.set_high()
        self.assertTrue(mux.clk_to_upd_out.high)

        csi30_dat_out.set_low()
        self.assertTrue(mux.dat_to_upd_out.low)
        csi30_dat_out.set_high()
        self.assertTrue(mux.dat_to_upd_out.high)

        self.assertTrue(mux.clk_to_fis_out.floating)
        self.assertTrue(mux.dat_to_fis_out.floating)

    def test_p43_going_low_routes_to_upd(self):
        mux = CSI30Demux()
        p43_out = LogicOutput(Level.LOW)
        p43_out.bind(mux.p43_in)
        csi30_clk_out = LogicOutput(Level.HIGH)
        csi30_clk_out.bind(mux.clk_from_csi30_in)
        csi30_dat_out = LogicOutput(Level.LOW)
        csi30_dat_out.bind(mux.dat_from_csi30_in)

        csi30_clk_out.set_low()
        self.assertTrue(mux.clk_to_upd_out.low)
        csi30_clk_out.set_high()
        self.assertTrue(mux.clk_to_upd_out.high)

        csi30_dat_out.set_low()
        self.assertTrue(mux.dat_to_upd_out.low)
        csi30_dat_out.set_high()
        self.assertTrue(mux.dat_to_upd_out.high)

        self.assertTrue(mux.clk_to_fis_out.floating)
        self.assertTrue(mux.dat_to_fis_out.floating)

    def test_p43_going_high_routes_to_fis(self):
        mux = CSI30Demux()
        p43_out = LogicOutput(Level.HIGH)
        p43_out.bind(mux.p43_in)
        csi30_clk_out = LogicOutput(Level.HIGH)
        csi30_clk_out.bind(mux.clk_from_csi30_in)
        csi30_dat_out = LogicOutput(Level.LOW)
        csi30_dat_out.bind(mux.dat_from_csi30_in)

        csi30_clk_out.set_low()
        self.assertTrue(mux.clk_to_fis_out.low)
        csi30_clk_out.set_high()
        self.assertTrue(mux.clk_to_fis_out.high)

        csi30_dat_out.set_low()
        self.assertTrue(mux.dat_to_fis_out.low)
        csi30_dat_out.set_high()
        self.assertTrue(mux.dat_to_fis_out.high)

        self.assertTrue(mux.clk_to_upd_out.floating)
        self.assertTrue(mux.dat_to_upd_out.floating)

    def test_switching_to_fis_pushes_current_levels(self):
        mux = CSI30Demux()
        p43_out = LogicOutput(Level.LOW)
        p43_out.bind(mux.p43_in)
        csi30_clk_out = LogicOutput(Level.HIGH)
        csi30_clk_out.bind(mux.clk_from_csi30_in)
        csi30_dat_out = LogicOutput(Level.HIGH)
        csi30_dat_out.bind(mux.dat_from_csi30_in)

        # CLK and DAT are both HIGH, routed to UPD
        self.assertTrue(mux.clk_to_upd_out.high)
        self.assertTrue(mux.dat_to_upd_out.high)
        self.assertTrue(mux.clk_to_fis_out.floating)
        self.assertTrue(mux.dat_to_fis_out.floating)

        # switch to FIS — no edges, just the switch
        p43_out.set_high()

        # FIS side should see the current levels immediately
        self.assertTrue(mux.clk_to_fis_out.high)
        self.assertTrue(mux.dat_to_fis_out.high)
        self.assertTrue(mux.clk_to_upd_out.floating)
        self.assertTrue(mux.dat_to_upd_out.floating)

    def test_switching_to_upd_pushes_current_levels(self):
        mux = CSI30Demux()
        p43_out = LogicOutput(Level.HIGH)
        p43_out.bind(mux.p43_in)
        csi30_clk_out = LogicOutput(Level.HIGH)
        csi30_clk_out.bind(mux.clk_from_csi30_in)
        csi30_dat_out = LogicOutput(Level.LOW)
        csi30_dat_out.bind(mux.dat_from_csi30_in)

        # CLK HIGH, DAT LOW, routed to FIS
        self.assertTrue(mux.clk_to_fis_out.high)
        self.assertTrue(mux.dat_to_fis_out.low)

        # switch to UPD — no edges, just the switch
        p43_out.set_low()

        # UPD side should see the current levels immediately
        self.assertTrue(mux.clk_to_upd_out.high)
        self.assertTrue(mux.dat_to_upd_out.low)
        self.assertTrue(mux.clk_to_fis_out.floating)
        self.assertTrue(mux.dat_to_fis_out.floating)
