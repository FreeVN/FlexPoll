# Als het niet werkt

Werk van boven naar onder: de meeste problemen zitten in de eerste twee blokken.

## De adapter staat niet in de lijst

**Windows**

- Ontbreekt de COM-poort ook in Apparaatbeheer? Dan is het een **driver**probleem.
  FTDI werkt out-of-the-box; **CH340** en **CP210x** hebben een driver van de
  fabrikant nodig (WCH of Silicon Labs).
- Namaak-FTDI-chips kunnen door een Windows-update geblokkeerd worden (Code 10).
  Gebruik dan een echte FTDI of een geïsoleerde stick van een bekend merk.
- Pas aangesloten? Even de pagina verversen — de poortlijst wordt bij het laden
  opgehaald.

**Linux**

- `ls: cannot access '/dev/ttyUSB0'` → de stick is niet ingeplugd of de kernel
  module ontbreekt. `dmesg | tail` zegt het meteen.
- De poort bestaat maar de app krijgt hem niet open → **rechten**:

  ```bash
  sudo usermod -aG dialout "$USER"      # daarna opnieuw inloggen
  ```

- In Docker: de container moet het device én de groep krijgen:

  ```bash
  --device /dev/serial/by-id/usb-…:/dev/ttyUSB0 --group-add dialout
  ```

## "Bus offline" of de poort gaat niet open

- Een ander programma houdt de poort bezet (Modbus Poll, een SCADA, een vorige
  instantie van FlexPoll). Sluit dat eerst; op Windows zegt Apparaatbeheer het
  soms niet, maar `handle.exe` of gewoon herstarten helpt.
- Verkeerde adapter gekozen (bv. een Bluetooth-COM-poort).
- De service draait als een gebruiker zonder `dialout`.

## Timeouts of rommel op de lijn

Dit is bijna altijd **hardware of framing**, niet de software:

1. **A en B omgewisseld.** De klassieker. Sommige sticks labellen anders dan je
   verwacht; omwisselen kost tien seconden.
2. **Baudrate/pariteit verkeerd.** Gebruik **Framing** om te zoeken in plaats van
   te gokken.
3. **Geen of dubbele terminating.** 120 Ω aan beide uiteinden van een lange lijn,
   niet in het midden.
4. **Adapter zonder auto-direction.** Een CH340 die RTS nodig heeft, werkt niet:
   FlexPoll toggelt geen RTS. Gebruik een FTDI of een geïsoleerde stick.
5. **USB selective suspend / slaapstand.** Windows zet de poort in slaap na
   inactiviteit → eerste frame na een pauze is altijd een timeout. Zet
   *USB-instellingen → selectief opschorten* uit.
6. **Slechte voeding of geen aarding.** Lange lijnen naast een frequentieregelaar
   geven precies dit beeld: af en toe een timeout, verder niets.

## De scan vindt niets, maar het toestel werkt

- **Scanbereik te klein**: staat het toestel op adres 40 en scan je 1–32, dan
  vind je niets.
- **Framing klopt niet** voor dat ene toestel (afwijkende instelling op een
  gedeelde lijn).
- Het toestel antwoordt alleen op **functiecode 4** terwijl de tool eerst 3
  probeert: de scan probeert beide, maar een streng beveiligde gateway kan
  weigeren. Lees het dan handmatig met de juiste functiecode.

## Waarden kloppen niet

| Symptoom | Oorzaak |
|---|---|
| Precies 10× of 100× te groot | De documentatie rekent in tienden/honderdsten. Dat is een schaalfactor, geen fout. |
| Absurd grote getallen bij 32-bit | **Woordvolgorde**: zet `AB` op `BA` of omgekeerd. |
| Waarde verspringt tussen twee waarden | Twee registers die je als één 32-bit leest, maar het zijn er twee losse 16-bit. |
| Altijd 0 | Verkeerd registeradres (0-based vs 40001-notatie) of verkeerde functiecode. |

## BACnet/IP vindt geen toestellen

Zie de checklist in [BACnet/IP](bacnet.md#waarom-zie-ik-geen-toestellen):
VLAN, UDP 47808, client isolation, BBMD.

## De web-UI is niet bereikbaar

- Poort 8099 bezet? Start met een andere poort: `--port 8098`.
- De service luistert standaard op `0.0.0.0`; vanaf een andere pc gebruik je dus
  het IP van de doos, niet `127.0.0.1`.
- Firewall op de doos: poort 8099/TCP openzetten.

## Ik wil weten wat er precies misgaat

De console (of `journalctl -u flexpoll -f`) toont elke poortactie en fout. In de
UI geeft **Buslog → verkeer** de frames. Bij een bugrapport helpt:

- merk, type en firmwareversie van het toestel
- de framing (baudrate/pariteit/stopbits)
- wat de buslog zegt op het moment van de fout
- de FlexPoll-versie (rechts in de titelbalk)

## Een probleem melden

[Open een issue](https://github.com/FreeVN/FlexPoll/issues) met het bovenstaande.
Het is een bèta: een melding met merk/type/firmware is de snelste weg naar een fix.
