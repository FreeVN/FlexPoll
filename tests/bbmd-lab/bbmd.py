# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
"""Echte BBMD (bacpypes3 BIPBBMD) — onafhankelijke implementatie naast FlexPoll.

Belangrijk: een BBMD moet zichzelf in zijn BDT hebben staan. Zonder die entry
zendt bacpypes3 een binnengekomen Forwarded-NPDU niet lokaal uit, en dan vindt
een foreign device wel de BBMD maar geen enkel toestel op dat subnet.
"""

import asyncio

from bacpypes3.ipv4 import IPv4Address
from bacpypes3.ipv4.app import BBMDApplication
from bacpypes3.local.device import DeviceObject


async def main() -> None:
    dev = DeviceObject(
        objectIdentifier=("device", 3001),
        objectName="Test-BBMD",
        vendorIdentifier=999,
        vendorName="Testbank",
        modelName="bbmd",
        firmwareRevision="1.0",
        applicationSoftwareVersion="1.0",
        protocolVersion=1,
        protocolRevision=22,
    )
    app = BBMDApplication(dev, IPv4Address("172.28.20.11/24"))
    app.bbmd.bbmdBDT.append(IPv4Address("172.28.20.11"))
    print("BBMD up op 172.28.20.11:47808", flush=True)
    await asyncio.Event().wait()


asyncio.run(main())
