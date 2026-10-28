# Beveiligingsbeleid

FlexPoll is een diagnose-tool: hij praat met industriële toestellen en heeft
daarvoor schrijfrechten nodig. Een fout kan een installatie in een verkeerde
stand zetten. Meld zulke problemen **niet** in een publieke issue.

## Melden

Stuur een mail naar de maintainer met:

- de versie (`python3 app.py --version`) en de commit-hash,
- welk transport het raakt (RTU, TCP, BACnet/IP),
- wat er misgaat en hoe je het reproduceert (config zonder klantgegevens),
- of het toestel iets deed dat het niet mocht doen.

Je krijgt een bevestiging binnen enkele dagen. Wordt het bevestigd, dan volgt een
fix en een patch-release; je wordt in de release notes vermeld, tenzij je liever
anoniem blijft.

## Wat in scope is

- Ongeautoriseerde schrijfacties of een verkeerde schaal/omrekening die een
  toestel in een gevaarlijke stand kan zetten.
- Injectie via de HTTP-API (pad, JSON, bestandsnaam), SSRF via de BACnet- of
  Modbus-client, of het lezen van bestanden buiten `data/`.
- Crashes die de polling-lus permanent stil leggen.

## Wat buiten scope is

- De tool heeft **geen authenticatie**. Hij is bedoeld voor een besloten
  netwerk; zet hem niet rechtstreeks op het internet. Dat is een ontwerpkeuze,
  geen kwetsbaarheid — maar zeg het ons als je een deployment ziet waar dat toch
  gebeurt.
- Alles wat het toestel zelf doet wanneer je er bewust een waarde naartoe
  schrijft.

## Ondersteunde versies

Alleen de laatste minor-release krijgt fixes.
