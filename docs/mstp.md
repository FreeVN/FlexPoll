# BACnet MS/TP

MS/TP is BACnet over RS-485: één tweedraads lijn waarop alle toestellen hangen,
met **token passing** in plaats van vrije toegang. FlexPoll doet mee als
**master**: het vraagt de token, zendt zijn verzoek, en geeft de token door aan
de volgende master.

!!! danger "Ongetest terrein — dit is de eerlijke versie"
    De MS/TP-laag is gebouwd volgens ANSI/ASHRAE 135 en getest tegen een
    **gesimuleerde peer**: CRCs tegen de check-waarden van de standaard, het
    frame-formaat tegen de voorbeeldframes uit de specificatie, en een volledige
    token-cyclus met Who-Is, object-list en Present_Value over een virtuele
    seriële lijn.

    Wat **niet** getest is: een echt MS/TP-toestel. De timing-constanten zijn die
    van de standaard, maar of een Siemens/Belimo-regelaar met onze tokens even
    vlot omgaat, is onbewezen. Gebruik dit om te diagnosticeren, niet om een
    gebouw in dienst te stellen.

## Kan dit op dezelfde adapter als Modbus?

**Nee, niet tegelijk.** Twee redenen:

1. **Andere linklaag.** MS/TP is 8N1 op 9600/19200/38400/57600/76800, met een
   preamble, een token en twee CRCs. Modbus RTU heeft zijn eigen framing en staat
   meestal op een andere baudrate.
2. **Beide willen master zijn.** Modbus zendt wanneer de master beslist; MS/TP
   mag alleen zenden als je de token hebt. Op één draad praten ze door elkaar:
   CRC-fouten, timeouts en een token die zoekraakt.

Daarom doet FlexPoll het volgende bij **Verbinden**:

- de Modbus-polling gaat op **pauze** en de seriële poort wordt **vrijgegeven**;
- de MS/TP-master opent die poort exclusief.

Wil je terug naar Modbus: **Loskoppelen**, en dan in het Modbus-tabblad op ▶.
Met twee USB-RS485-adapters kan je beide tegelijk draaien — maar dan met twee
instanties van FlexPoll (elk met een eigen `--port` voor de web-UI), want één
proces heeft één bus.

## Verbinden

1. Kies de **poort** van de USB-RS485-adapter.
2. **Baudrate** — moet voor de hele lijn gelijk zijn. 19200 is gebruikelijk,
   38400 komt voor bij nieuwere installaties.
3. **Ons MAC-adres** — 0–127. Elke master op de lijn moet een uniek nummer
   hebben. Op een testbank met één master is 0 prima.
4. **Verbinden**.

De statusregel zegt of het gelukt is; bij een fout krijg je de reden van de
seriële poort (poort bezet, rechten, verkeerde naam).

## Toestellen zoeken

**Toestellen zoeken** stuurt een **Who-Is** de lijn op. Elk toestel antwoordt met
een **I-Am**: device-instance, MAC-adres en vendor. Daarna leest FlexPoll de
naam (property 77) — dat duurt even, want elk punt is een eigen verzoek over een
lijn waar ook tokens passeren.

Klik op een toestel om de objecten te lezen. Je krijgt dezelfde tabel als bij
BACnet/IP: type (AI, AV, BI, BV, MSV, …), instance, naam en huidige waarde.

**Schrijven** kan op analoge en binaire uitgangen/waarden en op multi-state.
Andere objecten zijn read-only — dat is BACnet, niet de tool.

## Wat er (nog) niet is

- **Geen EDE-export** over MS/TP. Bij BACnet/IP kan dat wel; hier nog niet.
  Werk je met een gebouwbeheerder die een EDE wil, gebruik dan de IP-route.
- **Geen slave-modus**: FlexPoll is master, punt.
- **Geen routing/BBMD**: alleen het lokale segment.
- **Geen geconfigureerde max-master/MAC-lijst**: de tool leert de masters op de
  lijn kennen via Poll-For-Master, maar je kan ze niet vooraf ingeven.

## Als er niets gebeurt

| Symptoom | Waarschijnlijk |
|---|---|
| "kon niet verzenden — geen token van een andere master" | Er is geen andere master op de lijn die de token doorgeeft. Op een lijn met alleen FlexPoll hoort de tool zichzelf sole master te maken; gebeurt dat niet, controleer dan de bedrading en de baudrate. |
| Timeouts bij elke Who-Is | Baudrate of pariteit wijkt af, of A/B staan omgekeerd. |
| Eén toestel antwoordt niet | Ander MAC-adres dan verwacht, of het toestel staat op een ander segment. |
| Alles werkt, maar traag | Normaal: elk punt is een eigen verzoek, en tussen twee frames moet de token rond. |

De **buslog** in het Modbus-tabblad helpt niet bij MS/TP (dat is een andere
laag); kijk naar de console of `journalctl -u flexpoll -f` voor de details van de
seriële poort.
