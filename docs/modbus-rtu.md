# Modbus RTU (RS-485)

Modbus RTU is één tweedraads lijn waar alle toestellen aan hangen, elk met een
eigen adres (1–247). Eén framing geldt voor de hele lijn: dezelfde baudrate,
pariteit en stopbits.

## De bus instellen

| Veld | Wat het betekent |
|---|---|
| **Adapter** | De USB-RS485-stick. Gebruik het by-id-pad (`/dev/serial/by-id/usb-…`) in plaats van `/dev/ttyUSB0`: dat nummer verspringt als je iets anders inplugt. |
| **Baudrate** | 9600 is de norm bij Siemens Desigo Essentials, 19200 bij Belimo VAV, 38400/57600 bij sommige pompen. |
| **Pariteit** | 8N1 (none) of 8E1 (even). 8O1 komt zelden voor. |
| **Stopbits** | Bijna altijd 1. |
| **Verbind** | Opent de poort. De badge rechts boven wordt groen bij **Bus online**. |

!!! note "Eén framing per lijn"
    Staat er een toestel met een afwijkende instelling op dezelfde kabel, dan
    verstoort dat de hele lijn. Zo'n toestel hoort op een aparte poort of moet
    omgezet worden.

## Framing zoeken

Klik **Framing**. De tool probeert de combinaties van baudrate/pariteit/stopbits
op het **eerste adres van je scanbereik** en meldt welke werkt. Krijg je niets,
controleer dan eerst de bedrading (A/B omgewisseld is de klassieker) en de
terminator (120 Ω aan beide uiteinden van een lange lijn).

## Adressen scannen

**Scan adressen** loopt je bereik af en toont per adres een type en een
zekerheidsscore. Klik **+ toevoegen** om het als module op de lijn te zetten, of
sleep het juiste tegeltje uit de linkerkolom.

De score is geen mysterie: de tool kijkt welke registers antwoorden en of de
waarden plausibel zijn. 90 % of meer = gerust toevoegen; 60 % = het toestel
antwoordt, maar het type is een gok — controleer het adres in de documentatie van
het toestel.

## Een module lezen

Elke modulekaart toont:

- **adres** en een groene stip (antwoordt) of rode (antwoordt niet)
- het **serienummer** als het toestel dat levert
- per kanaal de **waarde**, de **eenheid** en de gekozen mode/sensor
- **framing onbekend** of de gemeten **responstijd** in milliseconden

Onderaan de kaart staat **Baud → auto**: laat de tool de framing per module
opnieuw bepalen. **Reset** wist de telling.

## Punten toevoegen

Klik op **+** bij een module (of gebruik **Punt toevoegen** in het menu) en vul in:

| Veld | Toelichting |
|---|---|
| **Naam** | Wat je op het scherm wil zien, bv. "Buitenvoeler". |
| **Eenheid** | `°C`, `V`, `m³/h`, `%`, … |
| **Functiecode** | 3 = holding register (lezen/schrijven), 4 = input register (lezen), 1 = coil, 2 = discrete input. |
| **Adres** | **0-based**, zoals in de meeste documentatie. Staat er in de handleiding "40001", dan is dat functiecode 3, adres 0. |
| **Datatype** | uint16/int16 voor één register; uint32/int32/float32 voor twee registers. |
| **Woordvolgorde** | `AB` = hoog woord eerst (Meestal), `BA` = laag woord eerst. Verkeerd gekozen geeft absurde waarden bij 32-bit. |

## Schrijven

Waarden met een invoerveld en een **Zet**-knop kan je wegschrijven (functiecode 6
of 5, afhankelijk van het type). Voorbeelden die in de praktijk gebruikt worden:
setpunt van een VAV, override van een regelaar, relaisspoel testen.

!!! warning "Schrijven op een live installatie"
    Een enkele schrijfactie kan een regelaar in override zetten of een klep
    sturen. Doe dit alleen op een testbank of met toestemming van de beheerder —
    en noteer de oude waarde voor je iets verandert.

## Buslog

Vink **verkeer** aan voor elk frame. De log toont tijdstip, adres, functiecode en
bij een fout de exception-code. Handig bij het zoeken naar een toestel dat af en
toe wegvalt: je ziet het patroon (elke 10 s een timeout op adres 7) in plaats van
een algemene foutmelding.

## Grenzen van de tool

- **Geen RTS-toggle.** Alleen adapters met automatische richtingsomschakeling
  (FTDI, de meeste geïsoleerde sticks) werken. Een CH340 die RTS nodig heeft,
  geeft timeouts.
- **Eén lijn per keer.** FlexPoll opent één seriële poort; meerdere RS-485-lijnen
  tegelijk vraagt meerdere instanties (of containers) met elk hun eigen poort.
- **Niet tegelijk met BACnet MS/TP op dezelfde poort.** Ander protocol, andere
  framing, en beide willen master zijn. Zie [BACnet MS/TP](mstp.md).
- **247 adressen is de bovengrens**, en een scan over alles duurt bij 9600 baud
  meerdere minuten. Beperk je bereik.
