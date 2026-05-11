from premium5.digital import LogicInput, LogicOutput


class CDC:
    """Stub for the CD changer"""

    def __init__(self):
        self._rx = CDCReceiver(self._on_command)

        # electrical interface
        self.cmd_in = self._rx.cmd_in
        self.clk_out = LogicOutput()
        self.dat_out = LogicOutput()

    def tick_1mhz(self, ticks):
        self._rx.tick_1mhz(ticks)


class CDCReceiver:
    """Receives command packets from the radio.  A command packet consists
    of four bytes, with the third byte being a command for the CD changer
    to process.  The packet is transmitted over a single wire using a PWM
    scheme similar to NEC infrared remotes.

    In PWM, encoding a bit has two phases: the active phase (mark), which
    is HIGH here, and the inactive phase (space), which is LOW here.  Every
    bit is a mark (HIGH) followed by a space (LOW).  The duration of the mark
    is always the same; the duration of the space varies (that's the "pulse
    width" in PWM).  The start bit has an extra-long mark and space.

    Timing (from Premium 5 firmware):
        Idle: LOW
        Start bit: 9.0ms HIGH, 4.5ms LOW
        0-bit: 0.56ms HIGH, 0.56ms LOW
        1-bit: 0.56ms HIGH, 1.69ms LOW

    Packet (always 4 bytes, LSB first):
        byte 0: 0xCA (always)
        byte 1: 0x34 (always)
        byte 2: command
        byte 3: command ^ 0xFF
    """

    # Nominal durations in ticks (1 tick = 1 microsecond)
    # Derived from firmware CR011 offsets at 4.19 MHz.
    START_MARK_TICKS  = 9009  # 9.0ms HIGH    0x9374 (37748 cycles) = 9009us
    START_SPACE_TICKS = 4505  # 4.5ms LOW     0x49BA (18874) = 4505us
    DATA_MARK_TICKS   = 563   # 0.56ms HIGH   0x0937 (2359) = 563us
    ZERO_SPACE_TICKS  = 563   # 0.56ms LOW    0x0937 (2359) = 563us
    ONE_SPACE_TICKS   = 1689  # 1.69ms LOW    0x1BA5 (7077) = 1689us

    # Timeout: If no edges for this long, packet is over.  This is
    # not derived from the firmware; it's a duration we made up that
    # is longer than the longest symbol.
    TIMEOUT_TICKS = START_MARK_TICKS + START_SPACE_TICKS + 1000 

    class _Symbol:
        """A symbol is a mark of a certain duration followed by a
           space of a certain duration."""

        def __init__(self, mark_ticks, space_ticks):
            r = lambda t: range(int(t * 0.80), int(t * 1.20) + 1)
            self._mark = r(mark_ticks)
            self._space = r(space_ticks)

        def detect(self, mark_ticks, space_ticks):
            """Detect if the mark and space durations are within
               +/- 20% of this symbol"""
            return (mark_ticks in self._mark) and (space_ticks in self._space)

    # Symbols
    START_SYMBOL = _Symbol(START_MARK_TICKS, START_SPACE_TICKS)
    ZERO_SYMBOL  = _Symbol(DATA_MARK_TICKS, ZERO_SPACE_TICKS)
    ONE_SYMBOL   = _Symbol(DATA_MARK_TICKS, ONE_SPACE_TICKS)

    # Measurement phases
    MEASURING_UNKNOWN = 0     # no edges received yet
    MEASURING_MARK = 1        # after rising edge, measuring mark
    MEASURING_SPACE = 2       # after falling edge, measuring space

    # State machine
    AWAITING_START = 0        # receiving the start bit
    RECEIVING_DATA = 1        # receiving data bits

    def __init__(self, on_command):
        """Calls on_command(command) when a valid command is received."""

        self.cmd_in = LogicInput()
        self.cmd_in.on_rising(self._on_rising)
        self.cmd_in.on_falling(self._on_falling)

        self.on_command = on_command

        self._state = self.AWAITING_START
        self._phase = self.MEASURING_UNKNOWN
        self._mark_ticks = 0
        self._space_ticks = 0
        self._bits = []

    def tick_1mhz(self, ticks):
        # keep measuring the current mark/space
        if self._phase == self.MEASURING_MARK:
            self._mark_ticks += ticks
        elif self._phase == self.MEASURING_SPACE:
            self._space_ticks += ticks

        # timeout: either an error or end of packet
        if self._mark_ticks > self.TIMEOUT_TICKS:
            self._state = self.AWAITING_START
            self._bits = []
        elif self._space_ticks > self.TIMEOUT_TICKS:
            if self._state == self.RECEIVING_DATA:
                self._on_bits_complete(self._bits)
                self._state = self.AWAITING_START
                self._bits = []

    def _on_rising(self):
        """Rising edge: start of a mark"""

        if self._phase == self.MEASURING_SPACE:
            self._on_symbol(self._mark_ticks, self._space_ticks)

        self._phase = self.MEASURING_MARK
        self._mark_ticks = 0

    def _on_falling(self):
        """Falling edge: start of a space"""

        self._phase = self.MEASURING_SPACE
        self._space_ticks = 0

    def _on_symbol(self, mark_ticks, space_ticks):
        """Received a mark followed by a space: that's a symbol.  Now
        we need to decode which symbol by comparing the pulse lengths."""

        if self.START_SYMBOL.detect(mark_ticks, space_ticks):
            # Receiving the start bit at any time, even if we've already
            # begun receiving bits, (re)starts receiving data.
            self._state = self.RECEIVING_DATA
            self._bits = []

        elif self._state == self.RECEIVING_DATA:
            if self.ZERO_SYMBOL.detect(mark_ticks, space_ticks):
                self._bits.append(0)

            elif self.ONE_SYMBOL.detect(mark_ticks, space_ticks):
                self._bits.append(1)

    def _on_bits_complete(self, bits):
        packet = self._packetize(bits)

        if len(packet) != 4:
            return # bad packet size

        if packet[0:1+1] != [0xCA, 0x34]:
            return # bad headers

        if packet[3] != (packet[2] ^ 0xFF):
            return # bad checksum

        self.on_command(packet[2])

    def _packetize(self, bits):
        """Decode bitstream into packet of bytes, LSB first"""
        packet, current_byte, bit_pos = [], 0, 0
        for bit in bits:
            current_byte |= (bit << bit_pos)
            bit_pos += 1
            if bit_pos == 8:
                packet.append(current_byte)
                current_byte, bit_pos = 0, 0
        return packet
