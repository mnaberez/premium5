from k0emu.i2c import StubI2CTarget
from premium5.digital import CSI30Demux, Inverter, Level, LogicOutput
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
        self._init_upd16432b()
        self._init_fis()
        self._init_mfsw()

    def _init_pin_drivers(self):
        # P0.1/INTP1: firmware checks this pin during power-on.
        # Must be HIGH or the power-on sequence fails.
        self._p01_driver = LogicOutput(Level.HIGH)
        self._p01_driver.bind(self.mcu.p0.pins[1].input)

        # P9.0 = S-Contact (ignition). Drive LOW = ignition off.
        self._s_contact = LogicOutput(Level.LOW)
        self._s_contact.bind(self.mcu.p9.pins[0].input)

    def _init_i2c_targets(self):
        i2c = self.mcu.proc.bus.device("iic0")
        eeprom_data = bytearray(b'\xFF' * 512)
        i2c.add_target(0x50, M24C04(eeprom_data, page_offset=0))
        i2c.add_target(0x51, M24C04(eeprom_data, page_offset=256))
        i2c.add_target(0x1C, StubI2CTarget())  # SAA7705H audio DSP
        i2c.add_target(0x22, StubI2CTarget())  # TDA7476 audio

    def _init_upd16432b(self):
        self.upd = UPD16432B()
        self._csi30_mux = CSI30Demux()
        self.mcu.p4.pins[3].output.bind(self._csi30_mux.p43_in)
        self.mcu.p32_sck30.bind(self._csi30_mux.clk_from_csi30_in)
        self.mcu.p31_so30.bind(self._csi30_mux.dat_from_csi30_in)
        self._csi30_mux.clk_to_upd_out.bind(self.upd.clk_in)
        self._csi30_mux.dat_to_upd_out.bind(self.upd.dat_in)
        self.mcu.p4.pins[7].output.bind(self.upd.stb_in)
        self.upd.dat_out.bind(self.mcu.p30_si30)

    def _init_fis(self):
        self.fis = FIS()
        self._csi30_mux.clk_to_fis_out.bind(self.fis.clk_in)
        self._csi30_mux.dat_to_fis_out.bind(self.fis.dat_in)
        self.mcu.p4.pins[4].output.bind(self.fis.ena_in)
        self.fis.ena_out.bind(self.mcu.p4.pins[5].input)

    def _init_mfsw(self):
        self.mfsw = MFSWTransmitter()
        inverter = Inverter()
        self.mfsw.swc_out.bind(inverter.input)
        inverter.output.bind(self.mcu.p0.pins[0].input)
