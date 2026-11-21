# thermocouple.py -- tiny drivers for MAX6675 and MAX31855 K-type thermocouple boards.
#
# read_c() returns degrees C, or None if the board reports a fault
# (probe unplugged, shorted, or the board isn't answering).


def decode_max6675(raw):
    """Decode the 16-bit word a MAX6675 sends."""
    # 0 = board missing / not answering; bit 15 is always 0 on a real reading;
    # bit 2 = thermocouple open (unplugged or broken probe).
    if raw == 0 or raw & 0x8000 or raw & 0x0004:
        return None
    return (raw >> 3) * 0.25


def decode_max31855(raw):
    """Decode the 32-bit word a MAX31855 sends."""
    # 0 = board missing / not answering; bit 16 = any fault;
    # bits 0-2 = open circuit / shorted to GND / shorted to VCC.
    if raw == 0 or raw & 0x00010007:
        return None
    t = raw >> 18               # 14-bit signed, 0.25 C per count
    if t & 0x2000:
        t -= 0x4000
    return t * 0.25


class _Board:
    nbytes = 2

    def __init__(self, spi, cs):
        self.spi = spi
        self.cs = cs
        self.buf = bytearray(self.nbytes)
        self.cs.value(1)

    def _read_raw(self):
        self.cs.value(0)
        try:
            self.spi.readinto(self.buf)
        finally:
            self.cs.value(1)
        return int.from_bytes(self.buf, "big")


class MAX6675(_Board):
    nbytes = 2

    def read_c(self):
        return decode_max6675(self._read_raw())


class MAX31855(_Board):
    nbytes = 4

    def read_c(self):
        return decode_max31855(self._read_raw())
