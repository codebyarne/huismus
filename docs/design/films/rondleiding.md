# De rondleiding

De film op de Nederlandse homepage, in het blok "Huismus in één minuut": een
rondleiding door de app in 82 seconden, met stem, muziek en ondertitels. De
eigenaar heeft beeld en geluid gekeurd (`huismus-intern/besluiten.md`,
2026-11-19). Versie 2 (2026-11-23) laat ook bonnetjes uit je map, je bankafschrift,
de btw-aangifte en overstappen uit een ander pakket zien; de offerte ging eruit.
Roos klinkt vrolijker (take A) en de muziek is een vrolijker nummer van 80 seconden;
de eigenaar keurde beeld en geluid op 2026-11-25.

- **Beeld:** het echte venster van Huismus op nepdata, licht, in "Helder". Het
  venster kantelt en de kaarten van een scherm komen los; een label linksboven
  zegt wat je ziet. Aan het slot hupt de mus op de goot, zoals op de site.
- **Stem:** Nederlands, je en jij, volgens `docs/schrijfwijzer.md`. Niets over
  wet of belasting: de film zegt wat je op het scherm ziet. Eén doorlopende
  opname, niet per zin geknipt: een knip in de stem valt op.
- **Ondertitels:** dezelfde woorden als losse `.vtt`, met de tijden van de
  opname.

## Wat er gezegd wordt

| # | Tijd | Beeld | Stem |
|---|---|---|---|
| 1 | 0:00 | Een factuur rolt uit, met de cijfers van het jaar eromheen. | Je facturen, je klanten, je bonnetjes. Het is jouw administratie! Dus waarom zou die bij iemand anders staan? |
| 2 | 0:08 | Het logo. | Dit is Huismus! Boekhouding voor zzp’ers, gewoon op je eigen computer. |
| 3 | 0:13 | Het Overzicht: de omzet, wat je nog ontvangt en Te doen. | Je ziet meteen wat er openstaat, wat je dit jaar omzette, en welke offerte nog op antwoord wacht. |
| 4 | 0:19 | Een nieuwe factuur: klant, regel, totaal, uitgeven. | Een factuur maak je in een paar klikken. Kies een klant, typ wat je deed, en Huismus rekent het totaal uit. Geef hem uit, en hij krijgt een vast nummer! |
| 5 | 0:30 | Verwerken: het bonnetje naast wat Huismus las, dan Klopt. | Bonnetjes zet je als foto in een map, ook vanaf je telefoon. Huismus haalt ze op, en jij kijkt ze na. |
| 6 | 0:37 | Bank: een afschrift inlezen, dan Geboekt. | Lees je bankafschrift in. Huismus legt elke betaling naast je facturen en uitgaven. |
| 7 | 0:43 | Het jaaroverzicht, dan de btw-aangifte van een kwartaal. | Je hele jaar staat op één scherm! Omzet, kosten en winst. Reken je btw? Dan staan de bedragen voor je aangifte per kwartaal klaar. |
| 8 | 0:53 | Importeren: de proefdraai, dan "Je administratie is verhuisd". | Kom je van Moneybird, een ander pakket of Excel? Dan neem je al je jaren gewoon mee! Huismus doet eerst een proefdraai, en slaat pas iets op als jij dat kiest. |
| 9 | 1:03 | Huismus op een Mac, op Windows en in de browser, met vier vinkjes. | Huismus draait op je Mac, op je pc, of op je eigen server. Helemaal gratis! Zonder abonnement, en zonder account. En je gegevens? Die blijven gewoon bij jou. |
| 10 | 1:15 | De mus op de goot en de kop van de site. | Huismus. Je boekhouding, op je eigen computer! |

Scène 5 tot en met 7 spelen in de administratie met btw (`demo_data --site --zonder-kor`),
de rest in die met de KOR. Het bankafschrift is verzonnen, voor die administratie.

## In het Engels

Sinds 2026-11-25 staat dezelfde film in het Engels op de Engelse homepage: de app
in het Engels, de labels in beeld en het slot in het Engels, dezelfde muziek.
Roos spreekt ook de Engelse tekst in. Ze leest Huismus als "Heuys-mus", omdat ze de
naam dan goed uitspreekt (gekozen door de eigenaar); in de ondertitels staat
Huismus. De nepgegevens blijven Nederlands, zoals bij een Nederlandse zzp'er: het
bonnetje, de categorieën, de omschrijvingen op het afschrift en de KOR-tekst.

| # | Stem |
|---|---|
| 1 | Your invoices, your customers, your receipts. It's your bookkeeping! So why should it live with someone else? |
| 2 | This is Huismus! Bookkeeping for freelancers, right on your own computer. |
| 3 | At a glance you see what's still open, what you earned this year, and which quote is waiting for an answer. |
| 4 | An invoice takes just a few clicks. Pick a customer, type what you did, and Huismus adds up the total. Issue it, and it gets a fixed number! |
| 5 | Save photos of your receipts in a folder, even from your phone. Huismus picks them up, and you check them. |
| 6 | Import your bank statement. Huismus puts every payment next to your invoices and expenses. |
| 7 | Your whole year on one screen! Revenue, costs and profit. Charging VAT? Then the amounts for your return are ready every quarter. |
| 8 | Coming from Moneybird, another package or Excel? Bring all your years with you! Huismus does a trial run first, and only saves when you say so. |
| 9 | Huismus runs on your Mac, your PC, or your own server. Completely free! No subscription, and no account. And your data? It simply stays with you. |
| 10 | Huismus. Your bookkeeping, on your own computer! |

## Opnieuw maken

De film is niet met `scripts/promo-film.sh` gemaakt. Een script speelt de
scènes af in de echte app (Playwright), binnen een pagina die het venster
kantelt en de kaarten laat zweven, en schiet elk beeld. De stem en de muziek
komen van ElevenLabs (stem "Roos"), een betaalde dienst; daarom staan het
script, de opname van de stem en de muziek voorlopig in
`huismus-intern/promo-video/`, met de stappen in de README daar.

Verandert een scherm uit de film, maak hem dan daar opnieuw en zet vier
bestanden in `docs/site/`: `film-rondleiding.nl.mp4` (1280×720, onder de 3 MB,
voor een telefoon), `film-rondleiding.nl.hd.mp4` (1920×1080, onder de 8 MB,
voor een breed scherm), `film-rondleiding.nl.webp` (het stilstaande beeld) en
`film-rondleiding.nl.vtt` (de ondertitels); voor de Engelse film dezelfde vier met
`.en.` (`FILM_LANG=en`, zie de README daar). Verandert de tekst, wijzig hem dan ook in de tabel hierboven.
