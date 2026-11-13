# Wat is er nieuw

Ongeveer elke twee weken komt er een nieuwe versie van Huismus. Hier lees je per versie
wat je er nu mee kunt. De nieuwste staat bovenaan.

Na een nieuwe versie wijst een melding op het overzicht je hierheen.

## 0.1.4, 13 november 2026

- **Bonnetjes onderweg.** Bewaar een foto van een bonnetje op je telefoon in je
  bonnetjesmap. Huismus haalt hem op, en op het overzicht zie je bijvoorbeeld
  **2 nieuwe bonnetjes**. De map kies je bij **Instellingen → Bonnetjesmap**:
  een map in iCloud Drive, Google Drive, OneDrive of Dropbox, of in Docker
  Dropbox of WebDAV. Foto's van een iPhone (HEIC) werken ook. Zo werkt het:
  [Bonnetjes onderweg](bonnetjes.nl.md).
- **Alles in één keer verwerken.** Met **Verwerken** loop je de bonnetjes
  zonder uitgave een voor een door, met het bonnetje groot naast de velden.
  Na **Opslaan** of **Klopt** komt het volgende bonnetje.
- **Huismus leest je bonnetjes zelf**, als je dat wilt. Kies bij
  **Instellingen → Bonnetjes lezen met AI** een AI-dienst met je eigen
  sleutel, of Ollama op je eigen computer. Elk nieuw bonnetje wordt dan een
  uitgave met **Nakijken**. Ook wat een AI-assistent invult, krijgt
  **Nakijken**.
- **De btw-aangifte.** Onder **Rapporten → Btw-aangifte** zie je per kwartaal,
  maand of jaar wat je in elke rubriek invult, en wat je betaalt of
  terugkrijgt. Met **CSV downloaden** krijg je hetzelfde als bestand. Je neemt
  de bedragen zelf over; Huismus verstuurt niets. Zo werkt het:
  [KOR en btw](kor-en-btw.nl.md#btw-aangifte).
- **Btw per uitgaveregel.** Staat de KOR uit, dan kies je bij elke
  uitgaveregel het btw-tarief. Het jaaroverzicht toont je kosten dan zonder
  btw en de voorbelasting apart. Bij een import uit Moneybird neemt Huismus
  het tarief mee als de naam ervan duidelijk is.
- **De hulp in groepen**, zodat je sneller vindt wat je zoekt.
- **Na een nieuwe versie** zegt het overzicht één keer dat Huismus is
  bijgewerkt, met een link naar deze pagina. **Nu zoeken** bij
  **Instellingen → Updates** kijkt meteen of er een nieuwe versie is.
- **De Mac-app heeft nu macOS 15 (Sequoia) of nieuwer nodig.** Heb je nog
  macOS 14? Werk je Mac dan bij via **Systeeminstellingen → Algemeen →
  Software-update**. Je administratie blijft staan.
- **Kleinere verbeteringen.** Een factuurregel staat op één rij. Een brede
  tabel scrolt binnen zijn kaart in plaats van afgeknipt te worden. Een
  foutpagina zegt in gewone woorden wat er mis is, zonder foutcode.

## 0.1.3, 4 november 2026

- **Kies het bonnetje meteen bij een nieuwe uitgave.** Je hoeft de uitgave niet
  eerst op te slaan. Het bonnetje staat nu bovenaan het formulier, want de rest
  typ je er meestal van over. Bij een bestaande uitgave staan de bonnetjes boven
  het formulier.
- **De + op je telefoon** opent nu een keuze: Factuur, Offerte, Klant of
  Uitgave, net als **Nieuw** op de computer. Eerst maakte hij alleen een
  factuur.
- **Wat is er nieuw** staat onder **Hulp**: per versie wat je ermee kunt, zoals
  deze pagina. De melding over een nieuwe versie linkt er ook naar.
- **Geen back-up kwijt in de cloud.** Werden er twee back-ups in dezelfde seconde
  naar Dropbox of WebDAV gestuurd, bijvoorbeeld als je de koppeling snel
  opnieuw maakte, dan overschreef de tweede de eerste. Nu blijven ze allebei.

## 0.1.2, 4 november 2026

- **De desktop-app werkt zichzelf bij.** Is er een nieuwe versie, dan haalt
  Huismus die op de achtergrond op. De volgende keer dat je de app opent, maakt
  hij eerst een back-up en installeert hij de nieuwe versie. Wil je niet
  wachten? Kies **Instellingen → Updates → Bijwerken**.
- **Huismus in Docker zegt het als er een nieuwe versie is**, op het overzicht
  en bij **Instellingen → Updates**. Je ziet er ook wat je moet typen om bij te
  werken. Zo werkt het: [Huismus in Docker](docker.nl.md#bijwerken).
- **Eerst een back-up, dan de nieuwe versie.** Voordat een nieuwe versie in
  Docker je administratie bijwerkt, maakt Huismus een back-up. Gaat er iets
  mis, dan heb je die nog.

## 0.1.1, 4 november 2026

- **Stap voor stap beginnen** is nu de grote knop als je Huismus voor het eerst
  opent. Importeren uit Moneybird staat ernaast.
- **Hulp voor het dagelijkse werk.** Onder Hulp lees je nu hoe je facturen,
  offertes en uitgaven maakt, hoe mailen werkt en hoe je exporteert.
- **Een back-up terugzetten is veiliger.** Huismus neemt dan nooit de geheime
  sleutels uit het back-upbestand over. Die van je eigen installatie blijven.
- **Exporteren naar een spreadsheet is veiliger.** Tekst die begint als een
  formule, zoals `=SOM(…)`, blijft in Excel of Numbers gewoon tekst.
- **Op de Mac gaan menu's weer dicht** nadat je iets gekozen hebt.

## 0.1.0, 2 november 2026

De eerste versie. Je maakt offertes, facturen en creditnota's als pdf en mailt
ze naar je klant. Je houdt je uitgaven bij, met bonnetjes. Onder **Rapporten**
zie je per jaar je omzet en hoe ver je van de KOR-grens af zit. Kom je van
Moneybird, dan neem je je hele export mee. En Huismus maakt elke dag een
back-up: zie [Back-ups](back-ups.nl.md).
