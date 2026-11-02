# Wat staat waar in docs/

## Voor gebruikers

[`hulp/`](hulp/): de uitleg bij het gebruik, één bestand per onderwerp per
taal (`<onderwerp>.nl.md`, `<onderwerp>.en.md`). Huismus toont dezelfde
bestanden in de app onder **Hulp** (`huismus/core/help.py`), zodat de uitleg hoort
bij de versie die iemand draait. Een nieuw onderwerp: beide bestanden, met
een `# Titel` op de eerste regel, en de naam in `TOPICS` in `huismus/core/help.py`.
Geen verwijzingen naar SPEC.md, broncode of GitHub, en geen tekst over wet of
belasting (`CLAUDE.md`); een link naar een ander onderwerp schrijf je als
`back-ups.nl.md#kopje`. `tests/core/test_help.py` controleert dat.

Dezelfde bestanden staan ook op de Huismus-site (`huismus.arnekrijnsen.com`),
met de downloadpagina erbij. Zelf bekijken:

```
SECRET_KEY=dev DEBUG=true uv run python manage.py build_site _site
python3 -m http.server 8797 -d _site
```

Bij elke release zet `.github/workflows/pages.yml` hem online (pas als de repo
openbaar is). Hoe hij gemaakt wordt: `huismus/core/site.py`.

## Voor beheerders

- [`deploy.md`](deploy.md): Huismus op de Raspberry Pi uitrollen.
- [`tailscale.md`](tailscale.md): Huismus via HTTPS in je tailnet.
- [`backups.md`](backups.md): back-ups met de hand maken en terugzetten.
- [`email.md`](email.md): waar het mailwachtwoord staat, mailen in tests.

## Voor ontwikkelaars

- [`architectuur.md`](architectuur.md): de projectkaart: apps, modellen
  en hun relaties, wat doet welke map, en waar de harde regels wonen.
- [`desktop.md`](desktop.md): hoe de desktop-app werkt, gebouwd en
  uitgebracht wordt.
- [`frontend.md`](frontend.md): hoe de schermen in elkaar zitten.
- [`design/`](design/): het ontwerp en de componentenpagina.
- [`invoice-requirements.md`](invoice-requirements.md): factuureisen met
  bronnen.

De productbesluiten, de backlog, het logboek per mijlpaal en de registratie
bij Google, Microsoft en Dropbox staan in een privé-repo van de maintainer,
`huismus-intern`. Code en commentaar verwijzen ernaar als
`huismus-intern/besluiten.md` met een datum; het besluit zelf staat in
`SPEC.md` als het het ontwerp raakt.
