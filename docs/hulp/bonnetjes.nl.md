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
geen uitgave hebben. Klik op **Uitgave maken** bij een bonnetje: je komt in
**Verwerken** (zie hieronder), met het bonnetje groot naast de velden. Vul
ze in en klik op **Opslaan**. Je krijgt meteen het volgende.

Heb je een bonnetje niet nodig, verwijder het dan uit de lijst. Het bestand
blijft in de map **Opgehaald** staan.

## Alles in één keer verwerken

Bonnetjes komen een maand of een kwartaal lang vanzelf binnen. Verwerk ze dan
in één keer: klik bij **Uitgaven** op **Verwerken**. Het getal erachter is
hoeveel er op je wachten: eerst de uitgaven om na te kijken, dan de
bonnetjes zonder uitgave.

Je ziet er steeds één. Links staat het bonnetje groot, rechts de velden van
de uitgave, en bovenaan waar je bent, bijvoorbeeld **3 van 24**. Op je
telefoon staat het bonnetje boven de velden.

- Bij een uitgave om na te kijken: klopt alles, klik dan op **Klopt**.
- Bij een bonnetje: vul de velden in en klik op **Opslaan**.
- Wil je er een later doen? Klik op **Overslaan**. Hij komt aan het eind
  weer langs.

Na de laatste zie je **Niets meer te verwerken.** Een pdf zie je op de
computer met alle pagina's. Op je telefoon, of als je het bonnetje groter wilt
zien, klik je op **Bonnetje openen**.

## Laat je AI-assistent ze verwerken

Heb je een AI-assistent gekoppeld (zie [AI-assistenten](ai-assistenten.nl.md)),
zeg dan: **Verwerk mijn bonnetjes in Huismus.** Hij leest elk bonnetje en
maakt de uitgave, met het bonnetje eraan. Kan hij een bonnetje niet lezen,
dan zegt hij dat en blijft het bij de bonnetjes zonder uitgave. Wat je
assistent invulde, krijgt het label **Nakijken** en staat bij **Uitgaven**
onder **Verwerken**. Klik op **Klopt** als alles goed is: je krijgt meteen
de volgende.

Je assistent ziet je bonnetjes alleen als je hem dit vraagt. Wil je dat
Huismus ze zelf laat lezen, zie dan hieronder.

## Bonnetjes lezen

Huismus kan je bonnetjes ook zelf laten lezen, zonder dat je het vraagt. Dat
doet hij met een AI-dienst die jij kiest, met je eigen sleutel. Elk bonnetje
dat binnenkomt, wordt dan vanzelf een uitgave met **Nakijken**. Jij kijkt
hem na en klikt op **Klopt**.

Ga naar **Instellingen → Bonnetjes lezen** en kies een dienst:

- **Anthropic (Claude), Google Gemini, Mistral of OpenAI.** Maak op de site
  van de dienst een account en een API-sleutel. Huismus vult het adres en een
  model in dat foto's kan lezen. Je betaalt de dienst zelf, per bonnetje een
  klein bedrag. Kijk op de site van de dienst wat het kost.
- **Ollama**, op je eigen computer of in je eigen netwerk. Dan gaan je
  bonnetjes niet het internet op, en heb je geen sleutel nodig. Kies een
  model dat foto's kan lezen. Draait Huismus in Docker, gebruik dan het adres
  van de computer met Ollama in je netwerk, bijvoorbeeld
  `http://192.168.1.20:11434/v1`.
- **Andere dienst.** Elke dienst die werkt met OpenAI-compatibele apps. Vul
  het adres, het model en je sleutel in.

Huismus probeert de dienst bij **Opslaan** eerst met één klein plaatje. Lukt
dat niet, dan zegt Huismus waarom en bewaart hij niets. Je sleutel zie je
daarna niet meer terug, en hij gaat niet mee in je back-ups.

Na het opslaan leest Huismus ook de bonnetjes zonder uitgave die er al
waren. Op het overzicht zie je dan bijvoorbeeld **2 nieuwe uitgaven om na te
kijken**.

### Wat Huismus laat liggen

Huismus raadt nooit een bedrag. Een bonnetje blijft bij de bonnetjes zonder
uitgave, met de reden erbij, als:

- het niet goed leesbaar is, of geen bonnetje is;
- er meer bonnetjes op staan;
- er geen totaal op staat, of de bedragen niet optellen tot het totaal;
- de btw er niet bij staat, terwijl je de KOR niet gebruikt;
- het lijkt op een uitgave die je al hebt: dezelfde dag en hetzelfde bedrag.

Maak die uitgave dan zelf, met **Uitgave maken**. Huismus stuurt hetzelfde
bonnetje nooit twee keer naar de dienst.

Lukt het lezen even niet, omdat de dienst je sleutel weigert of niet
bereikbaar is? Dan zie je dat in rood bij de bonnetjes zonder uitgave. De
bonnetjes wachten, en Huismus probeert het opnieuw als hij de volgende keer
in je bonnetjesmap kijkt.

Zet het uit met **Uitzetten** op dezelfde pagina. Huismus vergeet dan de
dienst en je sleutel.
