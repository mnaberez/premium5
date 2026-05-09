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

    def drives(self, *logic_inputs):
        for logic_input in logic_inputs:
            if logic_input not in self._inputs:
                self._inputs.append(logic_input)
                logic_input.notify(self._level)
        return self

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

    # chaining

    def follower(self):
        """Build a LogicInput that follows (mirrors) this output."""
        inp = LogicInput()
        self.drives(inp)
        return inp

    def inverted(self):
        """Build a LogicOutput that is the inverse of this output."""
        inv = Inverter()
        self.drives(inv.input)
        return inv.output


class LogicInput(object):
    """Receives a logic level from a bound LogicOutput.  Optionally
    simulates pull-up/down resistors and fires callbacks on 
    edge transitions."""

    _no_callback = staticmethod(lambda *args: None)

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
        self._on_rising   = self._no_callback  # rising edge
        self._on_falling  = self._no_callback  # falling edge
        self._on_floating = self._no_callback  # starts to float

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

    # LogicOutput notifies us when the level changes

    def notify(self, incoming_level):
        """The LogicOutput we are connected to is notifying us of
        its level.  It may or may not have changed."""
        self._incoming_level = incoming_level

        old_level = self._resolved_level
        self._resolved_level = self._resolve_level()

        if old_level != self._resolved_level:
            if self._resolved_level == Level.HIGH:
                self._on_rising()
            elif self._resolved_level == Level.LOW:
                self._on_falling()
            elif self._resolved_level == Level.FLOATING:
                self._on_floating()

    # internal helpers

    def _resolve_level(self):
        if self._incoming_level == Level.FLOATING:
            return self._pull_level
        return self._incoming_level

    # chaining

    def on_rising(self, callback):
        self._on_rising = callback
        return self

    def on_falling(self, callback):
        self._on_falling = callback
        return self

    def on_floating(self, callback):
        self._on_floating = callback
        return self

    def monitor(self):
        """Build a LogicOutput that mirrors this input's level."""
        out = LogicOutput(self._resolved_level)
        self.on_rising(out.set_high)
        self.on_falling(out.set_low)
        self.on_floating(out.set_floating)
        return out

    def driver(self, *args, **kwargs):
        """Build a LogicOutput that drives this input."""
        out = LogicOutput(*args, **kwargs)
        out.drives(self)
        return out

    def stuck(self, level):
        """
        Build a LogicOutput to drive this input always at a
        fixed level.  Used to convey that an input should always
        be fed that level.  The returned driver's level can 
        actually be changed later but you shouldn't do that."""
        return self.driver(level)


class Inverter(object):
    """Component that inverts its input"""

    def __init__(self):
        # electrical connections
        self.input = LogicInput()
        self.output = LogicOutput()

        self.input.on_rising(self.output.set_low)
        self.input.on_falling(self.output.set_high)
        self.input.on_floating(self.output.set_floating)


class Mux(object):
    """2 input, 1 output multiplexer:

    select LOW:  input_a routes to output
    select HIGH: input_b routes to output
    """

    def __init__(self):
        self.select_in = LogicInput(pull_level=Level.LOW)

        self.input_a = LogicInput()
        self.input_b = LogicInput()
        self.output = LogicOutput()

        self.select_in.on_falling(self._route_input_a_to_output)
        self.select_in.on_rising(self._route_input_b_to_output)
        self._route_input_a_to_output()

    def _route_input_a_to_output(self):
        self.output.set_level(self.input_a.level)
        self.input_a.on_rising(self.output.set_high)
        self.input_a.on_falling(self.output.set_low)
        self.input_a.on_floating(self.output.set_floating)
        self.input_b.on_rising(LogicInput._no_callback)
        self.input_b.on_falling(LogicInput._no_callback)
        self.input_b.on_floating(LogicInput._no_callback)

    def _route_input_b_to_output(self):
        self.output.set_level(self.input_b.level)
        self.input_b.on_rising(self.output.set_high)
        self.input_b.on_falling(self.output.set_low)
        self.input_b.on_floating(self.output.set_floating)
        self.input_a.on_rising(LogicInput._no_callback)
        self.input_a.on_falling(LogicInput._no_callback)
        self.input_a.on_floating(LogicInput._no_callback)


class Demux(object):
    """1 input, 2 output demultiplexer:

    select LOW:  input routes to output_a, output_b floats
    select HIGH: input routes to output_b, output_a floats
    """

    def __init__(self):
        self.select_in = LogicInput(pull_level=Level.LOW)

        self.input = LogicInput()
        self.output_a = LogicOutput()
        self.output_b = LogicOutput()

        self.select_in.on_falling(self._route_input_to_output_a)
        self.select_in.on_rising(self._route_input_to_output_b)
        self._route_input_to_output_a()

    def _route_input_to_output_a(self):
        self.output_b.set_floating()
        self.output_a.set_level(self.input.level)
        self.input.on_rising(self.output_a.set_high)
        self.input.on_falling(self.output_a.set_low)
        self.input.on_floating(self.output_a.set_floating)

    def _route_input_to_output_b(self):
        self.output_a.set_floating()
        self.output_b.set_level(self.input.level)
        self.input.on_rising(self.output_b.set_high)
        self.input.on_falling(self.output_b.set_low)
        self.input.on_floating(self.output_b.set_floating)
