from k0emu.devices import (MemoryDevice, RegisterFileDevice,
                           ProcessorStatusDevice,
                           ADCDevice, I2CControllerDevice,
                           InterruptControllerDevice,
                           WatchdogDevice, WatchTimerDevice)
from k0emu.processor import Processor
from premium5.devices import (CompareMatchTimerDevice, Port0Device,
                              Port2Device, Port3Device, Port4Device,
                              Port5Device, Port6Device, Port7Device,
                              Port8Device, Port9Device)
from premium5.devices import SPIControllerDevice, UARTDevice
from premium5.digital import Mux, LogicInput, LogicOutput


class UPD78F0831Y:
    """NEC uPD78F0831Y microcontroller.

    Encapsulates everything inside the chip: the processor, its internal
    bus, memories, and on-chip peripherals.  Exposes an interface for
    wiring to the machine.
    """

    def __init__(self):
        self.proc = Processor()

        self._init_interface()
        self._init_memories()
        self._init_ports()
        self._init_interrupts()
        self._init_csi30()
        self._init_csi31()
        self._init_uart0()
        self._init_i2c()
        self._init_timers()

    def _init_interface(self):
        '''The rest of the machine should interface with the MCU
        primarily through these objects.'''

        # GPIO ports: All are exposed but in some cases, the physical pin on
        # the real MCU is multiplexed (e.g. GPIO or SPI depending on register
        # settings).  If a muxed signal is defined below, use it instead.
        self.p0 = None
        self.p2 = None
        self.p3 = None
        self.p4 = None
        self.p5 = None
        self.p6 = None
        self.p7 = None
        self.p8 = None
        self.p9 = None

        # Multiplexed pins: CSI30 muxed with GPIO
        self.p31_so30_out = None   # P3.1/SO30 output  (CSI30/P3 muxed)
        self.p32_sck30_out = None  # P3.2/SCK30 output (CSI30/P3 muxed)
        self.p30_si30_in = None    # P3.0/SI30 input   (CSI30/P3 muxed)

        # Multiplexed pins: CSI31 muxed with GPIO
        self.p22_sck31_in = None   # P2.2/SCK31 input  (CSI31/P2 muxed)
        self.p20_si31_in = None    # P2.0/SI31 input   (CSI31/P2 muxed)

        # Multiplexed pins: UART0 muxed with GPIO
        self.p25_txd0_out = None   # P2.5/TxD0 output (UART0/P2 muxed)
        self.p24_rxd0_in = None    # P2.4/RxD0 input  (UART0/P2 muxed)

    def _init_memories(self):
        bus = self.proc.bus

        rom = MemoryDevice("rom", size=0xF000, fill=0xFF, writable=False)
        bus.add_device(rom, (0x0000, 0xEFFF))

        expansion_ram = MemoryDevice("expansion_ram", size=0x0800)
        bus.add_device(expansion_ram, (0xF000, 0xF7FF))

        reserved = MemoryDevice("reserved", size=0x0300, fill=0x08, writable=False)
        bus.add_device(reserved, (0xF800, 0xFAFF))

        high_speed_ram = MemoryDevice("high_speed_ram", size=0x03E0, high_speed=True)
        bus.add_device(high_speed_ram, (0xFB00, 0xFEDF))

        register_file = RegisterFileDevice("register_file", high_speed=True)
        bus.add_device(register_file, (0xFEE0, 0xFEFF))

        processor_status = ProcessorStatusDevice("processor_status")
        bus.add_device(processor_status, (0xFF1C, 0xFF1E))

    def _init_ports(self):
        bus = self.proc.bus

        self.p0 = Port0Device()
        bus.add_device(self.p0, (0xFF00, 0xFF00), (0xFF20, 0xFF20), (0xFF30, 0xFF30),
                                (0xFF48, 0xFF48), (0xFF49, 0xFF49))

        self.p2 = Port2Device()
        bus.add_device(self.p2, (0xFF02, 0xFF02), (0xFF22, 0xFF22), (0xFF32, 0xFF32))

        self.p3 = Port3Device()
        bus.add_device(self.p3, (0xFF03, 0xFF03), (0xFF23, 0xFF23), (0xFF33, 0xFF33))

        self.p4 = Port4Device()
        bus.add_device(self.p4, (0xFF04, 0xFF04), (0xFF24, 0xFF24), (0xFF34, 0xFF34))

        self.p5 = Port5Device()
        bus.add_device(self.p5, (0xFF05, 0xFF05), (0xFF25, 0xFF25), (0xFF35, 0xFF35))

        self.p6 = Port6Device()
        bus.add_device(self.p6, (0xFF06, 0xFF06), (0xFF26, 0xFF26), (0xFF36, 0xFF36))

        self.p7 = Port7Device()
        bus.add_device(self.p7, (0xFF07, 0xFF07), (0xFF27, 0xFF27), (0xFF37, 0xFF37))

        self.p8 = Port8Device()
        bus.add_device(self.p8, (0xFF08, 0xFF08), (0xFF28, 0xFF28))

        self.p9 = Port9Device()
        bus.add_device(self.p9, (0xFF09, 0xFF09), (0xFF29, 0xFF29))

    def _init_interrupts(self):
        bus = self.proc.bus

        self._intc = InterruptControllerDevice("intc")
        bus.add_device(self._intc, (0xFFE0, 0xFFEB))
        bus.set_interrupt_controller(self._intc)

        for bit in range(8):
            self._intc.connect(self.p0, bit, getattr(self._intc, 'INTP%d' % bit))

    def _init_csi30(self):
        bus = self.proc.bus

        self._csi30 = SPIControllerDevice("csi30")
        bus.add_device(self._csi30, (0xFF1A, 0xFF1A), (0xFFB0, 0xFFB0))
        self._intc.connect(self._csi30, self._csi30.INT_TRANSFER, self._intc.INTCSI30)

        # P3.1/SO30: mux between GPIO and SPI data out
        self._so30_mux = Mux()
        self.p3.pins[1].output.drives(self._so30_mux.input_a)
        self._csi30.dat_out.drives(self._so30_mux.input_b)
        self._csi30.enabled_out.drives(self._so30_mux.select_in)

        # P3.2/SCK30: mux between GPIO and SPI clock out
        self._sck30_mux = Mux()
        self.p3.pins[2].output.drives(self._sck30_mux.input_a)
        self._csi30.clk_out.drives(self._sck30_mux.input_b)
        self._csi30.enabled_out.drives(self._sck30_mux.select_in)

        # Package pins
        self.p31_so30_out = self._so30_mux.output
        self.p32_sck30_out = self._sck30_mux.output

        # P3.0/SI30: feeds both GPIO and SPI
        self.p30_si30_in = LogicInput()
        self.p30_si30_in.monitor().drives(self.p3.pins[0].input, 
                                          self._csi30.dat_in)

    def _init_csi31(self):
        bus = self.proc.bus

        self._csi31 = SPIControllerDevice("csi31")
        bus.add_device(self._csi31, (0xFF1B, 0xFF1B), (0xFFB8, 0xFFB8))
        self._intc.connect(self._csi31, self._csi31.INT_TRANSFER, self._intc.INTCSI31)

        # P2.2/SCK31: external clock input from CDC (active-low, inverted)
        self.p22_sck31_in = LogicInput()
        self.p22_sck31_in.monitor().drives(self.p2.pins[2].input,
                                           self._csi31.clk_in)

        # P2.0/SI31: data input from CDC (active-low, inverted)
        self.p20_si31_in = LogicInput()
        self.p20_si31_in.monitor().drives(self.p2.pins[0].input, 
                                          self._csi31.dat_in)

    def _init_uart0(self):
        bus = self.proc.bus

        self._uart0 = UARTDevice("uart0")
        bus.add_device(self._uart0,
                       (0xFF18, 0xFF18),    # TXS0/RXB0
                       (0xFFA0, 0xFFA1),    # ASIM0, ASIS0
                       (0xFFA2, 0xFFA2))    # BRGC0

        self._intc.connect(self._uart0, self._uart0.INT_TX, self._intc.INTST0)
        self._intc.connect(self._uart0, self._uart0.INT_RX, self._intc.INTSR0)
        self._intc.connect(self._uart0, self._uart0.INT_ERR, self._intc.INTSER0)

        # P2.5/TxD0: mux between GPIO and UART data out
        self._txd0_mux = Mux()
        self.p2.pins[5].output.drives(self._txd0_mux.input_a)
        self._uart0.txd_out.drives(self._txd0_mux.input_b)
        self._uart0.tx_enabled_out.drives(self._txd0_mux.select_in)
        self.p25_txd0_out = self._txd0_mux.output

        # P2.4/RxD0: feeds both GPIO and UART
        self.p24_rxd0_in = LogicInput()
        self.p24_rxd0_in.monitor().drives(self.p2.pins[4].input,
                                          self._uart0.rxd_in)

    def _init_i2c(self):
        bus = self.proc.bus

        i2c = I2CControllerDevice("iic0")
        bus.add_device(i2c, (0xFF1F, 0xFF1F), (0xFFA8, 0xFFAA))
        self._intc.connect(i2c, i2c.INT_TRANSFER, self._intc.INTIIC0)

    def _init_timers(self):
        bus = self.proc.bus

        tm01_cr011 = CompareMatchTimerDevice("tm01_cr011")
        bus.add_device(tm01_cr011, (0xFF12, 0xFF13), (0xFF14, 0xFF15))
        self._intc.connect(tm01_cr011, tm01_cr011.INT_COMPARE, self._intc.INTTM011)

        adc = ADCDevice("adc", result=0x8C)  # 14.0V typical car battery
        bus.add_device(adc, (0xFF17, 0xFF17), (0xFF80, 0xFF81))
        self._intc.connect(adc, adc.INT_COMPLETE, self._intc.INTAD00)

        watch_timer = WatchTimerDevice("watch_timer")
        bus.add_device(watch_timer, (0xFF41, 0xFF41))
        self._intc.connect(watch_timer, watch_timer.INT_PRESCALER, self._intc.INTWTNI0)
        self._intc.connect(watch_timer, watch_timer.INT_WATCH, self._intc.INTWTN0)

        watchdog = WatchdogDevice("watchdog")
        bus.add_device(watchdog, (0xFF42, 0xFF42), (0xFFF9, 0xFFF9))
        self._intc.connect(watchdog, watchdog.INT_OVERFLOW, self._intc.INTWDT)
