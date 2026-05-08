class Level:
    FLOATING = -1
    LOW = 0
    HIGH = 1


class LogicOutput(object):
    """Drives a logic level.  The owner of a LogicOutput changes its level.
    LogicInputs are bound to it and are notified when the level changes."""

    def __init__(self, level=Level.FLOATING):
        self._level = level
        self._inputs = []

    def bind(self, logic_input):
        if logic_input not in self._inputs:
            self._inputs.append(logic_input)
            logic_input.notify(self._level)

    # set the level

    def set_level(self, level):
        if level != self._level:
            self._level = level

            for logic_input in self._inputs:
                logic_input.notify(level)

    def set_high(self):
        self.set_level(Level.HIGH)

    def set_low(self):
        self.set_level(Level.LOW)

    def set_floating(self):
        self.set_level(Level.FLOATING)

    def toggle(self):
        if self._level == Level.HIGH:
            self.set_low()
        elif self._level == Level.LOW:
            self.set_high()

    # interrogate the level

    @property
    def high(self):
        return self._level == Level.HIGH

    @property
    def low(self):
        return self._level == Level.LOW

    @property
    def floating(self):
        return self._level == Level.FLOATING

    def as_input(self):
        """Create a LogicInput that follows this output's level."""
        inp = LogicInput()
        self.bind(inp)
        return inp


class LogicInput(object):
    """Receives a logic level from a bound LogicOutput.  Optionally
    simulates pull-up/down resistors and fires callbacks on 
    edge transitions."""

    _no_callback = staticmethod(lambda: None)

    def __init__(self, pull_level=Level.FLOATING):
        '''Use pull_level to simulate pull-up/pull-down resistor behavior:

           - Level.FLOATING: Floating input keeps floating. (default)
           - Level.HIGH:     Floating input becomes HIGH.
           - Level.LOW:      Floating input becomes LOW.
        '''
        # init internal state
        self._incoming_level = Level.FLOATING
        self.set_pull_level(pull_level)

        # callbacks
        self.on_rising  = self._no_callback
        self.on_falling = self._no_callback

    def set_pull_level(self, level):
        '''Change the pull-up behavior'''
        self._pull_level = level
        self._resolved_level = self._resolve_level()

    def snapshot(self):
        """Take a snapshot of our current level so the caller can
        save it and use it in comparisons later."""
        snap = LogicInput(pull_level=self._pull_level)
        snap.notify(self._incoming_level)
        return snap

    # interrogate the level

    @property
    def level(self):
        return self._resolved_level

    @property
    def high(self):
        return self._resolved_level == Level.HIGH

    @property
    def low(self):
        return self._resolved_level == Level.LOW

    @property
    def floating(self):
        return self._resolved_level == Level.FLOATING

    def __int__(self):
        return int(self._resolved_level == Level.HIGH)

    def as_output(self):
        """Create a LogicOutput that follows this input's level."""
        out = LogicOutput(self._resolved_level)
        self.on_rising = out.set_high
        self.on_falling = out.set_low
        return out

    # LogicOutput notifies us when the level changes

    def notify(self, incoming_level):
        """The LogicOutput we are connected to is notifying us of
        its level.  It may or may not have changed."""
        self._incoming_level = incoming_level

        old_level = self._resolved_level
        self._resolved_level = self._resolve_level()

        if old_level != self._resolved_level:
            if self._resolved_level == Level.HIGH:
                self.on_rising()
            elif self._resolved_level == Level.LOW:
                self.on_falling()

    # internal helpers

    def _resolve_level(self):
        if self._incoming_level == Level.FLOATING:
            return self._pull_level
        return self._incoming_level


class Inverter(object):
    """Component that inverts its input"""

    def __init__(self):
        # electrical connections
        self.input = LogicInput()
        self.output = LogicOutput()

        # callbacks from input change output
        self.input.on_rising = self.output.set_low
        self.input.on_falling = self.output.set_high


class Mux(object):
    """
    2 input, 1 output multiplexer:

    select LOW:  input_a routes to output
    select HIGH: input_b routes to output
    """

    def __init__(self):
        self.select = LogicInput(pull_level=Level.LOW)

        self.input_a = LogicInput()
        self.input_b = LogicInput()
        self.output = LogicOutput()

        self.select.on_falling = self._route_input_a_to_output
        self.select.on_rising  = self._route_input_b_to_output
        self._route_input_a_to_output()

    def _route_input_a_to_output(self):
        self.output.set_level(self.input_a.level)
        self.input_a.on_rising = self.output.set_high
        self.input_a.on_falling = self.output.set_low
        self.input_b.on_rising = LogicInput._no_callback
        self.input_b.on_falling = LogicInput._no_callback

    def _route_input_b_to_output(self):
        self.output.set_level(self.input_b.level)
        self.input_b.on_rising = self.output.set_high
        self.input_b.on_falling = self.output.set_low
        self.input_a.on_rising = LogicInput._no_callback
        self.input_a.on_falling = LogicInput._no_callback


class Demux(object):
    """
    1 input, 2 output multiplexer:

    select LOW:  input routes to output_a, output_b floats
    select HIGH: input routes to output_b, output_a floats
    """

    def __init__(self):
        self.select = LogicInput(pull_level=Level.LOW)

        self.input = LogicInput()
        self.output_a = LogicOutput()
        self.output_b = LogicOutput()

        self.select.on_falling = self._route_input_to_output_a
        self.select.on_rising  = self._route_input_to_output_b
        self._route_input_to_output_a()

    def _route_input_to_output_a(self):
        self.output_b.set_floating()
        self.output_a.set_level(self.input.level)
        self.input.on_rising = self.output_a.set_high
        self.input.on_falling = self.output_a.set_low

    def _route_input_to_output_b(self):
        self.output_a.set_floating()
        self.output_b.set_level(self.input.level)
        self.input.on_rising = self.output_b.set_high
        self.input.on_falling = self.output_b.set_low


class CSI30Demux(object):
    """Component to switch CSI30 between uPD16432B and FIS (3LB).

    The radio uses the SPI controller CSI30 for both its own
    display (the uPD16432B) and the external FIS interface (3LB).
    The firmware sets P4.3 to HIGH whenever it wants to talk to
    the FIS, otherwise it leaves P4.3 low.

    Guess:
        P4.3 controls some sort of demultiplexer.  Its function is
        probably to prevent CLK and DAT changes from "leaking"
        out to the FIS while the uPD16432B is being accessed.  It
        might also prevent the uPD16432B from seeing CLK and DAT
        changes when the FIS is being used.

    This emulation is an isolator:
        When P4.3 is LOW:  CSI30 drives the uPD16432B, FIS floats
        When P4.3 is HIGH: CSI30 drives the FIS bus, uPD16432B floats
    """

    def __init__(self):
        self._clk_demux = Demux()
        self._dat_demux = Demux()

        # input from P4.3: low=uPD16432B, high=FIS
        self.p43_in = LogicInput(pull_level=Level.LOW)

        # fan out input from P4.3 to both mux selects
        self._p43_fanout = LogicOutput()
        self._p43_fanout.bind(self._clk_demux.select)
        self._p43_fanout.bind(self._dat_demux.select)
        self.p43_in.on_falling = self._p43_fanout.set_low
        self.p43_in.on_rising  = self._p43_fanout.set_high

        # expose clk in/outs with descriptive names
        self.clk_from_csi30_in = self._clk_demux.input
        self.clk_to_upd_out = self._clk_demux.output_a
        self.clk_to_fis_out = self._clk_demux.output_b

        # expose dat in/outs with descriptive names
        self.dat_from_csi30_in = self._dat_demux.input
        self.dat_to_upd_out = self._dat_demux.output_a
        self.dat_to_fis_out = self._dat_demux.output_b
