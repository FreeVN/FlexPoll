# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
"""Echt, onafhankelijk BACnet-toestel (bacpypes3) voor de BBMD-labtest.

Draait in netb (172.28.20.0/24) achter de Docker-router. Publiceert AI/AV/BV
zodat FlexPoll kan bewijzen dat lezen over de router werkt en dat een
Who-Is via de BBMD bij dit toestel uitkomt.
"""

import asyncio

from bacpypes3.app import Application
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.local.analog import AnalogInputObject, AnalogValueObject
from bacpypes3.local.binary import BinaryValueObject


async def main() -> None:
    args = SimpleArgumentParser().parse_args([
        "--address", "172.28.20.10/24",
        "--name", "BBMD-Test-Device",
        "--instance", "2001",
        "--vendoridentifier", "999",
    ])
    app = Application.from_args(args)
    app.add_object(AnalogInputObject(
        objectIdentifier=("analogInput", 1), objectName="Ruimtetemperatuur",
        presentValue=21.5, units="degreesCelsius"))
    app.add_object(AnalogValueObject(
        objectIdentifier=("analogValue", 1), objectName="Setpunt",
        presentValue=22.0, units="degreesCelsius"))
    app.add_object(BinaryValueObject(
        objectIdentifier=("binaryValue", 1), objectName="Pomp",
        presentValue="active"))
    print("device 2001 up op 172.28.20.10", flush=True)
    await asyncio.Event().wait()


asyncio.run(main())
