from k0emu.i2c import StubI2CTarget
from premium5.digital import Demux, Level, LogicOutput
from premium5.fis import FIS
from premium5.mfsw import MFSWTransmitter
from premium5.i2c import M24C04
from premium5.mcu import UPD78F0831Y
from premium5.spi import UPD16432B


class Machine:
    """The Premium 5 radio board: MCU + external devices."""

    def __init__(self):
        self.mcu = UPD78F0831Y()

        self._init_pin_drivers()
        self._init_i2c_targets()
        self._init_upd16432b_and_fis()
        self._init_mfsw()

    def _init_pin_drivers(self):
        # P0.1/INTP1: firmware checks this pin during power-on.
        # Must be HIGH or the power-on sequence fails.
        self._p01_driver = LogicOutput(Level.HIGH)
        self._p01_driver.drives(self.mcu.p0.pins[1].input)

        # P9.0 = S-Contact (ignition). Drive LOW = ignition off.
        self._s_contact = LogicOutput(Level.LOW)
        self._s_contact.drives(self.mcu.p9.pins[0].input)

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
        clk_demux.output_b.drives(self.fis.clk_in)
        dat_demux.output_b.drives(self.fis.dat_in)
        self.mcu.p4.pins[4].output.drives(self.fis.ena_in)
        self.fis.ena_out.drives(self.mcu.p4.pins[5].input)

    def _init_mfsw(self):
        self.mfsw = MFSWTransmitter()
        self.mfsw.swc_out.inverted().drives(self.mcu.p0.pins[0].input)
