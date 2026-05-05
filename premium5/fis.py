from premium5.digital import Level, LogicInput, LogicOutput


class FIS:
    """FIS display in the instrument cluster.

    Receives packets from the radio via SPI ("3LB") and maintains
    a display buffer with what the FIS would display.

    This object is a facade for the receiver (wire protocol) and the
    interpreter (interprets commands).  The emulator should only be
    wired to this object, which exposes the electrical interface and
    the display data.  It needs to be ticked at 1 MHz by the
    ReferenceTick source so things like timeouts work.
    """

    def __init__(self):
        self._intp = FISInterpreter()
        self._recv = FISReceiver(self._intp.interpret)

        # electrical interface
        self.clk_in  = self._recv.clk_in
        self.dat_in  = self._recv.dat_in
        self.ena_in  = self._recv.ena_in
        self.ena_out = self._recv.ena_out

    @property
    def radio_data(self):
        return self._intp.radio_data

    def tick_1mhz(self, cycles=1):
        self._recv.tick_1mhz(cycles)


class FISReceiver:
    """FIS 3LB (three line bus) receiver.

    Receives bytes from the radio via CLK/DAT, with ENA handshaking.
    After the radio sends the first byte (signaled by ENA pulse on
    P4.4), the cluster drives ENA high on P4.5 to request each
    subsequent byte.

    SPI settings (confirmed by a logic analyzer capture of
                  the 3LB lines on the back of a cluster):

        CPOL=1: CLK idles HIGH
        CPHA=1: DAT is read on the falling (trailing) CLK edge
        MSB first, 8 bits per transfer

    CLK/DAT could in theory be directly connected to the radio's SPI controller
    CSI30.  In practice, they need to be connected through a transparent mux
    (CSI30Mux) because CSI30 is also used to drive the uPD16432B.

    This receiver handles the wire protocol only: SPI bit shifting, ENA
    handshake timing, packet assembly, and checksum validation.  When a
    valid packet is received, it fires a callback.
    """

    class _State:
        def __init__(self, ticks=0):
            self.ticks = ticks

    # States (ticks at 1 MHz, 1 tick = 1 us)
    #
    # The ENA pulse from the radio was measured to be about 26us, so we allow
    # it to be 10-50us.  All other timing values are best guesses.
    #
    WAITING_FOR_ENA_RISE = _State()            # idle, waiting for radio to initiate
    WAITING_FOR_ENA_MIN  = _State(ticks=10)    # 10us, reject glitches shorter than this
    WAITING_FOR_ENA_MAX  = _State(ticks=40)    # +40us (50us total), reject stuck ENA
    WAITING_FOR_CLK_FALL = _State(ticks=3000)  # 3ms, generous for firmware inter-byte gap
    RECEIVING_BIT        = _State(ticks=100)   # 100us, ~12x the 8us bit period at 125 kHz
    DELAYING_ENA_ACK     = _State(ticks=120)   # 120us, cluster processing time before ack

    def __init__(self, packet_callback):
        self._packet_callback = packet_callback

        # electrical interface
        self.clk_in = LogicInput()
        self.dat_in = LogicInput()
        self.ena_in = LogicInput()
        self.ena_out = LogicOutput(Level.LOW)

        # state machine
        self._state = self.WAITING_FOR_ENA_RISE
        self._countdown = 0

        # shift register / packet assembly
        self._shift_in = 0x00
        self._shift_count = 0
        self._packet = bytearray()
        self._bytes_expected = 0

        # callbacks
        self.clk_in.on_falling = self._on_clk_falling
        self.ena_in.on_rising = self._on_ena_rising
        self.ena_in.on_falling = self._on_ena_falling

    def tick_1mhz(self, cycles=1):
        if self._countdown > 0:
            self._countdown = max(self._countdown - cycles, 0)

        if self._state == self.WAITING_FOR_ENA_RISE:
            # We are waiting for the radio to initiate the transfer
            pass

        elif self._state == self.WAITING_FOR_ENA_MIN:
            # We got a rising edge on ENA and are waiting for the minimum pulse width

            if self._countdown == 0:
                # ENA held high for the minimum; if another edge had been
                # received, the on_falling callback would have aborted
                self._transition(self.WAITING_FOR_ENA_MAX)

        elif self._state == self.WAITING_FOR_ENA_MAX:
            # ENA has been held long enough and we're waiting for it to fall

            if self._countdown == 0:
                # ENA did not fall; if another edge had been received,
                # the on_falling callback would have transitioned
                self._abort("ENA stuck high")

        elif self._state == self.WAITING_FOR_CLK_FALL:
            # Either the ENA pulse was just received or we just received and acknowledged
            # a byte.  We are waiting for CLK to fall for the first bit of the next byte.
            # We give the radio a lot of time here (inter-byte delay).

            if self._countdown == 0:
                # timeout; if CLK had gone low, the on_falling callback
                # would have transitioned
                self._abort("Timeout waiting for first bit of byte")

        elif self._state == self.RECEIVING_BIT:
            # We are shifting in bits of a byte.  CLK edges within a byte
            # come much faster than the inter-byte gap.

            if self._countdown == 0:
                # timeout; if CLK had gone low, the on_falling callback
                # would have transitioned
                self._abort("Timeout waiting for successive bits in a byte")

        elif self._state == self.DELAYING_ENA_ACK:
            # We just received a complete byte.  We are waiting a bit of time before
            # we set ENA high to acknowledge it.

            if self._countdown == 0:
                # Time to acknowledge the byte
                self.ena_out.set_high()
                self._transition(self.WAITING_FOR_CLK_FALL)

    def _on_ena_rising(self):
        if self._state == self.WAITING_FOR_ENA_RISE:
            # Radio is initiating a new packet by pulsing ENA high
            self._shift_in = 0x00
            self._shift_count = 0
            self._packet = bytearray()
            self._bytes_expected = 0
            self._transition(self.WAITING_FOR_ENA_MIN)

        else:
            self._abort("spurious ENA rise mid-packet")

    def _on_ena_falling(self):
        if self._state == self.WAITING_FOR_ENA_MIN:
            self._abort("ENA pulse too short")

        elif self._state == self.WAITING_FOR_ENA_MAX:
            # Radio released ENA, pulse is complete; wait for first byte
            self._transition(self.WAITING_FOR_CLK_FALL)

        elif self._state != self.WAITING_FOR_ENA_RISE:
            self._abort("spurious ENA fall mid-packet")

    def _on_clk_falling(self):
        if self._state == self.WAITING_FOR_CLK_FALL:
            # First CLK edge of a new byte: pull our ENA low
            if self.ena_out.high:
                self.ena_out.set_low()

        elif self._state != self.RECEIVING_BIT:
            return

        # Shift in a bit on every CLK falling edge
        self._shift_in = (self._shift_in << 1) | int(self.dat_in)
        self._shift_count += 1
        self._transition(self.RECEIVING_BIT)

        if self._shift_count == 8:
            self._on_byte(self._shift_in & 0xFF)
            self._shift_in = 0x00
            self._shift_count = 0

    def _on_byte(self, byte):
        self._packet.append(byte)

        if len(self._packet) == 2:
            # Second byte is the length; compute total packet size
            self._bytes_expected = byte + 2

        if len(self._packet) == self._bytes_expected:
            # Packet complete: validate and deliver
            self._on_packet()
            self._transition(self.WAITING_FOR_ENA_RISE)
        else:
            # More bytes expected: schedule an ENA ack after a short delay
            self._transition(self.DELAYING_ENA_ACK)

    def _on_packet(self):
        if len(self._packet) < 3:
            return

        csum = 0
        for b in self._packet[:-1]:
            csum ^= b
        if self._packet[-1] != ((csum - 1) & 0xFF):
            return

        self._packet_callback(self._packet)

    def _transition(self, state):
        self._state = state
        self._countdown = state.ticks

    def _abort(self, reason):
        # self._state can be interrogated here to see what aborted
        self.ena_out.set_low()
        self._transition(self.WAITING_FOR_ENA_RISE)


class FISInterpreter:
    """Interprets FIS packets and updates display state."""

    def __init__(self):
        self.radio_data = bytearray(b'\x20' * 16)

    def interpret(self, packet):
        """Interpret the command in the FIS packet from the radio.  The
        packet must have already been validated (length and checksum)."""

        cmd = packet[0]
        if cmd == 0x81:
            self._cmd_radio_text(packet)

    def _cmd_radio_text(self, packet):
        # ensure we have exactly 16 bytes of printable ascii
        data = bytearray(packet[3:-1])[:16].ljust(16, b'\x20')
        for i in range(len(data)):
            if (data[i] < 0x20) or (data[i] >= 0x7f):
                data[i] = 0x20

        # split into two lines of 8 bytes, center justify each
        line1 = data[:8].strip(b'\x20').center(8, b'\x20')
        line2 = data[8:].strip(b'\x20').center(8, b'\x20')

        # recombine the filtered/justified lines
        self.radio_data = line1 + line2
