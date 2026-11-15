---
name: regie
description: Stuurt een paar mijlpalen van Huismus tegelijk aan vanuit één gesprek met de eigenaar. Start per issue uit de wachtrij een lokale sessie met /mijlpaal, ontvangt hun rapporten en bundelt status, vragen en screenshots voor de eigenaar. Gebruik als de eigenaar zegt "/regie", "regie", "werk de wachtrij af" of "doe meerdere dingen tegelijk".
---

# /regie [aantal]

Jij bent de regie. De eigenaar praat alleen met jou, vaak vanaf de telefoon
(Remote Control). Jij bouwt zelf niets: elke mijlpaal draait in een eigen lokale
sessie met `/mijlpaal`, in een eigen worktree. Jij houdt het overzicht, geeft
vragen door en start het volgende werk.

`aantal` is hoeveel mijlpalen er tegelijk lopen. Standaard 3. Meer geeft vooral
botsingen (vertaalbestanden, migratienummers, hetzelfde scherm).

Houd je eigen gesprek dun: lees geen code, geen diffs en geen lange logs. Alles
wat je nodig hebt, staat in de rapporten, op het bord en in de PR-status. Een
volle regie wordt traag, en dan stuurt niemand meer.

## Het rapport van een mijlpaal

Elke sessie die jij start, schrijft haar stand in één bestand per issue:

```
"$(git rev-parse --path-format=absolute --git-common-dir)/regie/<issue>.md"
```

Dat is de map `.git/regie/` van de hoofdmap, die alle worktrees delen. Git volgt
hem nooit, dus er komt niets van in een commit. Screenshots staan ernaast, in
`regie/<issue>/`. Het bestand begint met één regel:

```
#<issue> <STAND>: <één zin in producttaal>
```

`STAND` is een van:

- `BEZIG`: loopt, niets nodig.
- `VRAAG`: wacht op de eigenaar. Daaronder de vraag, het advies en wat de
  sessie intussen doet.
- `FLOW`: een grote wijziging met UI wacht op goedkeuring (`CLAUDE.md`, "Flow
  voorleggen"). Daaronder de stappen, elk met één zin en de paden van de
  screenshots (telefoon en desktop).
- `KLAAR`: gemerged naar `main`. Daaronder wat de gebruiker merkt en de
  besluiten van de PO-agent.
- `VAST`: komt niet verder zonder hulp (poort blijft rood, conflict, iets
  buiten de code). Daaronder wat er mis is.

Dezelfde eerste regel staat bovenaan het laatste bericht van die sessie, zodat
hij ook in de korte melding past die jij van de app krijgt (die wordt na
400 tekens afgekapt). Het bestand is de bron; de melding is de wekker.

## 1. Begin

1. Zet Remote Control voor jezelf aan (`set_remote_control`, `self`), als hij
   nog niet aanstaat.
2. Lees wat er al loopt:
   - de map `.git/regie/` (rapporten van eerdere rondes, ook van een vorige
     regie);
   - je gekoppelde sessies (`list_sessions` met `linked: true`);
   - de open PR's (`gh pr list`);
   - het bord: wat op `In Progress` staat.
   Een issue met een rapport dat niet `KLAAR` is, telt als lopend. Hoort het bij
   een sessie die niet aan jou gekoppeld is (een vorige regie), dan meldt die
   niet aan jou. Lees zijn rapport dan zelf bij elke ronde.
3. Stop zonder iets te starten als er een open issue met het label `pauze` is
   (`CLAUDE.md`, "Backlog: GitHub Issues"). Meld wat er nog loopt.

## 2. Kiezen

Neem van boven naar beneden van het bord, tot er `aantal` lopen:

```
gh project item-list 1 --owner codebyarne --limit 500 --format json --jq '[.items[] | select(.content.type == "Issue" and .status == "Todo" and ((.labels // []) | any(. == "wacht" or . == "idee" or . == "pauze") | not))][0:10][] | "#\(.content.number) \(.title)"'
```

Sla een issue over (het blijft staan, voor de volgende ronde) als het:

- hetzelfde scherm, dezelfde template of view raakt als iets wat al loopt;
- een migratie nodig heeft terwijl een andere lopende mijlpaal er ook een maakt;
- afhangt van een issue dat nog loopt.

Twijfel je, laat het dan wachten. Na elkaar is trager, maar botsen kost meer.
Een release-PR (`chore(release)`) telt niet als mijlpaal en loopt nooit naast
een andere release.

## 3. Starten

Per gekozen issue één sessie met `start_session`:

- `initiation` `user_asked` (de eigenaar vroeg om `/regie`), `context` `fresh`,
  `use_worktree` true, `target` `local`;
- `name` `m-<issue>`, `title` `Mijlpaal #<issue>: <titel>`;
- `permission_mode` gelijk aan die van jou (laat weg om te erven);
- `prompt`, precies zo:

  ```
  /mijlpaal #<issue> <titel>
  Regie: ja
  ```

- `background`: dat deze sessie door de regie is gestart, dat er andere
  mijlpalen naast lopen (noem hun issues en schermen), en dat ze rapporteert
  zoals `/mijlpaal` onder "Onder regie" zegt.

Kijk daarna met `get_session` of de nieuwe sessie Remote Control heeft
(`remoteControlState`). Staat hij uit, zet hem dan aan met `set_remote_control`,
zodat de eigenaar er ook vanaf de telefoon in kan.

## 4. Elke ronde

Je wordt wakker als een sessie een beurt afrondt (een `<side-sessions-event>`)
of als de eigenaar iets zegt. Lees dan de rapporten die veranderd zijn en doe
per stand:

- `BEZIG`: niets. Niet melden, niet porren.
- `VRAAG`: geef de vraag door aan de eigenaar, met het advies van de sessie
  als eerste optie. Bundel vragen die tegelijk binnenkomen in één bericht,
  maar elke vraag apart en met het issue erbij. Antwoordt de eigenaar, stuur
  het antwoord dan met `SendMessage` naar die sessie (`to` is haar
  `local_…`-id), met de woorden van de eigenaar letterlijk erbij.
- `FLOW`: stuur de screenshots op volgorde met `SendUserFile`, elk met de zin
  uit het rapport, en vraag of het zo live mag. Goedgekeurd of niet: geef het
  letterlijk door aan de sessie.
- `KLAAR`: controleer met `gh pr view` dat de PR echt gemerged is. Zo ja: meld
  het in één zin en vul de vrije plek met het volgende issue (stap 2 en 3).
  Een rapport is een bewering, geen bewijs.
- `VAST`: meld het in producttaal, met wat de sessie probeerde en jouw advies.
  Los het niet zelf op in de code.

Sluit elke ronde af met een kort overzicht, één regel per mijlpaal:

```
#201 Bon bij uitgave · BEZIG · bouwt de browsertest
#204 Btw-rapport per kwartaal · VRAAG · zie hierboven
#207 Importeren uit e-Boekhouden · KLAAR · staat op main
```

Een vraag die alleen de PO-agent hoeft te beantwoorden, komt niet bij jou: die
handelt de sessie zelf af. Krijg je er toch een, stuur hem terug met "vraag de
`product-owner`-agent".

## 5. Releases

Mijlpalen onder regie maken geen release. Dat doet de regie, volgens `CLAUDE.md`,
"Releases": op woensdag, als er die week iets anders dan documentatie op `main`
kwam en CI op `main` groen is. Start daarvoor één sessie (`name` `release`,
`prompt` met de release-stappen uit `docs/desktop.md`, "Een release maken"), op
een moment dat geen andere sessie aan het mergen is. Meld de eigenaar welke
versie klaarstaat en wat erin zit, in gewone taal.

## 6. Stoppen en overdragen

- Een `pauze`-issue of een lege wachtrij: start niets nieuws, laat lopende
  mijlpalen afmaken, en meld wanneer de laatste klaar is.
- Na een stuk of tien mijlpalen, of als je merkt dat je traag wordt: zeg tegen
  de eigenaar dat een verse `/regie` kan beginnen. De rapporten in
  `.git/regie/` nemen het over. Sessies van jou blijven aan jou melden, dus de
  nieuwe regie leest hun rapport zelf (stap 1).
- Een `KLAAR`-sessie mag weg. Vraag de eigenaar of je ze mag archiveren
  (`archive_session`), en doe het pas na een ja.
