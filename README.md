# premium5

[![Photo](./premium5/web/images/emulator.png)](https://mikenaberezny.com/videos/premium5)
                       
This project emulates the Volkswagen [Premium 5](https://github.com/mnaberez/vwradio/tree/main/reverse_engineering/delco/vw_premium_5) car radio made by Delco.  Built on [k0emu](https://github.com/mnaberez/k0emu) and [k0dasm](https://github.com/mnaberez/k0dasm), it runs all known versions of the radio's original firmware without patches.  Its purpose is to aid in continued reverse engineering of the radio and to help test firmware mods.  

Emulated components include the undocumented Renesas (NEC) µPD78F0831Y microcontroller (which turned out to be a subset of the [µPD78F0833Y](https://web.archive.org/web/20180328161019if_/https://www.renesas.com/en-us/doc/DocumentServer/021/U13892EJ2V0UM00.pdf)), the [µPD16432B](https://web.archive.org/web/20160611101704if_/http://archive.6502.org/datasheets/nec_upd16432b_2000_dec.pdf) LCD controller (SPI), and the STMicroelectronics M24C04 EEPROM (I2C).  To test remote control of the radio, there are also high-level emulations of the steering wheel controls (MFSW) and instrument cluster display (FIS).

Watch the emulator run in [this video](https://mikenaberezny.com/videos/premium5): the radio prompts for the SAFE code on power up, and if the correct code is toggled in, unlocks and responds to all buttons.  For example, FM mode can be selected and the frequency changed.  The emulator does not produce audio, nor does it emulate the tape deck or CD changer.

## Features                                                     

- Boots and runs the original firmware without patches
- Web UI with interactive faceplate: button input and pixel-perfect LCD
- Disassembly and listing views for debugging
- Register, memory, and EEPROM inspection
- Single step, slow run, or real-time emulation

## Installation

The emulator consists of two parts: the emulation backend written in Python and a web-based frontend. To emulate the radio at its original 4.19 MHz speed, [PyPy](https://pypy.org) and a modern CPU with strong single-threaded performance are required. Install `premium5` under PyPy with:

    pypy3 -m pip install git+https://github.com/mnaberez/premium5.git
                                                                                                                        
## Usage

Run the `premium5` executable and open the indicated URL in a browser:

    $ premium5 <firmware.bin>
    Premium 5 emulator
    http://localhost:8080

A firmware binary is required.  One can be built, byte-identical to the original, from [this disassembly](https://github.com/mnaberez/vwradio/tree/main/reverse_engineering/delco/vw_premium_5/disasm).

For more options, run `premium5` with no arguments.

## Author                                                                                          

[Mike Naberezny](https://github.com/mnaberez)
