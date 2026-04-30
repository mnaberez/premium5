from k0emu.devices import BasePortDevice, PortWithPullupsDevice, PortWithEdgeDetectionDevice


class Port0Device(PortWithEdgeDetectionDevice):
    """Port 0: 8-bit I/O port with external interrupt edge detection.
    P00/INTP0: input  MFSW (inverted; from HEF40106BT)
    P01/INTP1: input  Unknown
    P02/INTP2: input  Unknown (must be low or firmware stays in halt/sleep loop)
    P03/INTP3: input  Unknown (not used as INTP3)
    P04/INTP4: input  POWER key (0=pressed)
    P05/INTP5: input  uPD16432B KEYREQ (not used in firmware)
    P06/INTP6: input  STOP/EJECT key (0=pressed)
    P07/INTP7: input  Unknown
    Pull-up resistors on all pins."""
    def __init__(self):
        super().__init__("p0")


class Port2Device(PortWithPullupsDevice):
    """Port 2: 8-bit I/O port.
    P20/SI31:  input   CDC DI (inverted; from HEF40106BT)
    P21/SO31:  output  Unknown
    P22/SCK31: output  CDC CLK (inverted; from HEF40106BT)
    P23:       input   Tape METAL sense (1=metal)
    P24/RxD0:  input   L9637D RX (K-line)
    P25/TxD0:  output  L9637D TX (K-line)
    P26:       output  K-line resistor (0=disconnected, 1=connected)
    P27:       output  Unknown
    Pull-up resistors on all pins."""
    def __init__(self):
        super().__init__("p2")


class Port3Device(PortWithPullupsDevice):
    """Port 3: 7-bit I/O port (bit 7 fixed at 1).
    P30/SI30:  input   uPD16432B DAT in
    P31/SO30:  output  uPD16432B DAT out
    P32/SCK30: output  uPD16432B CLK
    P33:       output  Alarm LED (0=on, 1=off), N-ch open-drain
    P34/TO00:  output  Unknown
    P35/TI000: input   Unknown
    P36/TI010: unknown Unknown
    Pull-up resistors on P30-P32, P34-P36 (not P33)."""
    def __init__(self):
        super().__init__("p3")


class Port4Device(PortWithPullupsDevice):
    """Port 4: 8-bit I/O port.
    P40: input   Unknown
    P41: input   Unknown
    P42: input   Unknown
    P43: output  3LB bus isolation gate (0=isolated, 1=connected)
    P44: output  FIS ENA (3LB enable, active high)
    P45: input   FIS ENA readback (3LB enable from cluster)
    P46: output  uPD16432B /LCDOFF
    P47: output  uPD16432B STB
    Pull-up resistors on all pins."""
    def __init__(self):
        super().__init__("p4")


class Port5Device(PortWithPullupsDevice):
    """Port 5: 8-bit I/O port, TTL level input.
    P50: output  Unknown
    P51: output  Unknown
    P52: output  Unknown
    P53: output  Unknown
    P54: output  Unknown
    P55: output  Unknown
    P56: unknown Unknown
    P57: output  CDC DO (inverted; to HEF40106BT)
    Pull-up resistors on all pins."""
    def __init__(self):
        super().__init__("p5")


class Port6Device(PortWithPullupsDevice):
    """Port 6: 4-bit I/O port (P64-P67 only, lower 4 bits read as 1).
    P64: unknown Unknown
    P65: unknown Unknown
    P66: unknown Unknown
    P67: unknown Unknown
    Pull-up resistors on P64-P67."""
    def __init__(self):
        super().__init__("p6")


class Port7Device(PortWithPullupsDevice):
    """Port 7: 6-bit I/O port (bits 6-7 read as 1).
    P70/PCL:   unknown Unknown
    P71/SDA0:  output  I2C SDA, N-ch open-drain
    P72/SCL0:  output  I2C SCL, N-ch open-drain
    P73/TO01:  output  Bit-banged I2C SCL to TEA6840H NICE only
    P74/TI001: input   Bit-banged I2C SDA to TEA6840H NICE only
    P75/TI011: input   Unknown
    Pull-up resistors on P70, P73-P75 (not P71, P72)."""
    def __init__(self):
        super().__init__("p7")


class Port8Device(BasePortDevice):
    """Port 8: 8-bit I/O port.  No pull-up resistors.
    P80/ANI01: output  Switched 5V supply control (0=off, 1=on)
    P81/ANI11: output  Antenna phantom power out (0=off, 1=on)
    P82/ANI21: output  Monsoon amplifier power 12V out (0=off, 1=on)
    P83/ANI31: input   Unknown
    P84/ANI41: input   Unknown
    P85/ANI51: input   Unknown
    P86/ANI61: input   Unknown
    P87/ANI71: unknown Unknown"""
    def __init__(self):
        super().__init__("p8")


class Port9Device(BasePortDevice):
    """Port 9: 8-bit I/O port.  No pull-up resistors.
    P90/ANI00: input   S-Contact (0=off, 1=on)
    P91/ANI10: input   Terminal 30 Constant B+ analog input
    P92/ANI20: input   Terminal 58b Illumination analog input
    P93/ANI30: input   Unknown
    P94/ANI40: output  Unknown
    P95/ANI50: input   Unknown analog input
    P96/ANI60: input   Unknown
    P97/ANI70: output  Unknown"""
    def __init__(self):
        super().__init__("p9")
        self.external_inputs = 0xFE  # P9.0=0: S-Contact off (ignition off)
    def reset(self):
        super().reset()
        self.external_inputs = 0xFE  # P9.0=0: S-Contact off (ignition off)
