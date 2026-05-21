from collections import deque, namedtuple

from premium5.digital import LogicOutput, Level


class VolumeKnob:
    """Rotary encoder for the volume knob.

    Drives two outputs (phase A and phase B) through a
    Gray code sequence to simulate turning the knob.
    """

    # One detent = one increment/decrement.  The real encoder
    # produces 2 Gray code state transitions per detent.
    STATES_PER_DETENT = 2

    # Amount of time to hold each Gray code state on the
    # outputs before moving to the next one.  This must be
    # longer than the firmware's polling interval (~1ms).
    STATE_HOLD_TICKS = 5 * 1000

    def __init__(self):
        # electrical interface
        self.phase_a_out = LogicOutput()
        self.phase_b_out = LogicOutput()

        self._gray_codes = _GrayCodeIterator()
        self._waveform = deque()

        initial_state = next(self._gray_codes)
        self.phase_a_out.set_level(initial_state.phase_a_level)
        self.phase_b_out.set_level(initial_state.phase_b_level)

    def up(self):
        """Turn the knob one detent clockwise (volume up)"""
        self._enqueue_detent(self._gray_codes.CLOCKWISE)

    def down(self):
        """Turn the knob one detent counter-clockwise (volume down)"""
        self._enqueue_detent(self._gray_codes.COUNTERCLOCKWISE)

    def _enqueue_detent(self, direction):
        self._gray_codes.direction = direction

        for _ in range(self.STATES_PER_DETENT):
            gray_code_state = next(self._gray_codes)
            step = _WaveformStep(gray_code_state, self.STATE_HOLD_TICKS)
            self._waveform.append(step)

    def tick_1mhz(self, ticks=1):
        for _ in range(ticks):
            if not self._waveform:
                return

            step = self._waveform[0]

            if step.remaining_ticks == step.total_ticks:  # not output yet
                self.phase_a_out.set_level(step.state.phase_a_level)
                self.phase_b_out.set_level(step.state.phase_b_level)

            step.remaining_ticks -= 1
            if not step.remaining_ticks:
                self._waveform.popleft()


class _WaveformStep:
    """One step in the encoder waveform: a Gray code state
    held for a number of ticks."""

    def __init__(self, state, ticks):
        self.state = state
        self.total_ticks = ticks
        self.remaining_ticks = ticks


_GrayCodeState = namedtuple('_GrayCodeState', 
    ('phase_a_level', 'phase_b_level')
)


class _GrayCodeIterator:
    """Generates an infinite sequence of Gray codes.
    Set the direction and call next() on it to get the
    next Gray code in that direction."""

    CLOCKWISE = 1
    COUNTERCLOCKWISE = -1

    _SEQUENCE = (
        _GrayCodeState(Level.LOW,  Level.LOW),  # (0,0)
        _GrayCodeState(Level.HIGH, Level.LOW),  # (1,0)
        _GrayCodeState(Level.HIGH, Level.HIGH), # (1,1)
        _GrayCodeState(Level.LOW,  Level.HIGH), # (0,1)
    )

    def __init__(self):
        self.direction = self.CLOCKWISE
        self._index = len(self._SEQUENCE) - 1  # last, so next is first

    def __iter__(self):
        return self

    def __next__(self):
        self._index = (self._index + self.direction) % len(self._SEQUENCE)
        return self._SEQUENCE[self._index]
