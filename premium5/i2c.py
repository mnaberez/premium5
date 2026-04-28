from k0emu.i2c import BaseI2CTarget


class M24C04(BaseI2CTarget):
    """M24C04 I2C EEPROM (512 bytes).

    This is an I2C target, not a bus device.  It is registered on the
    I2CControllerDevice via add_target() at two I2C addresses: 0x50 for the lower
    256 bytes and 0x51 for the upper 256 bytes.

    Both addresses share the same backing store.  The page_offset
    parameter to the constructor selects which half (0 or 256).

    Page write: writes wrap within 16-byte page boundaries.
    After a write transaction, the address counter points to
    the start of the page that was written.
    """

    PAGE_SIZE = 16

    def __init__(self, data, page_offset):
        self._data = data
        self._page_offset = page_offset
        self._address = 0
        self._address_set = False

    def i2c_start(self, is_read):
        if not is_read:
            self._address_set = False

    def i2c_stop(self):
        pass

    def i2c_read(self):
        addr = self._page_offset + self._address
        value = self._data[addr]
        self._address = (self._address + 1) % 256
        return value

    def i2c_write(self, data):
        if not self._address_set:
            self._address = data
            self._address_set = True
        else:
            addr = self._page_offset + self._address
            self._data[addr] = data
            page_base = self._address & ~(self.PAGE_SIZE - 1)
            self._address = page_base | ((self._address + 1) & (self.PAGE_SIZE - 1))
        return self.ACK
