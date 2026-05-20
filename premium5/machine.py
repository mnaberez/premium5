from k0emu.i2c import StubI2CTarget
from premium5.cdc import CDC
from premium5.digital import Demux, Level
from premium5.fis import FIS
from premium5.mfsw import MFSW
from premium5.i2c import M24C04
from premium5.mcu import UPD78F0831Y
from premium5.spi import UPD16432B
from premium5.timing import ReferenceTick
from premium5.volume import VolumeKnob

class Machine:
    """The Premium 5 radio board: MCU + external devices."""

    def __init__(self, system_clock_hz):
        self.mcu = UPD78F0831Y()
        self.ref_tick = ReferenceTick(system_clock_hz)

        self._init_forced_pins()
        self._init_i2c_targets()
        self._init_upd16432b_and_fis()
        self._init_volume_knob()
        self._init_mfsw()
        self._init_cdc()

    def _init_forced_pins(self):
        # P0.1/INTP1: firmware checks this pin during power-on.
        # Must be HIGH or the power-on sequence fails.
        self.mcu.p0.pins[1].input.stuck(Level.HIGH)

        # P9.0 = S-Contact (ignition). Drive LOW = ignition off.
        self.mcu.p9.pins[0].input.stuck(Level.LOW)

    def _init_i2c_targets(self):
        i2c = self.mcu.proc.bus.device("iic0")
        eeprom_data = bytearray(b'\xFF' * 512)
        i2c.add_target(0x50, M24C04(eeprom_data, page_offset=0))
        i2c.add_target(0x51, M24C04(eeprom_data, page_offset=256))
        i2c.add_target(0x1C, StubI2CTarget())  # SAA7705H audio DSP
        i2c.add_target(0x22, StubI2CTarget())  # TDA7476 audio

    def _init_upd16432b_and_fis(self):
        """
        The radio uses the SPI controller CSI30 for both its own
        display (the uPD16432B) and the external FIS interface (3LB).
        The firmware sets P4.3 to HIGH whenever it wants to talk to
        the FIS, otherwise it leaves P4.3 low.

        Guess:
            P4.3 controls some sort of switch circuitry.  Its function
            is probably to prevent CLK and DAT changes from "leaking"
            out to the FIS while the uPD16432B is being accessed.  It
            might also prevent the uPD16432B from seeing CLK and DAT
            changes when the FIS is being used.

        This emulation is an isolator:
            When P4.3 is LOW:  CSI30 drives the uPD16432B, FIS floats
            When P4.3 is HIGH: CSI30 drives the FIS bus, uPD16432B floats
        """
        clk_demux, dat_demux = Demux(), Demux()
        self.mcu.p4.pins[3].output.drives(clk_demux.select_in,
                                          dat_demux.select_in)
        self.mcu.p32_sck30_out.drives(clk_demux.input)
        self.mcu.p31_so30_out.drives(dat_demux.input)

        self.upd = UPD16432B()
        clk_demux.output_a.drives(self.upd.clk_in)
        dat_demux.output_a.drives(self.upd.dat_in)
        self.mcu.p4.pins[7].output.drives(self.upd.stb_in)
        self.upd.dat_out.drives(self.mcu.p30_si30_in)

        self.fis = FIS()
        self.ref_tick.add_listener(self.fis.tick_1mhz)
        clk_demux.output_b.drives(self.fis.clk_in)
        dat_demux.output_b.drives(self.fis.dat_in)
        self.mcu.p4.pins[4].output.drives(self.fis.ena_in)
        self.fis.ena_out.drives(self.mcu.p4.pins[5].input)

    def _init_volume_knob(self):
        self.volume_knob = VolumeKnob()
        self.ref_tick.add_listener(self.volume_knob.tick_1mhz)

        # P4.0 = encoder phase A, P4.1 = encoder phase B
        self.volume_knob.phase_a_out.drives(self.mcu.p4.pins[0].input)
        self.volume_knob.phase_b_out.drives(self.mcu.p4.pins[1].input)

    def _init_mfsw(self):
        self.mfsw = MFSW()
        self.ref_tick.add_listener(self.mfsw.tick_1mhz)
        self.mfsw.swc_out.inverted().drives(self.mcu.p0.pins[0].input)

    def _init_cdc(self):
        self.cdc = CDC()
        self.ref_tick.add_listener(self.cdc.tick_1mhz)

        # P5.7 CDC DO (command from radio, inverted through HEF40106BT)
        self.mcu.p5.pins[7].output.inverted().drives(self.cdc.cmd_in)

        # CDC CLK -> inverter (HEF40106BT) -> P2.2/SCK31
        self.cdc.clk_out.inverted().drives(self.mcu.p22_sck31_in)

        # CDC DAT -> inverter (HEF40106BT) -> P2.0/SI31
        self.cdc.dat_out.inverted().drives(self.mcu.p20_si31_in)

    def advance(self, cycles):
        self.ref_tick.advance(cycles)
