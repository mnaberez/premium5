"""NEC PWM transmitter and receiver

Both the output from the MFSW and the input to the CDC use a PWM protocol
like NEC infrared remotes:  A transmission is always a packet of four
bytes where the first two bytes are always the same, the third byte is a
command code, and the fourth byte is the complement of the command code.

In PWM, every bit is encoded as a "symbol" which has two phases: the active
or "mark" phase, which is HIGH here, and the inactive or "space" phase, which
is LOW here.  The duration of the mark is always the same; the duration of
the space varies (that's the "pulse width" in PWM).  A packet consists of a
start symbol, 32 data bit symbols, and then a final HIGH pulse meaning stop.
The 32 data bits represent a packet of 4 bytes, where each byte is LSB-first.

Timing (from Premium 5 firmware's CDC transmitter):
    Idle: LOW
    Start: 9.00ms HIGH, 4.5ms LOW
    0-bit: 0.56ms HIGH, 0.56ms LOW
    1-bit: 0.56ms HIGH, 1.69ms LOW
    Stop : 0.56ms HIGH, then back to idle LOW

MFSW->Radio packet:             Radio->CDC packet:
    byte 0: 0x82 (always)           byte 0: 0xCA (always)
    byte 1: 0x17 (always)           byte 1: 0x34 (always)
    byte 2: command                 byte 2: command
    byte 3: command ^ 0xFF          byte 3: command ^ 0xFF

For the MFSW, there is also a "repeat last command" transmission consisting
of a repeat symbol (9.0ms HIGH, 2.4ms LOW) followed by the usual stop pulse.

See the bottom of the file for how the timing was derived.
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
        """Send the given command byte as a 4-byte packet."""

        packet = self._build_packet(command)
        self._symbols = self._build_symbols(packet)

        self.data_out.set_high() # mark=HIGH
        self._phase = self.SENDING_MARK
        self._ticks = 0

    def repeat(self):
        """Send a shorter transmission meaning repeat the last command"""

        self._symbols = [REPEAT_SYMBOL, STOP_SYMBOL]

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
    MEASURING_UNKNOWN = 0       # no edges received yet
    MEASURING_MARK = 1          # after rising edge, measuring mark
    MEASURING_SPACE = 2         # after falling edge, measuring space

    # State machine
    RECEIVING_FIRST_SYMBOL = 0  # waiting for start or repeat symbol
    RECEIVING_DATA = 1          # receiving data bits
    RECEIVING_STOP = 2          # waiting for stop pulse

    # Frame types
    FRAME_COMMAND = 0         # normal 4-byte command packet frame
    FRAME_REPEAT = 1          # short "repeat last command" frame

    def __init__(self, header0, header1, on_command, on_repeat):
        """Calls on_command(command) when a valid command is received.
        Calls on_repeat() when a repeat code is received."""

        self._header0 = header0
        self._header1 = header1
        self.on_command = on_command
        self.on_repeat = on_repeat

        self.data_in = LogicInput()
        self.data_in.on_rising(self._on_rising)
        self.data_in.on_falling(self._on_falling)

        self._phase = self.MEASURING_UNKNOWN
        self._reset()

    def _reset(self):
        self._state = self.RECEIVING_FIRST_SYMBOL
        self._frame = self.FRAME_COMMAND
        self._mark_ticks = 0
        self._space_ticks = 0
        self._bits = []

    def tick_1mhz(self, ticks):
        if self._phase == self.MEASURING_MARK:
            self._mark_ticks += ticks
            if self._mark_ticks > TIMEOUT_TICKS:
                self._reset()

        elif self._phase == self.MEASURING_SPACE:
            self._space_ticks += ticks
            if self._space_ticks > TIMEOUT_TICKS:
                self._reset()

    def _on_rising(self):
        """Rising edge: start of a mark"""

        if self._phase == self.MEASURING_SPACE:
            self._on_symbol(self._mark_ticks, self._space_ticks)

        self._phase = self.MEASURING_MARK
        self._mark_ticks = 0

    def _on_falling(self):
        """Falling edge: start of a space"""

        if self._state == self.RECEIVING_STOP:
            if self._mark_ticks in STOP_SYMBOL.mark_range:
                if self._frame == self.FRAME_COMMAND:
                    self._on_bits_complete(self._bits)
                elif self._frame == self.FRAME_REPEAT:
                    self.on_repeat()

            self._state = self.RECEIVING_FIRST_SYMBOL
            self._bits = []

        self._phase = self.MEASURING_SPACE
        self._space_ticks = 0

    def _on_symbol(self, mark_ticks, space_ticks):
        """Received a mark followed by a space: that's a symbol.  Now
        we need to decode which symbol by comparing the pulse lengths."""

        if self._state == self.RECEIVING_FIRST_SYMBOL:
            if START_SYMBOL.detect(mark_ticks, space_ticks):
                self._state = self.RECEIVING_DATA
                self._frame = self.FRAME_COMMAND

            elif REPEAT_SYMBOL.detect(mark_ticks, space_ticks):
                self._state = self.RECEIVING_STOP
                self._frame = self.FRAME_REPEAT

        elif self._state == self.RECEIVING_DATA:
            if ZERO_SYMBOL.detect(mark_ticks, space_ticks):
                self._bits.append(0)

            elif ONE_SYMBOL.detect(mark_ticks, space_ticks):
                self._bits.append(1)

            if len(self._bits) == 32:
                self._state = self.RECEIVING_STOP

    def _on_bits_complete(self, bits):
        """Received all bits of a command frame; decode the packet
        fire the callback if the packet is valid."""

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

        self.mark_range  = self._make_range(mark_ticks)
        self.space_range = self._make_range(space_ticks)

    def _make_range(self, nominal_ticks):
        """Build a range of 20% around the given ticks to use for detection"""
        tolerance = 0.20 # 20%
        min_ticks = max(1, int(nominal_ticks * (1.0 - tolerance)))
        max_ticks = int(nominal_ticks * (1.0 + tolerance))
        return range(min_ticks, max_ticks + 1)

    def detect(self, mark_ticks, space_ticks):
        """Detect if the given mark and space durations are
           within +/- 20% of this symbol"""
        return ((mark_ticks  in self.mark_range) and 
                (space_ticks in self.space_range))


# Symbols for the 32-bit packet were derived from the firmware's CDC
# transmitter offsets at 4.19 MHz.  Nominal duration in ticks (1 tick = 1us).

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
    mark_ticks=ZERO_SYMBOL.mark_ticks, # same 0x0937 (2359) as data bits
    space_ticks=1,                     # return line to idle
)

# The repeat symbol was derived from the firmware's MFSW receiver:
#   0x5A3D intp0_mfsw state 1 (mark is detected as between  6.0-12.0ms)
#   0x5A58 intp0_mfsw state 2 (space is detected as between 1.8- 3.0ms)

REPEAT_SYMBOL = Symbol(
    mark_ticks=9000,   # 9.0ms HIGH    midpoint of firmware's 6.0-12.0ms
    space_ticks=2400,  # 2.4ms LOW     midpoint of firmware's 1.8- 3.0ms
)

# Timeout: If no more edges are received for this long, the packet is
# over.  This is not derived from the firmware; it's a duration we
# made up that is longer than the longest symbol.
TIMEOUT_TICKS = START_SYMBOL.mark_ticks + START_SYMBOL.space_ticks + 1000
