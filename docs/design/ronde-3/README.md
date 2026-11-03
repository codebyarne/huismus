# Designronde 3 (2026-10-28)

> **Referentie, niet de bron**, net als `docs/design/`. De geldende CSS staat in
> `huismus/core/static/core/huismus.css`. Alle voorbeelddata is fictief.

Designs voor wat nog gebouwd wordt, gemaakt als canvas in Claude (privé; de link
staat in `huismus-intern/werkwijze.md`). Dit is een kopie van de
bestanden (`*.dc.html`, één per scherm; `hm.css` zijn de tokens in licht).

| Bestand | Wat | Voor |
|---|---|---|
| `Main.dc.html`, `Instellingen-telefoon.dc.html` | D0: Instellingen als overzicht met een pagina per onderwerp | eigen mijlpaal, vóór M11 |
| `Desktop-opstarten.dc.html`, `Desktop-bijwerken.dc.html`, `Download.dc.html` | D3: starten, niet starten, bijwerken, downloadpagina | M11 |
| `Backups.dc.html`, `Backup-melding.dc.html`, `Terugzetten.dc.html` | D4: back-ups via een map | M11 |
| `AI-assistenten.dc.html`, `AI-chat.dc.html` | D5: AI-assistenten (MCP): alleen koppelen; het gebruik zit in de app van de assistent (`AI-chat` is uitleg) | AI-koppeling (ook op de Pi) |
| `Beveiliging.dc.html` | D6: wachtwoord in de desktop-app | M11 |
| `Review.dc.html` | D7–D10: gebouwde schermen nagelopen | kleine fixes |

Keuring door de PO-agent en wat er is aangepast: `huismus-intern/besluiten.md`
(2026-10-28, designronde 3).

Bouwnoten van de PO-agent:
- `hm.css` gebruikt `.banner-*` en `.pill-*` als schets. Bouw met wat
  `huismus.css` heeft: `.flash-*` en `.hint-banner` voor meldingen, `.sheet`
  voor de onderste dialoog, `.spinner` en `.progress`. Een neutrale pill alleen
  toevoegen met bestaande tokens.
- Elk scherm krijgt Engelse teksten.
- De pagina Updates heeft geen apart design: één schakelaar "Zoek naar nieuwe
  versies" plus de huidige versie.
- Downloadpagina: knopnamen van macOS/Windows en de systeemeisen pas vastzetten
  na schermafdrukken van de eigenaar en de Intel-beslissing (SPEC.md §13).
