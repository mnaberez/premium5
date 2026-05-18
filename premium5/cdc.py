from premium5.digital import Level, LogicOutput
from premium5.nec import NECReceiver


class CDC:
    """CD changer"""

    # 50ms between packets
    TICKS_BETWEEN_PACKETS = 50_000

    # Real CDC responds ~10ms after ENABLE
    TICKS_AFTER_ENABLE = 10_000

    # Commands from the radio
    CMD_ENABLE = 0x27
    CMD_DISABLE = 0x08
    CMD_MAGAZINE = 0x1C
    CMD_PREV_TRACK = 0x1E
    CMD_NEXT_TRACK = 0x1F
    CMD_CD1 = 0x30
    CMD_CD6 = 0x35

    def __init__(self):
        self._rx = NECReceiver(0xCA, 0x34, self._on_command, self._on_repeat)
        self._tx = CDCTransmitter()

        # electrical interface
        self.cmd_in = self._rx.data_in
        self.clk_out = self._tx.clk_out
        self.dat_out = self._tx.dat_out

        # CDC state
        self.enabled = False
        self._cd = 1
        self._track = 1
        self._packet_queue = []

        # packet scheduling
        self._idle_countdown = self.TICKS_BETWEEN_PACKETS

    def _on_command(self, cmd):
        if cmd == self.CMD_ENABLE:
            self.enabled = True
            self._idle_countdown = self.TICKS_AFTER_ENABLE
            self._queue_announcement_packets(ack=False)
        elif cmd == self.CMD_DISABLE:
            self.enabled = False
            self._packet_queue = []
        elif cmd == self.CMD_MAGAZINE:
            self._idle_countdown = 0
            self._queue_announcement_packets()
        elif cmd == self.CMD_NEXT_TRACK:
            self._track += 1
            self._idle_countdown = 0
            self._queue_track_change_packets()
        elif cmd == self.CMD_PREV_TRACK:
            if self._track > 1:
                self._track -= 1
            self._idle_countdown = 0
            self._queue_track_change_packets()
        elif self.CMD_CD1 <= cmd <= self.CMD_CD6:
            self._cd = cmd - self.CMD_CD1 + 1
            self._track = 1

    def _on_repeat(self):
        pass

    def _queue_track_change_packets(self):
        """Queue an ACK + transition for a track change.

        From capture: frame 0x94 (ACK), 0xB4 (transitioning),
        byte6=0xAF, time resets to 0:00.
        """
        cd = self._cd
        track = self._track
        self._packet_queue = [
            self.make_status_packet(cd, track, 0, 0, frame=0x94, byte6=0xAF),
            self.make_status_packet(cd, track, 0, 0, frame=0xB4, byte6=0xAF),
            self.make_status_packet(cd, track, 0, 0, frame=0xB4, byte6=0xAF),
        ]

    def _queue_announcement_packets(self, ack=True):
        """Queue the disc announcement sequence.

        If ack=True, starts with an ACK packet (for MAGAZINE).
        Then alternates status packets with announcement packets
        for each of the 6 CD slots, then a final status with
        byte 6 indicating normal play.
        """
        cd = self._cd
        track = self._track
        self._packet_queue = []
        if ack:
            self._packet_queue.append(
                self.make_status_packet(cd, track, 0, 0, frame=0x94, byte6=0xAF)
            )

        # status packet used during announcements:
        # frame=0xB4 (transitioning), byte6=0x6F (from capture)
        announce_status = self._make_announce_status_packet()

        for cd in range(1, 7):
            self._packet_queue.append(announce_status)
            self._packet_queue.append(self._make_disc_announcement(cd))

        # final status: transitioning, playing normally
        self._packet_queue.append(
            self.make_status_packet(self._cd, self._track, 0, 0, frame=0xB4, byte6=0xCF)
        )

    def _make_announce_status_packet(self):
        """Status packet sent between announcements.

        Frame=0xB4 (transitioning), byte6=0x6F (from capture).
        """
        frame = 0xB4
        byte1 = (~(0x40 | self._cd)) & 0xFF
        byte7 = frame | 0x08
        return [frame, byte1, 0xFF, 0xFF, 0xFF, 0xFF, 0x6F, byte7]

    def _make_disc_announcement(self, cd):
        """Announcement packet for a loaded audio CD."""
        frame = 0xB4  # transitioning
        byte1 = 0x20 | ((~cd) & 0x0F)  # bit 5 = audio, bit 6 clear = has disc
        byte2 = (~0x15) & 0xFF  # 15 tracks (BCD)
        byte3 = (~0x45) & 0xFF  # 45 minutes (BCD)
        byte4 = (~0x00) & 0xFF  # 0 seconds (BCD)
        byte7 = frame | 0x08
        return [frame, byte1, byte2, byte3, byte4, 0xFF, 0xFF, byte7]

    def tick_1mhz(self, ticks):
        self._rx.tick_1mhz(ticks)
        self._tx.tick_1mhz(ticks)

        if not self._tx.busy:
            self._idle_countdown -= ticks
            if self._idle_countdown <= 0:
                self._send_next_packet()

    # Heartbeat packet from real CDC capture (digital.csv).
    # Radio sees it arrive but doesn't parse it as status.
    HEARTBEAT_PACKET = [0x7A, 0x5F, 0x7F, 0x7F, 0xFF, 0xFF, 0xFF, 0xFE]

    def _send_next_packet(self):
        if not self.enabled:
            packet = self.HEARTBEAT_PACKET
        elif self._packet_queue:
            packet = self._packet_queue.pop(0)
        else:
            packet = self.make_status_packet(self._cd, self._track, 0, 0)

        self._tx.send_packet(packet)
        self._idle_countdown = self.TICKS_BETWEEN_PACKETS

    def make_status_packet(self, cd, track, minutes, seconds,
                           frame=0x34, byte6=0xCF):
        """Build an 8-byte status packet.

        All values are wire-level (before the radio's inverter).
        """
        def to_bcd_wire(value):
            bcd = ((value // 10) << 4) | (value % 10)
            return (~bcd) & 0xFF

        byte1 = (~(0x40 | cd)) & 0xFF
        byte2 = to_bcd_wire(track)
        byte3 = to_bcd_wire(minutes)
        byte4 = to_bcd_wire(seconds)
        byte5 = 0xFF  # no scan/mix
        byte7 = frame | 0x08

        return [frame, byte1, byte2, byte3, byte4, byte5, byte6, byte7]


class CDCTransmitter:
    """Clocks out SPI packets to the radio one tick at a time.

    Call send_packet(data_bytes) to start a transmission.
    Call tick_1mhz() on every microsecond.

    50 kBaud, MSB first, 1ms byte-to-byte.
    Clock idles LOW, radio latches data on falling edge (CPOL=0, CPHA=1).
    """

    # 50 kBaud: 20us per bit, 10us per half-period
    TICKS_PER_HALF_PERIOD = 10

    # 1ms byte-to-byte: 1000 - (8 bits * 2 half-periods * 10 ticks) = 840
    TICKS_BETWEEN_BYTES = 840

    def __init__(self):
        self.clk_out = LogicOutput(Level.LOW)
        self.dat_out = LogicOutput(Level.LOW)
        self._init_state()

    def _init_state(self):
        self._packet = []
        self._bit_index = 7
        self._clk_half_period_countdown = 0
        self._interbyte_gap_countdown = 0

    def send_packet(self, data_bytes):
        self._init_state()
        self._packet = list(data_bytes)

    @property
    def busy(self):
        return bool(self._packet)

    def tick_1mhz(self, ticks):
        for _ in range(ticks):
            if not self.busy:
                return

            # inter-byte gap: wait before starting next byte
            if self._interbyte_gap_countdown:
                self._interbyte_gap_countdown -= 1
                continue

            # clock half-period: wait before next edge
            if self._clk_half_period_countdown:
                self._clk_half_period_countdown -= 1
                continue

            self._clk_half_period_countdown = self.TICKS_PER_HALF_PERIOD

            if self.clk_out.low:
                self._drive_clk_high()
            else: # high
                self._drive_clk_low()

    def _drive_clk_high(self):
        """CLK is low and we are about to drive it high.  Radio latches DAT
        on the falling edge of CLK, so we update DAT first and then drive
        CLK high."""
        bit = (self._packet[0] >> self._bit_index) & 1
        self.dat_out.set_level_from(bit)
        self.clk_out.set_high()

    def _drive_clk_low(self):
        """CLK is high and we are about to drive it low.  We've just sent
        a bit so either set up for the next bit or we're done."""
        self.clk_out.set_low()

        if self._bit_index == 0:
            # bits 7..0 were sent; byte is complete
            self._packet.pop(0)
            self._bit_index = 7
            self._interbyte_gap_countdown = self.TICKS_BETWEEN_BYTES
        else:
            self._bit_index -= 1
