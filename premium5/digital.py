class Level:
    FLOATING = -1
    LOW = 0
    HIGH = 1


class LogicOutput(object):
    """Drives a logic level. Owner calls set_high/set_low/set_floating.
    When the state changes, pushes the new value to the bound LogicInput."""

    def __init__(self):
        self._state = Level.FLOATING
        self._input = None

    def bind(self, logic_input):
        self._input = logic_input
        self._input.notify(self._state)

    def set_high(self):
        self._set(Level.HIGH)

    def set_low(self):
        self._set(Level.LOW)

    def set_floating(self):
        self._set(Level.FLOATING)

    @property
    def high(self):
        return self._state == Level.HIGH

    @property
    def low(self):
        return self._state == Level.LOW

    @property
    def floating(self):
        return self._state == Level.FLOATING

    def _set(self, state):
        if state != self._state:
            self._state = state
            if self._input is not None:
                self._input.notify(state)


class LogicInput(object):
    """Receives a logic level from a bound LogicOutput.
    Has a default (pull-up/pull-down) for when the output is FLOATING.
    Fires on_rising/on_falling callbacks on transitions."""

    _no_callback = staticmethod(lambda: None)

    def __init__(self, default=Level.LOW):
        self._default_level = default
        self._incoming_level = Level.FLOATING
        self._resolved_level = default
        self.on_rising = self._no_callback
        self.on_falling = self._no_callback

    def set_default(self, level):
        self._default_level = level
        self._resolved_level = self._resolve_level()

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

    def notify(self, incoming_level):
        """The LogicOutput we are connected to is notifying us of its level.
        It may or may not have changed."""
        self._incoming_level = incoming_level

        old_level = self._resolved_level
        self._resolved_level = self._resolve_level()

        if old_level != self._resolved_level:
            if self._resolved_level == Level.HIGH:
                self.on_rising()
            elif self._resolved_level == Level.LOW:
                self.on_falling()

    def snapshot(self):
        """Take a snapshot of our current level so the caller can save it
        and use it in comparisons later."""
        snap = LogicInput(default=self._resolved_level)
        snap._incoming_level = self._resolved_level
        snap._resolved_level = self._resolved_level
        return snap

    def _resolve_level(self):
        if self._incoming_level == Level.FLOATING:
            return self._default_level
        return self._incoming_level


class Inverter(object):
    """Inverts the signal: HIGH becomes LOW, LOW becomes HIGH."""

    def __init__(self):
        self.input = LogicInput()
        self.output = LogicOutput()
        self.input.on_rising = self.output.set_low
        self.input.on_falling = self.output.set_high
