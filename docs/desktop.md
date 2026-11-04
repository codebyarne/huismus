# Huismus als desktop-app

Naast de Pi/Docker-route draait Huismus ook als gewone app op een Mac of op
Windows (SPEC.md M11). Het is dezelfde Django-app met dezelfde
SQLite-database; alleen het inpakken en de eerste start zijn anders. Dit is
nog een **prototype**: macOS 14 of nieuwer op Apple Silicon, en Windows 10 of
nieuwer op x64. Windows 11 op ARM draait de x64-versie via emulatie; Windows
10 op ARM en 32-bit Windows niet. De downloadpagina volgt.

Dit document is voor ontwikkelaars: hoe de app werkt en gebouwd wordt. De
uitleg voor gebruikers staat in
[`docs/hulp/desktop-app.nl.md`](hulp/desktop-app.nl.md), en in de app onder
Hulp.

## Wat er gebeurt als je de app opent

1. Het venster toont "Huismus start…".
2. De app voert de migraties uit en start de server op `127.0.0.1`, op poort
   8765 (zo blijft het adres voor AI-assistenten hetzelfde,
   `docs/hulp/ai-assistenten.nl.md`) of een vrije poort als die bezet is. Van buiten
   de computer is hij niet bereikbaar.
3. Het venster opent Huismus met een token dat bij elke start nieuw is. Het
   eerste verzoek ruilt het om voor een cookie; daarna staat het niet meer in
   het adres. Een browsertab of ander programma zonder dat token krijgt alleen
   "Open Huismus met de app op deze computer." (`huismus/core/desktop.py`).
4. Zonder wachtwoord logt het venster vanzelf in; er is dan ook geen knop
   Uitloggen. Staat er een gebruiker mét wachtwoord in de database (zoals na
   het terugzetten van een back-up van de Pi), dan vraagt de app bij het
   openen alleen het wachtwoord (zie "Wachtwoord" hieronder).
5. Lukt de start niet, dan zegt het venster dat, met "Opnieuw proberen",
   "Logbestand bewaren" en een foutcode (`database-vergrendeld`,
   `al-geopend`, of de naam van de fout).

Sluit je het venster, dan stopt de server. Er blijft niets op de achtergrond
draaien. Twee keer tegelijk openen kan niet (`desktop/lock.py`). Op de Mac zet
macOS dan zelf het open venster voor; op Windows haalt de tweede het open
venster naar voren en stopt (`desktop/windows.py`). Lukt dat niet, dan zegt
het venster `al-geopend`.

Op Windows heeft het venster Microsoft Edge WebView2 nodig
(`desktop/webview2.py`); wat een gebruiker ziet als het ontbreekt, staat in
[`docs/hulp/desktop-app.nl.md`](hulp/desktop-app.nl.md).

## Wachtwoord

Standaard opent Huismus zonder wachtwoord. Bij Instellingen → Wachtwoord
(`/instellingen/wachtwoord/`, `huismus/core/password_views.py`) zet je de schakelaar
aan; dan verschijnen de velden (alleen CSS, geen JavaScript) en stel je een
wachtwoord in. Django's eigen regels gelden (minstens 8 tekens, niet te
gewoon). Daarna vraagt de app het bij elke start: het inlogscherm toont dan
alleen het veld Wachtwoord, en de sessie eindigt als de app sluit.

Wijzigen en uitzetten vragen eerst het huidige wachtwoord. Een fout telt mee
in dezelfde rem als op het inlogscherm (10 pogingen per kwartier). Na het
juiste huidige wachtwoord mag je het binnen 10 minuten één keer wijzigen.
Uitgezet logt het venster weer vanzelf in. Het venstertoken blijft altijd
nodig. Het wachtwoord zit in de database, dus ook in elke back-up; de app
kan het niet terughalen.

## Back-ups

In Instellingen → Back-ups kies je één keer een map: een gevonden map van
iCloud Drive, Google Drive, OneDrive of Dropbox, of "Andere map…" (een
USB-stick). Huismus maakt alleen de laatste map aan (bijvoorbeeld "Huismus");
bestaat de map daarboven niet, dan zegt hij dat. Een map in of rond je
administratie kan niet: de database zelf gaat nooit in die map, alleen de
archieven van `manage.py backup`. "Kiezen…" opent het mapvenster van het
systeem, alleen in de app zelf.

Op Windows stelt Huismus voor wat hij vindt van OneDrive
(`%USERPROFILE%\OneDrive`, ook "OneDrive - Bedrijf" van een werkaccount),
iCloud Drive (`%USERPROFILE%\iCloudDrive`), Dropbox en Google Drive op
`G:\Mijn Drive` of `G:\My Drive`. Staat Google Drive op een andere letter,
kies hem dan met "Andere map…".

- **Wanneer:** meteen na het kiezen, dan bij het openen van de app en elk
  uur dat hij open staat, als er vandaag nog geen back-up is
  (`huismus/core/auto_backups.py`, `desktop/app.py`).
- **Bewaren:** alles van de laatste 30 dagen, daarvoor de nieuwste van elke
  maand, en altijd de allernieuwste. Huismus ruimt alleen zijn eigen
  archieven op (`huismus-backup-<datum>-<tijd>.tar.gz`).
- **Melding op het overzicht:** rood als de laatste back-up mislukte (map niet
  bereikbaar of vol), oranje zonder gekozen map of na 7 dagen zonder
  back-up. Daaronder "Laatste back-up: vandaag 09:12".
- **Terugzetten** (Back-ups → "Een back-up terugzetten…"): een back-up uit
  de lijst of een ander bestand (zoals een back-up van de Pi). Huismus
  controleert het bestand eerst, maakt een back-up van hoe het nu is, en
  zet dan terug; intussen zegt elke pagina "Even geduld". Daarna lopen de
  migraties, voor een back-up van een oudere versie. Een back-up van een
  nieuwere versie weigert hij. Is er nog geen map gekozen, dan gaat de
  back-up van vóór het terugzetten naar `Huismus back-ups` naast de
  administratie.

De gekozen map en hoe de laatste back-up ging staan in
`backup-status.json` in de administratie (net als de update-instelling in
`update-status.json`), maar niet in een back-up: ze horen
bij deze computer. Na terugzetten blijft de map gekozen; op een andere
computer kies je hem opnieuw.

## Updates

Bij het openen en daarna eens per dag kijkt de app in de releaselijst van
GitHub of er een nieuwere versie is (`huismus/core/updates.py`). Dat is het enige
verzoek dat Huismus naar buiten doet: alleen de openbare lijst, met als
User-Agent "Huismus" en verder niets. In Instellingen → Updates staat het
uit te zetten ("Automatisch bijwerken"); dan gaat er geen enkel verzoek meer
de deur uit en wordt een al gedownloade versie weggegooid.

Een release telt als:

- de tag precies `vX.Y.Z` is, hoger dan de huidige versie (uit
  `pyproject.toml`, dat in de app zit);
- hij geen concept of pre-release is;
- hij een bestand voor dit systeem heeft, `Huismus-<versie>-macos.dmg` of op
  Windows `Huismus-<versie>-windows.exe`, met de SHA-256 die GitHub bij elk
  bestand vermeldt (`digest`).

Bijwerken gaat vanzelf (besluit 2026-11-04, `huismus-intern/besluiten.md`).
Is er zo'n versie, dan downloadt de app hem meteen op de achtergrond naar
`.huismus-update` naast de administratie en controleert de SHA-256
(`updates.prepare`, in het uurritme van `desktop/app.py`; mislukt het, dan
een dag later weer). Daarna zegt de blauwe melding op het overzicht
"Huismus 1.4.0 staat klaar…". Bij het volgende openen, na het migreren en
vóórdat het venster Huismus laat zien, installeert de app hem
(`updates.install_at_start`): nooit midden in een sessie. "Bijwerken naar
1.4.0" op Instellingen → Updates doet hetzelfde meteen, na bevestiging.
Installeren gaat zo:

1. kan de app zichzelf hier niet vervangen (niet in een app, map niet
   schrijfbaar), dan stopt hij vóór er iets gebeurt (`updates.precheck`);
2. gebruikt Huismus het klaarstaande bestand (nog eens gecontroleerd), of
   downloadt het naar `.huismus-update` en controleert de SHA-256 (klopt die
   niet, of ontbreekt hij: niets installeren);
3. maakt hij een back-up, in de gekozen map of anders in `Huismus back-ups`;
4. schrijft hij in `update-status.json` van welke naar welke versie en waar
   de back-up staat, start hij een klein script (`desktop/updater.py`) en
   sluit hij. Het script wacht tot de app dicht is, zet `Huismus.app` uit het
   `.dmg` op de plaats van de oude (de oude blijft tot de kopie af is) en
   opent hem. Op Windows is het een PowerShell-script: dat wacht ook tot de
   app dicht is, controleert de SHA-256 nog een keer, draait de installer
   zonder vensters of vragen (`/VERYSILENT`) en opent Huismus weer.

De nieuwe versie draait bij het starten de migraties. Lukt dat, dan zegt het
overzicht "Bijgewerkt naar 1.4.0." Lukt het niet, dan toont het venster
"Bijwerken is niet gelukt" met "Back-up terugzetten", "Logbestand bewaren" en
een link naar de vorige versie. Na terugzetten start de server niet: deze
versie zou dezelfde migratie weer proberen. Installeer dan de vorige versie.

Automatisch wordt een versie één keer geprobeerd. Mislukt dat (de app kan
zichzelf niet vervangen, of het script gaf het op en opende de oude versie
weer), dan onthoudt `update-status.json` die versie (`auto_failed`): het
overzicht zegt één keer dat het niet lukte, en daarna kan alleen de knop het
nog. Een volgende versie probeert het weer vanzelf. Een mislukte back-up
telt niet als poging: dan start de huidige versie gewoon en probeert het bij
het volgende openen opnieuw.

Testen zonder releases: zet `HUISMUS_RELEASES_URL` op een eigen lijst (ook
een `file://`-adres), zoals `tests/fixtures/releases/releases.json`. Alleen
dan mag een download ook via iets anders dan HTTPS. Het echte vervangen van
de app kan alleen op een Mac of op Windows en is een handcontrole vóór de
eerste release.

## Waar alles staat

De mappen van de administratie, het logbestand en de app zelf, en het
verwijderen, staan voor gebruikers in
[`docs/hulp/desktop-app.nl.md`](hulp/desktop-app.nl.md#waar-alles-staat)
(`desktop/paths.py`). Daarnaast: de administratie bevat ook `secret-key`, en
het slot tegen twee keer openen is `~/Library/Application Support/Huismus.lock`
(Mac) of `%APPDATA%\Huismus.lock` (Windows).

`HUISMUS_DATA_DIR` gaat voor, net als op Docker. Zo kun je de app op een kopie
starten in plaats van op je echte administratie.

## Zelf bouwen

Nodig: een Mac met Apple Silicon, [uv](https://docs.astral.sh/uv/), en Pango
uit Homebrew (`brew install pango`). Pango gaat mee in de app; de Mac waarop
je hem opent heeft geen Homebrew nodig.

```bash
./scripts/build-mac.sh
```

Dat maakt `dist/Huismus.app` en `dist/Huismus.dmg` (ongeveer 80 MB en 45 MB).
Controleren zonder venster, op een kopie:

```bash
HUISMUS_DATA_DIR=/tmp/huismus-kopie dist/Huismus.app/Contents/MacOS/Huismus --check
```

Dat start alles behalve het venster, opent de eerste pagina zoals het venster
dat doet en maakt een PDF (van een uitgegeven document, als er een is). Het
eindigt met "Huismus werkt" of met "Controle mislukt" en het logbestand.

Op Windows, in Git Bash, met [uv](https://docs.astral.sh/uv/),
[Inno Setup 6](https://jrsoftware.org/isinfo.php) en Pango uit
[MSYS2](https://www.msys2.org/) (in de UCRT64-omgeving:
`pacman -S mingw-w64-ucrt-x86_64-pango mingw-w64-ucrt-x86_64-gettext-tools`):

```bash
./scripts/build-windows.sh
```

Dat maakt `dist/Huismus` (de map met `Huismus.exe`) en de installer
`dist/Huismus-<versie>-windows.exe`. Pango gaat mee; de computer waarop je
installeert heeft geen MSYS2 nodig. Staat MSYS2 ergens anders dan `C:\msys64`,
zet dan `PANGO_BIN` op zijn map `ucrt64\bin`. Controleren gaat net als op de Mac:
`HUISMUS_DATA_DIR=... dist/Huismus/Huismus.exe --check`.

Vanuit de broncode, zonder in te pakken:

```bash
uv run --group desktop python -m desktop
```

## De eerste keer openen

De app en de installer zijn niet ondertekend (besluit van 2026-10-27: een
hobbyproject), alleen ad hoc. Wat een gebruiker de eerste keer ziet en
kiest ("Toch openen", SmartScreen) staat in
[`docs/hulp/desktop-app.nl.md`](hulp/desktop-app.nl.md). Een app die je zelf
bouwde heeft dat niet nodig.

## Hoe het gebouwd is

Nog geen definitieve keuze (SPEC.md sectie 13); dit is wat het prototype
gebruikt:

- **PyInstaller** pakt Python, de afhankelijkheden en Pango in
  (`desktop/huismus.spec`). Django vindt zijn apps, templates en migraties op
  naam; die staan daarom met de hand in het recept.
- **pywebview** geeft het venster: WKWebView, de webview van macOS zelf
  (`desktop/app.py`). Twee dingen doet Huismus daar anders dan pywebview
  (`desktop/webkit.py`): een PDF om te downloaden gaat naar een
  bewaarvenster, en een link of formulier met `target="_blank"` (zoals
  "Voorbeeld-pdf") opent in een tweede venster van de app. Op Windows is het
  WebView2; daar gaat een download al naar een bewaarvenster, en
  `desktop/webview2.py` laat `target="_blank"` naar Huismus zelf over aan
  WebView2, dat er een tweede venster met zijn pdf-viewer voor opent.
- **Pango op Windows** komt uit MSYS2 (UCRT64). WeasyPrint zoekt zijn
  bibliotheken op naam; de app laat die naam alleen in zijn eigen map zoeken,
  net als op de Mac (`_use_the_apps_own_pango` in `desktop/app.py`).
- **Inno Setup** maakt van de map met `Huismus.exe` de installer
  (`desktop/huismus.iss`): per gebruiker, Nederlands of Engels zoals Windows.
- **De WSGI-server uit de standaardbibliotheek**, een thread per verzoek
  (`desktop/server.py`), zonder gunicorn: het venster is de enige bezoeker.
- **Ad hoc ondertekend**, zonder hardened runtime (`scripts/build-mac.sh`):
  daarmee laadt macOS alleen bibliotheken van hetzelfde team, en ad hoc heeft
  geen team.

Bekend en nog niet gedaan: Intel-Macs, macOS ouder dan 14, Windows op ARM
als eigen versie, en de downloadpagina.

## Een release maken

Een versie-tag bouwt beide apps in GitHub Actions
(`.github/workflows/release.yml`, jobs `macos-app` en `windows-app`), naast
het Docker-image:

1. Zet de nieuwe versie in `pyproject.toml` en zet die op `main`.
2. Tag die commit met precies `v` plus die versie (`git tag v1.4.0 && git push
   origin v1.4.0`). Wijkt de tag af van `pyproject.toml`, dan stopt de bouw:
   de bijgewerkte app zou zichzelf anders als oud zien en dezelfde update
   steeds opnieuw aanbieden.
3. Op een Apple Silicon-runner (`macos-14`) installeert de job Pango uit
   Homebrew, draait `scripts/build-mac.sh` en daarna `Huismus --check` op een
   lege administratie. Faalt die controle, dan komt er niets online.
4. Op een Windows-runner (`windows-2022`) installeert de job Pango uit MSYS2
   en Inno Setup, draait `scripts/build-windows.sh`, installeert de installer
   stil en draait `Huismus.exe --check` op de geïnstalleerde app, op een lege
   administratie.
5. Pas als beide gelukt zijn, zet de job `publish` `Huismus-<versie>-macos.dmg`
   en `Huismus-<versie>-windows.exe` op de GitHub-release van de tag.
   Bestaat die release nog niet, dan maakt hij hem als concept (met de
   release-notities die GitHub uit de PR-titels maakt), voegt de bestanden
   toe en publiceert hem pas daarna. Bestaat hij al (ook als concept, van een
   eerdere poging), dan vervangt hij de bestanden en publiceert hem. De app
   slaat concepten over, dus ziet nooit een release zonder zijn bestand.

Een proefbouw zonder release: start de workflow "Release" met de hand (Actions
→ Release → Run workflow). Dan bouwt en controleert alleen de Windows-job; de
installer staat 3 dagen als bijlage bij de run, en er komt niets online.

De Pango-pakketten van Homebrew op die runner zijn gebouwd voor macOS 14
(Sonoma). De app vraagt daarom minstens macOS 14 (`LSMinimumSystemVersion` in
`desktop/huismus.spec`); op een oudere macOS zegt macOS dat hij daar niet
werkt. Elke Apple Silicon-Mac kan macOS 14 draaien.

Een release kost op een privé-repo ongeveer 160 tot 210 minuten van het
gratis Actions-tegoed: Mac-minuten tellen tien keer, Windows-minuten twee
keer. Een proefbouw op Windows ongeveer 60. Zolang de repo privé is,
kan de app de releaselijst niet zonder inloggen lezen; updates werken dus pas
na de openbare release (SPEC.md sectie 11).
