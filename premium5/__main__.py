"""
Premium 5 emulator.

Runs the 78K/0 emulator with VW Premium 5 radio configuration
and serves a web UI over HTTP.

Usage: pypy3 premium5.py <rom.bin> [listing.lst]
"""

import sys

from premium5.emulator import Emulator, Listing
from premium5.webserver import serve


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        sys.exit(1)
    rom_path = sys.argv[1]
    listing_path = sys.argv[2] if len(sys.argv) > 2 else None
    listing = Listing(listing_path) if listing_path else None
    emulator = Emulator(rom_path, listing)
    serve(emulator)


if __name__ == "__main__":
    main()
