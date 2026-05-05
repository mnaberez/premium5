from k0emu.devices import (MemoryDevice, RegisterFileDevice,
                           ProcessorStatusDevice,
                           ADCDevice, I2CControllerDevice,
                           InterruptControllerDevice,
                           WatchdogDevice, WatchTimerDevice,
                           FreeRunningTimerDevice)
from k0emu.i2c import StubI2CTarget
from k0emu.processor import Processor
from premium5.devices import (Port0Device, Port2Device, Port3Device,
                              Port4Device, Port5Device, Port6Device,
                              Port7Device, Port8Device, Port9Device)
from premium5.devices import SPIControllerDevice
from premium5.digital import CSI30Mux
from premium5.fis import FIS
from premium5.i2c import M24C04
from premium5.spi import UPD16432B


def make_processor():
    """Build a Processor with the default bus and memory layout
    for the uPD78F0831Y."""
    proc = Processor()

    rom = MemoryDevice("rom", size=0xF000, fill=0xFF, writable=False)
    proc.bus.add_device(rom, (0x0000, 0xEFFF))

    expansion_ram = MemoryDevice("expansion_ram", size=0x0800)
    proc.bus.add_device(expansion_ram, (0xF000, 0xF7FF))

    reserved = MemoryDevice("reserved", size=0x0300, fill=0x08, writable=False)
    proc.bus.add_device(reserved, (0xF800, 0xFAFF))

    high_speed_ram = MemoryDevice("high_speed_ram", size=0x03E0, high_speed=True)
    proc.bus.add_device(high_speed_ram, (0xFB00, 0xFEDF))

    register_file = RegisterFileDevice("register_file", high_speed=True)
    proc.bus.add_device(register_file, (0xFEE0, 0xFEFF))

    from premium5.digital import Level, LogicOutput

    p0 = Port0Device()
    proc.bus.add_device(p0, (0xFF00, 0xFF00), (0xFF20, 0xFF20), (0xFF30, 0xFF30),
                            (0xFF48, 0xFF48), (0xFF49, 0xFF49))

    # P0.1/INTP1: firmware checks this pin during power-on.
    # Must be HIGH or the power-on sequence fails.
    p01_driver = LogicOutput(Level.HIGH)
    p01_driver.bind(p0.pins[1].input)

    p2 = Port2Device()
    proc.bus.add_device(p2, (0xFF02, 0xFF02), (0xFF22, 0xFF22), (0xFF32, 0xFF32))

    p3 = Port3Device()
    proc.bus.add_device(p3, (0xFF03, 0xFF03), (0xFF23, 0xFF23), (0xFF33, 0xFF33))

    p4 = Port4Device()
    proc.bus.add_device(p4, (0xFF04, 0xFF04), (0xFF24, 0xFF24), (0xFF34, 0xFF34))

    p5 = Port5Device()
    proc.bus.add_device(p5, (0xFF05, 0xFF05), (0xFF25, 0xFF25), (0xFF35, 0xFF35))

    p6 = Port6Device()
    proc.bus.add_device(p6, (0xFF06, 0xFF06), (0xFF26, 0xFF26), (0xFF36, 0xFF36))

    p7 = Port7Device()
    proc.bus.add_device(p7, (0xFF07, 0xFF07), (0xFF27, 0xFF27), (0xFF37, 0xFF37))

    p8 = Port8Device()
    proc.bus.add_device(p8, (0xFF08, 0xFF08), (0xFF28, 0xFF28))

    p9 = Port9Device()
    proc.bus.add_device(p9, (0xFF09, 0xFF09), (0xFF29, 0xFF29))

    # P9.0 = S-Contact (ignition). Drive LOW = ignition off.
    s_contact = LogicOutput(Level.LOW)
    s_contact.bind(p9.pins[0].input)

    processor_status = ProcessorStatusDevice("processor_status")
    proc.bus.add_device(processor_status, (0xFF1C, 0xFF1E))

    intc = InterruptControllerDevice("intc")
    proc.bus.add_device(intc, (0xFFE0, 0xFFEB))
    proc.bus.set_interrupt_controller(intc)

    for bit in range(8):
        intc.connect(p0, bit, getattr(intc, 'INTP%d' % bit))

    i2c = I2CControllerDevice("iic0")
    proc.bus.add_device(i2c, (0xFF1F, 0xFF1F), (0xFFA8, 0xFFAA))
    intc.connect(i2c, i2c.INT_TRANSFER, intc.INTIIC0)
    eeprom_data = bytearray(b'\xFF' * 512)
    i2c.add_target(0x50, M24C04(eeprom_data, page_offset=0))
    i2c.add_target(0x51, M24C04(eeprom_data, page_offset=256))
    i2c.add_target(0x1C, StubI2CTarget())  # SAA7705H audio DSP
    i2c.add_target(0x22, StubI2CTarget())  # TDA7476 audio

    upd = UPD16432B()
    csi30 = SPIControllerDevice("csi30")
    csi30_mux = CSI30Mux()
    p4.pins[3].output.bind(csi30_mux.p43_in)
    csi30.clk_out.bind(csi30_mux.clk_from_csi30_in)
    csi30.dat_out.bind(csi30_mux.dat_from_csi30_in)
    csi30_mux.clk_to_upd_out.bind(upd.clk_in)
    csi30_mux.dat_to_upd_out.bind(upd.dat_in)
    p4.pins[7].output.bind(upd.stb_in)
    upd.dat_out.bind(csi30.dat_in)
    csi30.upd = upd  # XXX smell: stashing on an unrelated device

    # FIS (3LB)
    fis = FIS()
    csi30_mux.clk_to_fis_out.bind(fis.clk_in)
    csi30_mux.dat_to_fis_out.bind(fis.dat_in)
    p4.pins[4].output.bind(fis.ena_in)
    fis.ena_out.bind(p4.pins[5].input)
    csi30.fis = fis  # XXX smell: stashing on an unrelated device
    proc.bus.add_device(csi30, (0xFF1A, 0xFF1A), (0xFFB0, 0xFFB0))
    intc.connect(csi30, csi30.INT_TRANSFER, intc.INTCSI30)

    # CSI31 (CDC) not mapped — no CD changer connected.
    # FF1B and FFB8 are unmapped; firmware writes are ignored.

    tm01 = FreeRunningTimerDevice("tm01")
    proc.bus.add_device(tm01, (0xFF14, 0xFF15))

    adc = ADCDevice("adc", result=0x8C)  # 14.0V typical car battery
    proc.bus.add_device(adc, (0xFF17, 0xFF17), (0xFF80, 0xFF81))
    intc.connect(adc, adc.INT_COMPLETE, intc.INTAD00)

    watch_timer = WatchTimerDevice("watch_timer")
    proc.bus.add_device(watch_timer, (0xFF41, 0xFF41))
    intc.connect(watch_timer, watch_timer.INT_PRESCALER, intc.INTWTNI0)
    intc.connect(watch_timer, watch_timer.INT_WATCH, intc.INTWTN0)

    watchdog = WatchdogDevice("watchdog")
    proc.bus.add_device(watchdog, (0xFF42, 0xFF42), (0xFFF9, 0xFFF9))
    intc.connect(watchdog, watchdog.INT_OVERFLOW, intc.INTWDT)

    return proc
