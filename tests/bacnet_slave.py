"""Minimal BACnet/IP test slave (stdlib) — om de client end-to-end te testen.

Serveert één device 1234 met een handvol objecten, incluised de object-list array,
zodat EDE, lezen en schrijven herhaalbaar getest kunnen worden.
"""
import socket
import struct
import sys

from bacnet import (_app_bool, _app_enum, _app_real, _app_str, _app_uint,
                    _ctx, _read_tag, parse_value)

PORT = 47808
BIND = "0.0.0.0"
DEVICE = 1234
VENDOR = 999

# (type, instance) -> properties
DEVS = {
    (8, DEVICE): {77: "Gezel-Test-Device", 70: "Testbank", 120: 999, 121: 8, 44: 2},
    (0, 1): {77: "Buiten temperatuur", 28: "Test AI", 85: 12.5, 117: 62},
    (1, 1): {77: "Kleppositie", 28: "Test AO", 85: 45.0, 117: 98},
    (2, 1): {77: "Setpunt", 28: "Test AV", 85: 21.0, 117: 62, 17: 1},
    (3, 1): {77: "Vrijgave", 28: "Test BI", 85: 1, 111: ["Uit", "Aan"]},
    (13, 1): {77: "Stand", 28: "Test MSI", 85: 2},
    (19, 1): {77: "Bedrijfsmodus", 28: "Test MSV", 85: 2, 74: 3,
              111: ["Koelen", "Verwarmen", "Auto"]},
}
ORDER = [(8, DEVICE), (0, 1), (1, 1), (2, 1), (3, 1), (13, 1), (19, 1)]

REAL_TYPES = (0, 1, 2)
BOOL_TYPES = (3, 4, 8)
ENUM_TYPES = (5, 13, 14, 19)


def enc_value(obj, prop, value):
    t, _ = obj
    if prop in (77, 28, 70):
        return _app_str(value)
    if prop == 85 and t in BOOL_TYPES:
        return _app_bool(bool(value))
    if prop in (85, 117) and t in REAL_TYPES:
        return _app_real(float(value))
    if (prop == 85 and t in ENUM_TYPES) or prop in (120, 121):
        return _app_enum(int(value)) if prop == 85 else _app_uint(int(value))
    if prop == 44:                      # segmentation-supported (bitstring-ish) -> enum
        return _app_enum(int(value))
    return _app_uint(int(value))


def handle_apdu(apdu, src, sock):
    kind = apdu[0] & 0xF0
    service = apdu[1] if apdu[0] == 0x10 else (apdu[3] if len(apdu) > 3 else None)
    inv = apdu[1]

    if apdu[0] == 0x10 and service == 0x08:           # Who-Is (unconfirmed, geen len-check)
        iam = bytes([0x10, 0x00]) + bytes([0xC4]) + struct.pack(">I", (8 << 22) | DEVICE)
        iam += _app_uint(480) + _app_enum(0) + _app_uint(VENDOR)
        sock.sendto(bytes([0x81, 0x0A]) + struct.pack(">H", len(iam) + 6) + b"\x01\x00" + iam, src)
        return

    if kind != 0x00 or len(apdu) < 8:
        return

    i = 4
    tag, cls, ln, j = _read_tag(apdu, i)
    if cls != 1 or ln != 4:                            # object-id: context tag 0
        return
    oid = int.from_bytes(apdu[j:j + 4], "big")
    obj = (oid >> 22, oid & 0x3FFFFF)
    i = j + 4
    tag, cls, ln, j = _read_tag(apdu, i)
    prop = int.from_bytes(apdu[j:j + ln], "big")
    i = j + ln
    index = None
    if i < len(apdu):
        tag, cls, ln, j = _read_tag(apdu, i)
        index = int.from_bytes(apdu[j:j + ln], "big")

    props = DEVS.get(obj)

    if service == 0x0C:                                # ReadProperty
        if props is None or (prop not in props and prop != 76):
            err = bytes([0x50, inv, 0x0C]) + _ctx(2, _app_enum(0)) + _ctx(3, _app_enum(32))
            sock.sendto(bytes([0x81, 0x0A]) + struct.pack(">H", len(err) + 6) + b"\x01\x00" + err, src)
            return
        head = bytes([0x30, inv, 0x0C]) + _ctx(0, struct.pack(">I", (obj[0] << 22) | obj[1])) + _ctx(1, bytes([prop]))
        if prop == 111 and isinstance(props.get(111), list):     # state-text (array)
            texts = props[111]
            if index is None or index == 0:
                body = _app_uint(len(texts))
            elif 1 <= index <= len(texts):
                body = _app_str(texts[index - 1])
            else:
                return
            if index is not None:
                head += _ctx(2, bytes([index]))
            ack = head + b"\x3e" + body + b"\x3f"
            sock.sendto(bytes([0x81, 0x0A]) + struct.pack(">H", len(ack) + 6) + b"\x01\x00" + ack, src)
            return
        if prop == 76:                                  # object-list (array)
            if index == 0:
                body = _app_uint(len(ORDER))
            else:
                t, inst = ORDER[index - 1]
                body = bytes([0xC4]) + struct.pack(">I", (t << 22) | inst)
            if index is not None:
                head += _ctx(2, bytes([index]))
        else:
            body = enc_value(obj, prop, props[prop])
            if index is not None:
                head += _ctx(2, bytes([index]))
        ack = head + b"\x3e" + body + b"\x3f"
        sock.sendto(bytes([0x81, 0x0A]) + struct.pack(">H", len(ack) + 6) + b"\x01\x00" + ack, src)
        return

    if service == 0x0F:                                # WriteProperty
        k = i
        if k < len(apdu) and apdu[k] == 0x3E:
            k += 1
        value, _ = parse_value(apdu, k)
        if props is not None and prop in props and obj[0] in (1, 2):    # AO / AV schrijfbaar
            props[prop] = value
            print("write", obj, prop, "=", value, flush=True)
            ack = bytes([0x20, inv])
        else:
            ack = bytes([0x50, inv, 0x0F]) + _ctx(2, _app_enum(2)) + _ctx(3, _app_enum(40))
        sock.sendto(bytes([0x81, 0x0A]) + struct.pack(">H", len(ack) + 6) + b"\x01\x00" + ack, src)
        return


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind((BIND, PORT))
    print("BACnet testslave op %d, device %d" % (PORT, DEVICE), flush=True)
    while True:
        data, src = sock.recvfrom(4096)
        print("rx", src, data.hex(" "), flush=True)
        if len(data) < 8 or data[0] != 0x81:
            continue
        npdu = data[4:]
        if len(npdu) < 2 or npdu[0] != 0x01:
            continue
        body = npdu[2:]
        if npdu[1] & 0x20 and len(npdu) >= 6:      # global broadcast (Who-Is)
            body = npdu[6:]
        try:
            handle_apdu(body, src, sock)
        except Exception as exc:                       # noqa: BLE001
            print("fout:", exc, file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
