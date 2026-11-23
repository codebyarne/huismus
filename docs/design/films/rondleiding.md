# De rondleiding

De film op de Nederlandse homepage, in het blok "Huismus in één minuut": een
rondleiding door de app in ongeveer 80 seconden, met stem, muziek en ondertitels. De
eigenaar heeft beeld en geluid gekeurd (`huismus-intern/besluiten.md`,
2026-11-19). Versie 2 (2026-11-23) laat ook bonnetjes uit je map, je bankafschrift,
de btw-aangifte en overstappen uit een ander pakket zien; de offerte ging eruit.

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
| 2 | 0:07 | Het logo. | Dit is Huismus! Boekhouding voor zzp’ers, gewoon op je eigen computer. |
| 3 | 0:12 | Het Overzicht: de omzet, wat je nog ontvangt en Te doen. | Je ziet meteen wat er openstaat, wat je dit jaar omzette, en welke offerte nog op antwoord wacht. |
| 4 | 0:18 | Een nieuwe factuur: klant, regel, totaal, uitgeven. | Een factuur maak je in een paar klikken. Kies een klant, typ wat je deed, en Huismus rekent het totaal uit. Geef hem uit, en hij krijgt een vast nummer! |
| 5 | 0:29 | Verwerken: het bonnetje naast wat Huismus las, dan Klopt. | Bonnetjes zet je als foto in een map, ook vanaf je telefoon. Huismus haalt ze op, en jij kijkt ze na. |
| 6 | 0:36 | Bank: een afschrift inlezen, dan Geboekt. | Lees je bankafschrift in. Huismus legt elke betaling naast je facturen en uitgaven. |
| 7 | 0:42 | Het jaaroverzicht, dan de btw-aangifte van een kwartaal. | Je hele jaar staat op één scherm! Omzet, kosten en winst. Reken je btw? Dan staan de bedragen voor je aangifte per kwartaal klaar. |
| 8 | 0:52 | Importeren: de proefdraai, dan "Je administratie is verhuisd". | Kom je van Moneybird, een ander pakket of Excel? Dan neem je al je jaren gewoon mee! Huismus doet eerst een proefdraai, en slaat pas iets op als jij dat kiest. |
| 9 | 1:01 | Huismus op een Mac, op Windows en in de browser, met vier vinkjes. | Huismus draait op je Mac, op je pc, of op je eigen server. Helemaal gratis! Zonder abonnement, en zonder account. En je gegevens? Die blijven gewoon bij jou. |
| 10 | 1:13 | De mus op de goot en de kop van de site. | Huismus. Je boekhouding, op je eigen computer! |

Scène 5 tot en met 7 spelen in de administratie met btw (`demo_data --site --zonder-kor`),
de rest in die met de KOR. Het bankafschrift is verzonnen, voor die administratie.

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
`film-rondleiding.nl.vtt` (de ondertitels). Verandert de tekst, wijzig hem dan ook in de tabel hierboven.
