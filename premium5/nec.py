"""NEC PWM transmitter and receiver

Both the output from the MFSW and the input to the CDC use a PWM protocol
like NEC infrared remotes:  A transmission is always a packet of four
bytes where the first two bytes are always the same, the third byte is a
command code, and the fourth byte is the complement of the command code.

In PWM, encoding a bit has two phases: the active phase (mark), which
is HIGH here, and the inactive phase (space), which is LOW here.  Every
bit is a mark (HIGH) followed by a space (LOW).  The duration of the mark
is always the same; the duration of the space varies (that's the "pulse
width" in PWM).  The start bit has an extra-long mark and space.

Timing (from Premium 5 firmware's CDC transmitter):
    Idle: LOW
    Start bit: 9.0ms HIGH, 4.5ms LOW
    0-bit: 0.56ms HIGH, 0.56ms LOW
    1-bit: 0.56ms HIGH, 1.69ms LOW

MFSW->Radio packet:             Radio->CDC packet:
    byte 0: 0x82 (always)           byte 0: 0xCA (always)
    byte 1: 0x17 (always)           byte 1: 0x34 (always)
    byte 2: command                 byte 2: command
    byte 3: command ^ 0xFF          byte 3: command ^ 0xFF
"""

from premium5.digital import Level, LogicInput, LogicOutput


class NECTransmitter:

    # Symbol phases
    SENDING_MARK = 0
    SENDING_SPACE = 1

    def __init__(self, header0, header1, on_complete):
        """Calls on_complete when a packet has been sent. """

        self._header0 = header0
        self._header1 = header1
        self.on_complete = on_complete

        self.data_out = LogicOutput(Level.LOW)

        self._symbols = []
        self._phase = self.SENDING_MARK
        self._ticks = 0

    def send(self, command):
        """Send a command"""

        packet = self._build_packet(command)
        self._symbols = self._build_symbols(packet)

        self.data_out.set_high() # mark=HIGH
        self._phase = self.SENDING_MARK
        self._ticks = 0

    def tick_1mhz(self, ticks=1):
        """Work through the FIFO buffer of symbols to transmit.  There are
        two phases to transmitting a symbol: mark then space.  After a symbol
        has been transmitted, it is popped off.  When all elements are popped
        off, the entire packet has been transmitted. 
        Ticked at 1 MHz, so 1 tick = 1 us."""

        for _ in range(ticks):
            if not self._symbols:
                return # not transmitting

            self._ticks += 1
            symbol = self._symbols[0]

            if self._phase == self.SENDING_MARK:
                if self._ticks == symbol.mark_ticks:
                    self._ticks = 0
                    self.data_out.set_low() # space=LOW
                    self._phase = self.SENDING_SPACE

            elif self._phase == self.SENDING_SPACE:
                if self._ticks == symbol.space_ticks:
                    self._ticks = 0
                    self._symbols.pop(0)

                    if self._symbols:
                        self.data_out.set_high() # mark=HIGH
                        self._phase = self.SENDING_MARK
                    else:
                        self.on_complete()
                        return

    @property
    def busy(self):
        return bool(self._symbols)

    def _build_packet(self, command):
        """Build a complete 4-byte packet for a command byte"""
        checksum = command ^ 0xFF
        return (self._header0, self._header1, command, checksum)

    def _build_symbols(self, packet):
        """Build a list of symbols to transmit for a packet"""
        symbols = [START_SYMBOL]
        for byte_val in packet:
            for bit_pos in range(8):
                bit = (byte_val >> bit_pos) & 1
                symbols.append(ONE_SYMBOL if bit else ZERO_SYMBOL)
        symbols.append(STOP_SYMBOL)
        return symbols


class NECReceiver:

    # Measurement phases
    MEASURING_UNKNOWN = 0     # no edges received yet
    MEASURING_MARK = 1        # after rising edge, measuring mark
    MEASURING_SPACE = 2       # after falling edge, measuring space

    # State machine
    AWAITING_START = 0        # receiving the start bit
    RECEIVING_DATA = 1        # receiving data bits

    def __init__(self, header0, header1, on_command):
        """Calls on_command(command) when a valid command is received."""

        self._header0 = header0
        self._header1 = header1
        self.on_command = on_command

        self.data_in = LogicInput()
        self.data_in.on_rising(self._on_rising)
        self.data_in.on_falling(self._on_falling)

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
        if self._mark_ticks > TIMEOUT_TICKS:
            self._state = self.AWAITING_START
            self._bits = []
        elif self._space_ticks > TIMEOUT_TICKS:
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

        if START_SYMBOL.detect(mark_ticks, space_ticks):
            # Receiving the start bit at any time, even if we've already
            # begun receiving bits, (re)starts receiving data.
            self._state = self.RECEIVING_DATA
            self._bits = []

        elif self._state == self.RECEIVING_DATA:
            if ZERO_SYMBOL.detect(mark_ticks, space_ticks):
                self._bits.append(0)

            elif ONE_SYMBOL.detect(mark_ticks, space_ticks):
                self._bits.append(1)

    def _on_bits_complete(self, bits):
        packet = self._packetize(bits)

        if len(packet) != 4:
            return # bad packet size

        if packet[0:1+1] != [self._header0, self._header1]:
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


class Symbol:
    """A symbol is a mark of a certain duration followed by a
       space of a certain duration."""

    def __init__(self, mark_ticks, space_ticks):
        self.mark_ticks = mark_ticks
        self.space_ticks = space_ticks

        r = lambda t: range(int(t * 0.80), int(t * 1.20) + 1)
        self._mark = r(mark_ticks)
        self._space = r(space_ticks)

    def detect(self, mark_ticks, space_ticks):
        """Detect if the given mark and space durations are
           within +/- 20% of this symbol"""
        return (mark_ticks in self._mark) and (space_ticks in self._space)


# Symbols.  Nominal durations in ticks (1 tick = 1 microsecond).
# Derived from the firmware's CDC transmitter CR011 offsets at 4.19 MHz.
START_SYMBOL = Symbol(
    mark_ticks=9009,  # 9.0ms HIGH    0x9374 (37748 cycles) = 9009us
    space_ticks=4505, # 4.5ms LOW     0x49BA (18874) = 4505us
)

ZERO_SYMBOL = Symbol(
    mark_ticks=563,   # 0.56ms HIGH   0x0937 (2359) = 563us
    space_ticks=563,  # 0.56ms LOW    0x0937 (2359) = 563us
)

ONE_SYMBOL = Symbol(
    mark_ticks=563,   # 0.56ms HIGH   0x0937 (2359) = 563us
    space_ticks=1689, # 1.69ms LOW    0x1BA5 (7077) = 1689us
)

STOP_SYMBOL = Symbol(
    mark_ticks=ZERO_SYMBOL.mark_ticks, # same as data mark per NEC
    space_ticks=1,                     # return line to idle
)

# Timeout: If no more edges are received for this long, the packet is
# over.  This is not derived from the firmware; it's a duration we
# made up that is longer than the longest symbol.
TIMEOUT_TICKS = START_SYMBOL.mark_ticks + START_SYMBOL.space_ticks + 1000
