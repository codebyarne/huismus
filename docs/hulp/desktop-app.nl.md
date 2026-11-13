# De desktop-app

Met de desktop-app gebruik je Huismus als gewone app op je Mac of
Windows-pc, zonder server. Je administratie staat dan op je eigen computer.
De app werkt op macOS 15 (Sequoia) of nieuwer met een Apple-chip, en op Windows 10 of
nieuwer.

## De eerste keer openen

**Mac.** Apple heeft de app niet ondertekend. Daarom weigert macOS hem de
eerste keer te openen. Ga dan naar Systeeminstellingen → Privacy en
beveiliging en kies **Toch openen**.

**Windows.** Ook de installer is niet ondertekend. De eerste keer zegt
Windows "Windows heeft uw pc beschermd". Kies **Meer informatie** en dan
**Toch uitvoeren**. Je hebt geen beheerdersrechten nodig om Huismus te
installeren.

Op Windows heeft Huismus Microsoft Edge WebView2 nodig voor zijn venster.
Windows 11 en een bijgewerkt Windows 10 hebben dat al. Ontbreekt het, dan
vraagt Huismus of je het nu bij Microsoft wilt downloaden. Installeer het en
open Huismus opnieuw.

Wil je eerst rondkijken? Kies op het lege overzicht **Probeer met nepdata**.
Huismus vult zich dan met voorbeelden. Met de knop
**Nepdata leegmaken** haal je ze weer weg.

## Openen en sluiten

Bij het openen staat er even "Huismus start…" in het venster. Daarna draait
Huismus alleen op je eigen computer. Van buitenaf kan niemand erbij. Sluit
je het venster, dan stopt Huismus helemaal.

Huismus kan maar één keer tegelijk open. Open je hem nog een keer, dan komt
het venster dat al open is naar voren.

Lukt het starten niet, dan zegt het venster dat. Je ziet dan een foutcode en
de knoppen **Opnieuw proberen** en **Logbestand bewaren**. Vraag je iemand
om hulp, stuur dan het logbestand mee.

## Een wachtwoord instellen

Huismus opent zonder wachtwoord, tenzij je er een instelt bij **Instellingen
→ Wachtwoord**. Daarna vraagt de app het elke keer dat je hem opent.

Wil je het wachtwoord wijzigen of uitzetten, dan vraagt Huismus eerst het
huidige. Het wachtwoord gaat mee in elke back-up. Ben je het vergeten, dan
kan Huismus het niet terughalen.

Zet je een back-up van een server terug, zoals van een Raspberry Pi, dan
vraagt de app voortaan het wachtwoord van die server.

## Back-ups

Bij **Instellingen → Back-ups** kies je één keer een map. Daarna maakt
Huismus elke dag een back-up, zolang de app open staat. Huismus stelt de
mappen voor van iCloud Drive, Google Drive, OneDrive en Dropbox die hij op
je computer vindt. Staat Google Drive op Windows niet op `G:`, kies hem dan
met **Andere map…**. Meer lees je in [Back-ups](back-ups.nl.md).

## Bijwerken naar een nieuwe versie

Bij het openen en daarna eens per dag kijkt Huismus of er een nieuwe versie
is. Dat is het enige wat Huismus uit zichzelf op internet opvraagt: de
openbare lijst met versies, verder niets. Wil je dat niet, zet dan
**Automatisch bijwerken** uit bij **Instellingen → Updates**.

Is er een nieuwe versie, dan downloadt Huismus hem op de achtergrond en
controleert hem. Zolang dat duurt, zegt het overzicht "Huismus … is gevonden
en wordt gedownload"; daarna "Huismus … staat klaar". Je hoeft
niets te doen: de volgende keer dat je Huismus opent, maakt hij eerst een
back-up, installeert de nieuwe versie en opent vanzelf weer. Dat duurt
ongeveer een minuut. Op het overzicht staat daarna "Huismus is bijgewerkt
naar …", met een link naar [Wat is er nieuw](nieuw.nl.md).
Terwijl je werkt, wordt Huismus nooit bijgewerkt.

Wil je niet wachten? Kies dan bij **Instellingen → Updates** **Nu zoeken**,
of **Bijwerken naar …** als er al een nieuwe versie is, en bevestig.

Lukt het bijwerken niet, dan zegt het venster dat, met de knoppen **Back-up
terugzetten** en **Logbestand bewaren**. Installeer daarna de vorige versie
opnieuw.

## Waar alles staat

| Wat | Mac | Windows |
|---|---|---|
| Je administratie | `~/Library/Application Support/Huismus` | `%APPDATA%\Huismus` |
| Logbestand | `~/Library/Logs/Huismus/huismus.log` | `%LOCALAPPDATA%\Huismus\huismus.log` |
| Back-ups van vóór terugzetten, als er geen map gekozen is | `~/Library/Application Support/Huismus back-ups` | `%APPDATA%\Huismus back-ups` |
| De app zelf | waar je `Huismus.app` neerzet | `%LOCALAPPDATA%\Programs\Huismus` |

## Huismus verwijderen

Op een Mac sleep je `Huismus.app` naar de prullenmand. Op Windows verwijder
je Huismus via Instellingen → Apps. Je administratie blijft dan gewoon
staan. Wil je die ook weg hebben, maak dan eerst een back-up als je hem nog
nodig kunt hebben, en verwijder daarna zelf de map uit de tabel hierboven.
