# Bonnetjes onderweg

Maak onderweg een foto of scan van een bonnetje en zet hem in een map die
synchroniseert, zoals iCloud Drive of Dropbox. Huismus haalt hem meestal
binnen een paar minuten op. Thuis maak je er met één klik een uitgave van, met het bonnetje
er al aan vast.

## Een bonnetjesmap instellen

Ga naar **Instellingen → Bonnetjesmap** en kies waar Huismus kijkt.

- **In de desktop-app** kies je een map op je laptop. Huismus stelt een map
  `Huismus bonnetjes` voor in iCloud Drive, Google Drive, OneDrive of
  Dropbox, als die op je laptop staan. Huismus maakt de map meteen aan, zodat
  je hem ook op je telefoon ziet.
- **In Docker, bijvoorbeeld op een Raspberry Pi,** kies je **Dropbox** of
  **WebDAV**. Daarvoor stel je die eerst in bij **Instellingen → Back-ups**.
  Huismus haalt de bonnetjes zelf op en blijft onbereikbaar vanaf internet.
  - Met **Dropbox** kijkt Huismus in **Apps › Huismus › Bonnetjes** in je
    Dropbox.
  - Met **WebDAV**, zoals Nextcloud, kDrive of Koofr, kijkt Huismus in de map
    **Huismus › Bonnetjes**, naast je back-ups. In de app van je opslagdienst
    op je telefoon zie je die map ook.
- Gebruik je Syncthing? Kies dan een gewone map die Syncthing bijhoudt. In
  Docker koppel je die eerst, zie [Huismus in Docker](docker.nl.md).

Huismus kijkt meteen als er iets in de map of in Dropbox verandert. Een
bestand in een map haalt hij op als het een minuut niet meer verandert, zodat
het helemaal gesynchroniseerd is. Voor de zekerheid kijkt hij ook elke 10
minuten. Bij WebDAV kijkt hij alleen elke 10 minuten. Komt er iets binnen, dan zie je op het overzicht bijvoorbeeld **2
nieuwe bonnetjes**. Wil je niet wachten, klik dan op **Nu ophalen**.

## Een bonnetje bewaren op je telefoon

**iPhone:** open de foto, tik op het deelsymbool en kies **Bewaar in
Bestanden**. Kies de map, bijvoorbeeld iCloud Drive › Huismus bonnetjes.

Tip: in de app Bestanden kun je een bonnetje meteen scannen. Open de map,
tik op de drie puntjes en kies **Scan documenten**. Dat maakt een pdf.

**Android:** deel de foto met de app van je dienst, zoals Google Drive,
OneDrive, Dropbox of Nextcloud, en kies de map.

Huismus haalt pdf's, JPG's, PNG's en HEIC-foto's van de iPhone op, tot
10 MB per bestand. Huismus bewaart een HEIC-foto als JPG. Het origineel
staat in de map **Opgehaald**.

## Wat Huismus met het bestand doet

Huismus bewaart het bonnetje eerst in je administratie. Daarna verplaatst
hij het in je map naar de map **Opgehaald**. Zo zie je wat binnen is, en
haalt Huismus niets twee keer op.

Lukt iets niet, dan blijft het bestand gewoon in je map staan. Bijvoorbeeld
een Word-bestand, of een bestand dat groter is dan 10 MB. De pagina
Bonnetjesmap zegt dan welk bestand het is en waarom.

## Een uitgave maken van een bonnetje

Bij **Uitgaven** staat de knop **Bonnetjes**, met hoeveel bonnetjes er nog
geen uitgave hebben. Klik op **Uitgave maken** bij een bonnetje: je krijgt
het gewone formulier, met het bonnetje al bovenaan. Vul de rest in en klik
op **Opslaan**. Wacht er nog een bonnetje, dan krijg je meteen het volgende.
Wil je er een later doen, klik dan op **Overslaan**.

Heb je een bonnetje niet nodig, verwijder het dan uit de lijst. Het bestand
blijft in de map **Opgehaald** staan.

## Laat je AI-assistent ze verwerken

Heb je een AI-assistent gekoppeld (zie [AI-assistenten](ai-assistenten.nl.md)),
zeg dan: **Verwerk mijn bonnetjes in Huismus.** Hij leest elk bonnetje en
maakt de uitgave, met het bonnetje eraan. Kan hij een bonnetje niet lezen,
dan zegt hij dat en blijft het bij de bonnetjes zonder uitgave. Wat je
assistent invulde, staat bij **Uitgaven** onder **Nakijken**. Open de
bovenste en klik op **Klopt** als alles goed is: je krijgt meteen de
volgende. Met **Overslaan** laat je er een staan voor later.

Je assistent ziet je bonnetjes alleen als je hem dit vraagt. Huismus stuurt
zelf niets naar een AI-dienst.
