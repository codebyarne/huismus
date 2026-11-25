# Ronde 9: een video in de kop van de site

De kop van de homepage krijgt een mens: de meubelmaker uit de werkplaats, in een
korte stille lus. Voorbeeld: de kop van shine.co/nl (een kaart met ronde hoeken over de
hele breedte, een video zonder geluid in een lus, de tekst erop).

## De video maken

De eigenaar maakt de clip met een videogenerator, vanaf de goedgekeurde foto met het
lege laptopscherm: `docs/design/ronde-7/fotos/foto-1-kop-leeg-scherm.jpg`. Het scherm
blijft leeg; daarna komt er een echte schermafdruk van Huismus op, in het Nederlands en
in het Engels, net als bij de foto. Daarom staat de camera stil.

Prompt:

```text
Use this photo as the first frame. Locked-off camera on a tripod: no camera movement,
no zoom, no pan. The woman keeps sanding the chair leg with slow, steady strokes; her
hands, arms and shoulders move naturally. Fine sawdust drifts through the window light.
Everything else stays exactly where it is: the laptop and its plain light grey screen,
the mug, the workbench, the tools. Nothing new appears, no text, no logos, she does not
look at the camera. Documentary, natural window light, 35mm film grain, same colours as
the photo. 8 seconds; the last frame should match the first so it can loop.
```

Lever: de beste mp4 die de generator geeft, zo breed mogelijk (de foto is 5:2; 16:9 of
21:9 is goed).

## De toets

Dezelfde als voor de foto's (`ronde-7/fotos.md`), plus:

- Handen en schuurpapier blijven kloppen in elk beeld, ook halverwege.
- Het laptopscherm en de werkbank bewegen niet.
- De lus springt niet zichtbaar.
- Haalt de clip de toets niet: opnieuw, of de kop blijft de foto.

## Wat er op de site staat

- Kop: een kaart met ronde hoeken over de breedte van de pagina. De video staat erin als
  achtergrond, met een donker verloop waar de tekst staat. Daarop het labeltje, de kop,
  de zin eronder en de downloadknoppen. Er zweeft één echt kaartje uit Huismus overheen.
- De video speelt zonder geluid, in een lus (`muted autoplay loop playsinline`), met de
  foto als stilstaand beeld eronder. Elke taal heeft een eigen clip, met het Nederlandse
  of Engelse scherm op de laptop.
- Geen JavaScript, zoals de rest van de site: de video kiest met `<source media="…">`. Bij
  "minder beweging" laadt er geen video en staat de foto er. Een knopje in de hoek van de
  kaart (een schakelaar in CSS) verbergt de video en toont de foto (WCAG 2.2.2).
- Laadt de video niet, dan blijft de foto staan, zonder foutmelding.
- Telefoon: de foto boven, staand bijgesneden op de meubelmaker; de tekst eronder op petrol.
  Ook daar speelt de video, hooguit ~0,6 MB. Computer: hooguit 1,5 MB, H.264, zonder
  geluidsspoor. "Data besparen" valt zonder script niet te zien en doet niet mee.
- Het verloop onder de tekst is zo donker dat wit en de lichte framboos ruim AA halen
  (gemeten op de foto: wit minstens 10 : 1, framboos minstens 5,2 : 1). Meet het opnieuw
  op het lichtste beeld van de clip.
- De meubelmaker staat niet meer bovenaan "Voor wie"; daar staan de vier andere foto's.
- Het grote beeld van het overzicht blijft direct eronder staan.

## In twee stappen

1. De kaart met de foto (deze ronde). Besluit `product-owner` 2026-11-25.
2. De video, zodra de clip de toets haalt. Ook die gaat eerst langs de eigenaar.
