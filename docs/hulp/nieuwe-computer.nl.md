# Naar een nieuwe computer

Verhuis je Huismus naar een nieuwe computer, Raspberry Pi, NAS of server? Je
administratie neem je mee met een back-up. Een paar instellingen horen bij
het apparaat en stel je daar opnieuw in.

## Verhuizen in vier stappen

1. **Maak op de oude computer een back-up.** Kies **Instellingen → Back-ups
   → Nu back-up maken**. Gaan je back-ups naar Dropbox of WebDAV? Houd dan je
   herstelcode bij de hand. Die vind je onder **Beheren → Herstelcode
   bekijken**.
2. **Installeer Huismus op de nieuwe computer.** Hoe dat gaat, staat bij
   [De desktop-app](desktop-app.nl.md) en [Huismus in Docker](docker.nl.md).
3. **Zet de back-up terug.** Kies **Instellingen → Back-ups → Een back-up
   terugzetten…** en kies het bestand. Staat je back-up in de cloud? Koppel
   dan eerst dezelfde cloud en kies **Heb je al een herstelcode van een
   eerdere installatie?**. Meer hierover staat bij
   [Back-ups](back-ups.nl.md#een-back-up-terugzetten).
4. **Gebruik de oude computer niet meer voor Huismus.** Anders heb je twee
   administraties die uit elkaar gaan lopen, met dezelfde factuurnummers
   voor verschillende facturen.

## Wat meekomt

Alles van je administratie: je facturen, offertes en creditnota's, je
klanten, je uitgaven en bonnetjes, je logo en je instellingen. Ook je inlog
komt mee: je gebruikersnaam en wachtwoord blijven hetzelfde. In de
desktop-app geldt dat ook voor het wachtwoord van de app.

## Wat je opnieuw instelt

Dit zit bewust niet in een back-up. Het zijn sleutels en wachtwoorden die
niet mogen rondgaan met een kopie van je back-up, en mappen die op elke
computer anders heten.

- **Je back-upmap of cloud.** Kies opnieuw een map bij **Instellingen →
  Back-ups**, of koppel Dropbox of WebDAV opnieuw met je herstelcode. Zolang
  je dat niet doet, maakt Huismus geen back-ups. Het overzicht zegt dat met
  een oranje melding.
- **Je mailwachtwoord.** Vul het opnieuw in bij **Instellingen → Mailen**.
  De rest van je mailinstellingen staat er al. Ontbreekt je wachtwoord, dan
  zegt Huismus dat na het terugzetten, en ook als je een factuur wilt mailen.
- **Je bonnetjesmap.** Kies hem opnieuw bij **Instellingen → Bonnetjesmap**.
  Bonnetjes die Huismus al had opgehaald, staan gewoon in je administratie.
- **De AI-dienst die je bonnetjes leest.** Kies de dienst opnieuw bij
  **Instellingen → Bonnetjes lezen met AI** en vul je sleutel in.
- **Je AI-assistenten.** Kies **Koppelen** bij **Instellingen →
  AI-assistenten** en geef je assistent de nieuwe sleutel. De oude sleutel
  werkt op de nieuwe computer niet.
- **Updates.** Had je **Automatisch bijwerken** uitgezet, of in Docker
  **Zoeken naar nieuwe versies**? Zet het dan opnieuw uit bij
  **Instellingen → Updates**.
- **Inloggen op je andere apparaten.** Na het terugzetten blijf je ingelogd
  in de browser waarin je het deed. Op andere apparaten log je opnieuw in.

## Draait Huismus in Docker?

Wat in je `compose.yaml` of in je opdracht staat, zit ook niet in een
back-up: het adres en de mappen die je aan Huismus koppelt. Zet dat op de
nieuwe server opnieuw op, zoals bij [Huismus in Docker](docker.nl.md) staat.
Een map voor je back-ups koppel je zoals bij
[Een map koppelen](back-ups.nl.md#een-map-koppelen) staat.

Heeft de nieuwe server een ander adres? Zet Huismus dan opnieuw op het
beginscherm van je telefoon. Hoe dat gaat, lees je bij
[Op je telefoon](telefoon.nl.md).
