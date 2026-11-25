# Ronde 9: een mens in de kop van de site

De kop van de homepage krijgt een mens: de man aan de keukentafel, met Huismus open op
de laptop, eerst als foto en daarna in een korte stille lus. Voorbeeld: de kop van
shine.co/nl (een kaart met ronde hoeken over de hele breedte, een video zonder geluid in
een lus).

Eerst was het de meubelmaker uit de werkplaats. De eigenaar koos op 25 november voor de
keukentafel: een laptop in een stoffige werkplaats klopt niet, en in een video werd het
schuurstof sneeuw. De meubelmaker staat nu weer in "Voor wie".

## Wat er op de site staat

- Kop: een petrol kaart met ronde hoeken over de breedte van de pagina. Links het
  labeltje, de kop, de zin eronder en de downloadknoppen, wit op petrol. Rechts de foto,
  die naar links in het petrol overloopt. De tekst staat dus nooit op het beeld, en de
  foto blijft helder. Rechtsonder op de foto één kaartje uit de app, met verzonnen
  gegevens: "Factuur 2026-014 · Betaald · € 890,00".
- Onder 900 px (tablet, telefoon): de foto boven, de tekst eronder op petrol, in dezelfde
  kaart. Het kaartje valt weg.
- Direct onder de kaart: "Eerst rondkijken?" en de vier vinkjes. Daaronder het overzicht.
- "Voor wie" toont de vier andere foto's; de man aan de keukentafel staat alleen in de kop.

## De video maken

De eigenaar maakt de clip met een videogenerator (bijvoorbeeld Kling), met hetzelfde
begin- en eindbeeld, zodat de lus naadloos is: de goedgekeurde foto met het lege
laptopscherm, `docs/design/ronde-7/fotos/foto-2-overstappen-leeg-scherm.jpg`, in 16:9
gesneden. Het scherm blijft leeg; daarna komt er een echte schermafdruk van Huismus op,
in het Nederlands en in het Engels, net als bij de foto. Daarom staat de camera stil.

Prompt:

```text
Use this image as the first and the last frame. Locked-off camera on a tripod: no camera
movement, no zoom, no pan. The man types slowly on the laptop, pauses, glances down at
the papers beside him and lightly touches the top sheet, then looks back at the screen
and types again. Small, calm, natural movements; he breathes, his shoulders move a
little. The desk lamp glows steadily, the net curtains stir very slightly in the window
light. Everything else stays exactly where it is: the laptop and its plain light grey
screen, the lamp, the papers, the kitchen. Nothing new appears, no text, no logos, he
does not look at the camera. Documentary, natural evening light, 35mm film grain, same
colours as the photo.
```

Negatieve prompt, als de generator die heeft: `camera movement, text on screen, dust,
particles, extra hands`.

`scripts/kop_video_veo.py` doet hetzelfde met Veo via de Gemini-API, met de sleutel van
de eigenaar; op 25 november gaf die sleutel geen videomodel.

## De toets

Dezelfde als voor de foto's (`ronde-7/fotos.md`), plus:

- Handen en vingers op het toetsenbord en het papier blijven kloppen, in elk beeld.
- Het laptopscherm, de lamp en de tafel bewegen niet.
- Geen stof, deeltjes of iets anders dat door de lucht zweeft.
- De lus springt niet zichtbaar.
- Haalt de clip de toets niet: opnieuw, of de kop blijft de foto.

## De video op de site (stap 2)

- Zonder geluid, in een lus (`muted autoplay loop playsinline`), met de foto als
  stilstaand beeld eronder. Elke taal heeft een eigen clip, met het Nederlandse of
  Engelse scherm op de laptop.
- Geen JavaScript, zoals de rest van de site: de video kiest met `<source media="…">`. Bij
  "minder beweging" laadt er geen video en staat de foto er. Een knopje in de hoek van de
  kaart (een schakelaar in CSS) verbergt de video en toont de foto (WCAG 2.2.2), op elke
  breedte.
- Laadt de video niet, dan blijft de foto staan, zonder foutmelding.
- Computer: hooguit 1,5 MB, H.264, zonder geluidsspoor. Telefoon: een uitsnede voor het
  vlak boven de tekst, hooguit ~0,6 MB. "Data besparen" valt zonder script niet te zien
  en doet niet mee.

## In twee stappen

1. De kaart met de foto. Besluit `product-owner` 2026-11-25.
2. De video, zodra de clip de toets haalt. Ook die gaat eerst langs de eigenaar.
