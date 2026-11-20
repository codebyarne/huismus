# Overstappen uit e-Boekhouden.nl

Heb je je administratie in e-Boekhouden.nl? Dan haal je je gegevens
eruit, laat je ze door een AI-assistent omzetten naar het sjabloon van
Huismus en importeer je ze. Huismus doet eerst een proefdraai en slaat pas
iets op als jij dat kiest.

## Je gegevens uit e-Boekhouden.nl halen

e-Boekhouden.nl heeft geen export met alles erin. Dit beschrijft het in zijn
hulp:

1. **Klanten:** open **Relaties**, kies **Zoeken**, klik op **zoeken** en dan
   op het Excel-icoon. [Zo beschrijft e-Boekhouden.nl het in zijn
   hulp](https://cdn.e-boekhouden.nl/handleiding/Handleiding_Relaties.pdf).
2. **Facturen:** open **Factureren**, **Facturen**, **Overzicht**. Per factuur
   sla je de pdf op met het printer-icoon. [Zo beschrijft e-Boekhouden.nl het
   in zijn hulp](https://cdn.e-boekhouden.nl/handleiding/Handleiding_Factureren.pdf).
3. **Auditfile:** open **Beheer**, **Exporteren**, **XML-Auditfile**. Daarmee
   controleert de assistent of er een factuur ontbreekt. [Zo beschrijft
   e-Boekhouden.nl het in zijn hulp](https://www.e-boekhouden.nl/veelgestelde-vragen).

Een export van factuurregels, offertes, uitgaven of je bijlagen staat niet in
de openbare hulp van e-Boekhouden.nl. Je facturen heb je dan alleen als pdf.
De assistent leest elke regel uit de pdf. Dat is veel werk, dus doe het per
jaar als je veel facturen hebt. De proefdraai rekent daarna elk totaal na.

Sla je de pdf's niet op, dan maakt Huismus ze zelf, met je bedrijfsgegevens
van nu. Bewaar daarom de pdf's die je klanten kregen ook zelf.

## Omzetten met een AI-assistent

1. Open in Huismus **Importeren**, kies **Uit een ander pakket of Excel** en
   klik op **Sjabloon downloaden**.
2. Open een AI-assistent, zoals ChatGPT of Claude. Dit is een gewone chat
   waarin je bestanden zet, niet de koppeling bij
   [AI-assistenten](ai-assistenten.nl.md).
3. Zet het sjabloon en al je bestanden uit e-Boekhouden.nl in de chat. Kopieer de
   opdracht hieronder en plak hem erbij.

Je laat die dienst dan wel je administratie lezen.

```text
Ik stap over van e-Boekhouden.nl naar Huismus. Zet mijn gegevens om naar het importsjabloon van Huismus.

Wat ik je geef:
- het importsjabloon van Huismus (een zip);
- mijn export uit e-Boekhouden.nl: de relaties als Excel, de pdf's van mijn facturen, en de XML-auditfile.

Waar het hoort:
- Relaties aan wie ik factureer → klanten.csv.
- Elke pdf van een factuur of creditnota → een rij in facturen.csv en de regels in regels.csv, zoals ze op de pdf staan. De pdf zelf → de map voor pdf's van facturen of creditnota's.
- Uitgaven neem je alleen over als ik ze je los geef.
- De auditfile gebruik je alleen om te controleren of er een factuur ontbreekt of een totaal afwijkt.

Zo vul je het sjabloon:
- Lees eerst LEESMIJ.txt in het sjabloon. Schrijf bedragen, datums en mapnamen zoals daar staat.
- Laat de eerste rij met kolomnamen van elk bestand precies zoals hij is. Vervang de voorbeeldrij door mijn gegevens.
- Verzin niets. Staat iets niet in mijn bestanden, laat de cel dan leeg. Weet je niet welke kolom bij welke hoort, vraag het me eerst.
- Neem bedragen over zoals ze in mijn bestanden staan, tot op de cent. Reken geen totalen opnieuw uit en rond niets af.
- Neem factuur- en creditnotanummers precies over. Nummer niets opnieuw.
- Geef elke klant een klantnummer en gebruik dat nummer ook bij zijn facturen en offertes.
- Een creditnota krijgt als soort "creditnota", negatieve bedragen, en in "gecrediteerde factuur" het nummer van de factuur waar hij bij hoort.
- Neem van elke factuurregel het btw-tarief over, ook als het 0 is. Staat er bij een factuurregel geen tarief, vul dan niets in maar vraag het me.
- Neem van elke uitgave het btw-tarief en het btw-bedrag over, ook als ze 0 zijn. Staat er bij een uitgave geen tarief, laat het dan leeg.
- Concepten neem je niet mee.
- Zet de pdf's van facturen en creditnota's in de mappen die LEESMIJ.txt noemt, met het nummer als naam. Bonnetjes gaan in de map bonnetjes, met hun bestandsnaam in de kolom bonnetjes van uitgaven.csv. Meer bonnetjes bij één uitgave scheid je met " | ".
- Geef me alles terug als één zip, met dezelfde bestandsnamen als het sjabloon. Een bestand waar niets in komt, laat je weg.

Zet onder de zip een lijstje: wat je niet kon overnemen, wat je leeg liet en waar mijn bestanden elkaar tegenspreken.
```

Je krijgt een zip terug. Lees het lijstje eronder: wat de assistent niet
kon overnemen, vul je zelf aan of laat je weg.

## Importeren en nakijken

Sleep de zip in Huismus naar het vak bij **Uit een ander pakket of Excel** en
klik op **Proefdraai starten**. De proefdraai slaat niets op. Huismus rekent
elke factuur na, tot op de cent, en zegt wat niet klopt. Wat je dan ziet,
lees je bij [Importeren uit een ander pakket of
Excel](importeren.nl.md#wat-de-proefdraai-laat-zien).

Klopt alles, klik dan op **Nu echt importeren**. Vergelijk daarna per jaar je
omzet bij **Rapporten › Jaaroverzicht** met die in e-Boekhouden.nl.

## Daarna opzeggen

Zeg e-Boekhouden.nl pas op als alles in Huismus staat, je het hebt nagekeken en er een
[back-up](back-ups.nl.md) is. Bewaar ook wat je uit e-Boekhouden.nl hebt gehaald bij
je eigen bestanden.

Volgens e-Boekhouden.nl zeg je op onder **Beheer**. Daarna worden je
gegevens verwijderd, tenzij je een Online Archief neemt. [Zo beschrijft e-Boekhouden.nl het in
zijn hulp](https://www.e-boekhouden.nl/veelgestelde-vragen).
