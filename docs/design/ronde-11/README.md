# Ronde 11: Uitleg op de site

Een nieuw onderdeel op mijnhuismus.nl, naast Hulp: pagina's over hoe iets werkt
voor een zzp'er, los van Huismus (issue #308). Zoals in ronde 8 is het ontwerp
de site zelf: `huismus/templates/site/guide_index.html` en `guide_page.html`
met `site.css`, op de tokens van `huismus/core/static/core/huismus.css`. Er
zijn geen nieuwe componenten in `huismus.css`.

- **De lijst** (`/uitleg/`): de regels met een pijl van de hulpindex, zonder
  groepen zolang er weinig pagina's zijn. De inleiding zegt het verschil met
  Hulp.
- **Een pagina:** titel en samenvatting, de uitleg los op de pagina, dan
  "Zo doe je dit in Huismus" als vel met een link naar de hulppagina, dan de
  bronnen klein eronder met de dag waarop ze zijn nagekeken, en de band met de
  downloadknoppen.
- **Menu:** Uitleg tussen Functies en Hulp, ook in de voet.

De site is altijd licht (besluit 2026-11-19), dus er is geen donkere variant.

Bekijken:

```
SECRET_KEY=dev uv run python manage.py build_site /tmp/huismus-site
python3 -m http.server 8791 --directory /tmp/huismus-site
```

en open http://localhost:8791/uitleg/.
