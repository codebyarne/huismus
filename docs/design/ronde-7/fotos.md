# Ronde 7: foto's voor de site

Vijf foto's van zzp'ers aan het werk. Eerst proberen met een beeldgenerator. De foto's
blijven alleen als ze echt overkomen. Haalt één foto de toets niet, dan gaat de hele set
naar gratis stockfoto's (Unsplash of Pexels), zodat de stijl één geheel blijft.

De mensen op de foto's zijn niemand: geen naam, geen citaat, en nergens staat dat het
gebruikers van Huismus zijn.

## Gekozen: foto's van een beeldgenerator

De vijf foto's in `fotos/` zijn op 18 november 2026 gemaakt met een beeldgenerator en
door de eigenaar goedgekeurd. Ze haalden de toets hieronder. Er is geen stock gebruikt.

| Plek | Bestand | Wat erop staat |
|---|---|---|
| 1. Kop | `fotos/foto-1-kop.jpg` | Meubelmaker schuurt een stoel, Huismus open op de laptop op de werkbank |
| 2. Overstappen | `fotos/foto-2-overstappen.jpg` | Iemand aan de keukentafel met Huismus open en een stapel papieren |
| 3. Voor wie | `fotos/foto-3-fotograaf.jpg` | Fotograaf stelt in een park haar camera in |
| 4. Voor wie | `fotos/foto-4-hovenier.jpg` | Hovenier legt een schop in zijn bus |
| 5. Voor wie | `fotos/foto-5-schrijver.jpg` | Tekstschrijver aan een bureau bij het raam |

Wat er na het maken aan gedaan is:

- Foto 1 en 2: een echte schermafdruk van Huismus op het lege laptopscherm gezet. De
  versies met leeg scherm staan ernaast (`-leeg-scherm.jpg`), voor als er een ander
  scherm op moet. Op foto 2 staat nu de facturenlijst; daar hoort het importscherm.
- Foto 3: de verzonnen lettertjes op de camera vervaagd.
- Foto 5: een filmrandje weggesneden.
- Foto 3 en 4 zijn een paar keer opnieuw gemaakt. Wat afviel: een merknaam op de camera,
  verzonnen letters op een winkelruit, een wazig gemaakt gezicht, en een foto die
  scherper en kleuriger was dan de rest.

## De toets

Een foto mag blijven als dit allemaal klopt:

- Handen, vingers en gereedschap kloppen, ook als je inzoomt.
- De huid heeft poriën en rimpels. Geen gladde reclamehuid.
- Er staat geen leesbare tekst en geen logo in beeld. Een laptopscherm is leeg en egaal, of het staat van de camera af.
- Het licht komt van één kant, zoals uit een raam of een lamp. Geen studiolicht.
- Er ligt rommel: zaagsel, kabels, een koffiekop. Niets is opgeruimd voor de foto.
- De vijf foto's lijken van dezelfde fotograaf: zelfde kleur, zelfde korrel.
- Laat de foto zien aan iemand die niet weet hoe hij gemaakt is. Twijfelt die, dan valt hij af.

## Voor elke beeldprompt

Zet dit achter elke prompt hieronder:

```text
Documentary photograph, natural window light, 35mm lens, slight film grain, muted warm
colours with a hint of teal, shallow depth of field, candid moment, the person is busy and
does not look at the camera, ordinary Dutch setting, slightly messy, no text, no logos.
```

Bij foto 3 en 4 hielp het om dit er nog achter te zetten:

```text
Shot on 35mm colour negative film on a dull overcast autumn day: soft flat light, muted
desaturated colours, visible film grain. The photograph fills the whole frame edge to
edge, no border. All faces are sharp and natural, nothing is blurred out.
```

## De vijf foto's

| Plek | Verhouding | Beeldprompt | Zoektermen voor stock |
|---|---|---|---|
| 1. Kop | 5:2, liggend (gemaakt als 21:9 en bijgesneden) | `A woman in her forties, furniture maker, sanding a chair leg in a small workshop, an open laptop on the workbench beside her with the screen facing the camera, the screen plain light grey and evenly lit, a coffee mug, sawdust in the air. Wide composition, she is on the left, the laptop on the right.` | woodworker workshop woman, furniture maker candid |
| 2. Overstappen | 3:2 | `A man in his thirties at a kitchen table in the evening, looking at an open laptop seen over his shoulder, the screen facing the camera, plain light grey and evenly lit, a folder of papers and receipts next to him, warm lamp light.` | freelancer kitchen table evening laptop, paperwork at home |
| 3. Voor wie | 1:1 | `A woman in her late twenties, photographer, kneeling in a Dutch city park in autumn on a grey day, looking down at the back of her plain black camera and adjusting it, a worn canvas camera bag open in the grass. No brand names or lettering on the camera or bag, no signs in the background.` | photographer outdoors adjusting camera candid |
| 4. Voor wie | 1:1 | `A man in his fifties, gardener, seen from the side, sliding a spade into the open back of a plain white van parked on a Dutch residential street with clipped hedges and brick terraced houses, a rake and bags of soil already inside, work gloves on, a worn dark green work jacket and muddy trousers, his weathered face in profile clearly visible, fallen leaves on the wet pavement. No number plate, no lettering on the van or on the bags.` | gardener van tools, landscaper loading van |
| 5. Voor wie | 1:1 | `A woman in her sixties writing at a desk by a window, notebook and reading glasses, bookshelf behind her, rainy light.` | writer desk window notebook, working from home older woman |

## Huismus op het laptopscherm

Op foto 1 en 2 staat Huismus open op de laptop. Een beeldgenerator verzint een scherm, en
een stockfoto toont een ander programma. Daarom:

- Maak of kies de foto met een leeg, egaal laptopscherm dat naar de camera staat.
- Zet er daarna een echte schermafdruk uit `docs/site/` op, in het perspectief van het
  scherm: `overzicht` op foto 1, `importeren` op foto 2. Lichte modus, met de verzonnen
  administratie.
- Maak de schermafdruk iets matter en voeg wat glans toe, zodat hij bij het licht van de
  foto past.
- Bij stock: zoek met "blank screen" of "mockup" erbij, bijvoorbeeld "laptop blank screen
  workshop".

Foto 3, 4 en 5 hebben geen scherm in beeld.

## Als het stock wordt

- Kies uit één of twee fotografen, zodat de kleuren bij elkaar passen.
- Lees de licentie van de foto zelf en bewaar de link naar de bron in deze map.
- Geen foto waarop een merk, een kenteken of een herkenbaar adres staat.
