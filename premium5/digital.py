class Level:
    FLOATING = -1
    LOW = 0
    HIGH = 1


class LogicOutput(object):
    """Drives a logic level.  Inputs are bound to it.  Whenever it
    level changes, inputs are notified."""

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
