# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
"""Zelftest voor de MS/TP-laag, zonder hardware.

    python3 tests/mstp_selftest.py

Wat het bewijst:
  * de CRCs tegen de check-waarden van de standaard
  * het frame-formaat tegen de voorbeeldframes uit de specificatie
  * een volledige token-cyclus tussen twee masters (wij + een gesimuleerde peer)
  * Who-Is → I-Am, object-list lezen en Present_Value lezen over MS/TP

Wat het NIET bewijst: dat een echt toestel met onze timing en frames overweg
kan. Dat kan alleen op een fysieke lijn met een echt toestel.
"""

from __future__ import annotations

import os
import pty
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mstp                                                  # noqa: E402
from mstp_peer import MstpPeer                               # noqa: E402


def test_crc_and_frames() -> None:
    assert mstp.crc8_header(b"123456789") == 0x89, "CRC-8/BAC check-waarde"
    assert mstp.crc16_data(b"123456789") == 0x906E, "CRC-16/X.25 check-waarde"
    assert mstp.encode_frame(mstp.TOKEN, 0x72, 0x0A).hex() == "55ff00720a0000a9", "token-frame"
    assert mstp.encode_frame(mstp.POLL_FOR_MASTER, 0x07, 0x03).hex() == "55ff01070300006d", "pfm-frame"
    # Ronde-trip en een bewust kapotte CRC.
    blob = mstp.encode_frame(mstp.DATA_EXPECTING_REPLY, 5, 0, b"\x01\x04\x10\x08")
    frames, rest = mstp.decode_frames(blob)
    assert len(frames) == 1 and frames[0].data == b"\x01\x04\x10\x08" and not rest
    broken = bytearray(blob)
    broken[-1] ^= 0xFF
    frames, _ = mstp.decode_frames(bytes(broken))
    assert frames == [], "kapotte data-CRC moet het frame verwerpen"
    print("  CRCs en frames: ok")


def test_live_cycle() -> None:
    master_fd, slave_fd = pty.openpty()
    slave_name = os.ttyname(slave_fd)
    peer = MstpPeer(master_fd)
    thread = threading.Thread(target=peer.run, kwargs={"seconds": 25.0}, daemon=True)
    thread.start()

    line = mstp.MstpMaster(slave_name, mac=0, baud=19200, master_timeout=1.5)
    line.open()
    try:
        devices = line.whois(timeout=4.0)
        assert devices, "geen I-Am ontvangen"
        assert devices[0]["device"] == 1234, f"verkeerde device: {devices}"
        print(f"  Who-Is: device {devices[0]['device']} op MAC {devices[0]['mac']}: ok")

        objects = line.objects(5, 1234)
        assert len(objects) == 2, f"object-list: {objects}"
        print(f"  object-list: {len(objects)} objecten: ok")

        value = line.read_property(5, 0, 0, 85)
        assert abs(float(value) - 21.5) < 0.01, f"present-value: {value}"
        print(f"  Present_Value AI-0: {value}: ok")
        print(f"  frames: tx={line.stats['tx']} rx={line.stats['rx']} tokens={line.stats['token']}")
    finally:
        line.close()
        peer.running = False
        os.close(slave_fd)
        try:
            os.close(master_fd)
        except OSError:
            pass


if __name__ == "__main__":
    started = time.time()
    print("MS/TP zelftest")
    test_crc_and_frames()
    test_live_cycle()
    print(f"geslaagd in {time.time() - started:.1f}s")
