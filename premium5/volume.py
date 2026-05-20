from premium5.digital import LogicOutput, Level


class VolumeKnob:
    """Rotary encoder for the volume knob.

    Drives two outputs (phase A and phase B) through a
    Gray code sequence to simulate turning the knob.
    """

    # Gray code states (phase_a, phase_b).
    #   Forward iteration (+1) = clockwise         (volume up)
    #   Reverse iteration (-1) = counter-clockwise (volume down)
    #           (A, B), (A, B), (A, B), (A, B)
    SEQUENCE = ((0, 0), (1, 0), (1, 1), (0, 1),)

    # Ticks between each transition of the Gray code sequence.
    # The firmware polls the encoder once per watch timer
    # interrupt (about every 1ms).  We need at least one
    # poll between transitions so the firmware sees each one.
    # 5ms/transition, 1 detent = 2 transitions, so 10ms/detent.
    TICKS_PER_TRANSITION = 5 * 1000

    # One detent = one increment/decrement of volume change.  A real
    # encoder produces 2 state transitions per detent.
    TRANSITIONS_PER_DETENT = 2

    def __init__(self):
        self.phase_a_out = LogicOutput(Level.LOW)
        self.phase_b_out = LogicOutput(Level.LOW)

        self._seq_index = 0              # current position in gray code sequence
        self._seq_direction = 0          # up/clockwise=1, down/counter-clockwise=-1
        self._transitions_remaining = 0  # transitions left to clock out
        self._transition_countdown = 0   # number of ticks remaining on current state

    def up(self):
        """Queue one detent clockwise (volume up)."""
        self._seq_direction = 1  # clockwise
        self._transitions_remaining = self.TRANSITIONS_PER_DETENT

    def down(self):
        """Queue one detent counter-clockwise (volume down)."""
        self._seq_direction = -1  # counter-clockwise
        self._transitions_remaining = self.TRANSITIONS_PER_DETENT

    def tick_1mhz(self, ticks=1):
        if self._transitions_remaining == 0:
            return

        self._transition_countdown -= ticks
        if self._transition_countdown > 0:
            return

        self._seq_index = (self._seq_index + self._seq_direction) % len(self.SEQUENCE)

        a, b = self.SEQUENCE[self._seq_index]
        self.phase_a_out.set_level_from(a)
        self.phase_b_out.set_level_from(b)

        self._transitions_remaining -= 1
        self._transition_countdown = self.TICKS_PER_TRANSITION
