from premium5.digital import Level, LogicInput, LogicOutput


class FISReceiver(object):
    """Instrument cluster side of the 3LB (FIS) bus.

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

    def __init__(self):
        # electrical interface
        self.clk_in = LogicInput()
        self.dat_in = LogicInput()
        self.ena_in = LogicInput()
        self.ena_out = LogicOutput(Level.LOW)

        # received display data
        self.radio_data = bytearray()

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
            # Packet complete: process it and return to idle
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

        if self._packet[0] == 0x81:
            self.radio_data = bytearray(self._packet[2:-1])

    def _transition(self, state):
        self._state = state
        self._countdown = state.ticks

    def _abort(self, reason):
        # self._state can be interrogated here to see what aborted
        self.ena_out.set_low()
        self._transition(self.WAITING_FOR_ENA_RISE)
