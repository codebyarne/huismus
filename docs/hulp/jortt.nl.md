# Overstappen uit Jortt

Heb je je administratie in Jortt? Dan haal je je gegevens eruit, laat je
ze door een AI-assistent omzetten naar het sjabloon van Huismus en
importeer je ze. Huismus doet eerst een proefdraai en slaat pas iets op als
jij dat kiest.

## Je gegevens uit Jortt halen

Jortt heeft geen export met alles erin. Je haalt per onderdeel een bestand
op:

1. **Klanten:** open **Klanten** en klik op **Download CSV**. [Zo beschrijft
   Jortt het in zijn hulp](https://www.jortt.nl/factuur-maken/factuur-maken-uitleg/klanten-aanmaken-en-beheren/).
2. **Facturen:** open **Facturen en offertes**, **Facturen**. Kies een
   periode, bijvoorbeeld een jaar, en klik op het download-icoon. Je krijgt
   een zip met een pdf per factuur. Doe dat voor elk jaar. [Zo beschrijft
   Jortt het in zijn hulp](https://www.jortt.nl/uitleg/faq/exportmogelijkheden-in-jortt/).
3. **Offertes, inkoopfacturen en bonnetjes:** die exporteert Jortt alleen via
   de koppeling met Dropbox. [Zo beschrijft Jortt het in zijn
   hulp](https://www.jortt.nl/uitleg/faq/exportmogelijkheden-in-jortt/).
4. **Auditfile:** open **Boekhoudbot** en kies **Maak voor mij een
   auditfile**, voor elk jaar. Daarmee controleert de assistent of er een
   factuur ontbreekt. [Zo beschrijft Jortt het in zijn hulp](https://www.jortt.nl/boekhouder/boekhouder-uitleg/auditfile/).

Je facturen krijg je alleen als pdf. De assistent leest elke regel uit de
pdf. Dat is veel werk, dus doe het per jaar als je veel facturen hebt. De
proefdraai rekent daarna elk totaal na. De pdf's gaan mee: in Huismus staat
bij elke factuur de pdf die je klant kreeg.

## Omzetten met een AI-assistent

1. Open in Huismus **Importeren**, kies **Uit een ander pakket of Excel** en
   klik op **Sjabloon downloaden**.
2. Open een AI-assistent, zoals ChatGPT of Claude. Dit is een gewone chat
   waarin je bestanden zet, niet de koppeling bij
   [AI-assistenten](ai-assistenten.nl.md).
3. Zet het sjabloon en al je bestanden uit Jortt in de chat. Kopieer de
   opdracht hieronder en plak hem erbij.

Je laat die dienst dan wel je administratie lezen.

```text
Ik stap over van Jortt naar Huismus. Zet mijn gegevens om naar het importsjabloon van Huismus.

Wat ik je geef:
- het importsjabloon van Huismus (een zip);
- mijn export uit Jortt: het klantenbestand (CSV), een zip met de pdf's van mijn facturen per jaar, en de auditfile. Misschien ook offertes, inkoopfacturen en bonnetjes uit Dropbox.

Waar het hoort:
- Het klantenbestand van Jortt → klanten.csv.
- Elke pdf van een factuur of creditnota → een rij in facturen.csv en de regels in regels.csv, zoals ze op de pdf staan. De pdf zelf → de map voor pdf's van facturen of creditnota's.
- Offertes → offertes.csv en regels.csv; inkoopfacturen en bonnetjes → uitgaven.csv, uitgaveregels.csv en de map voor bonnetjes.
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
omzet bij **Rapporten › Jaaroverzicht** met die in Jortt.

## Als je opzegt

Volgens Jortt houd je je gegevens als je teruggaat naar jortt Starter. De boekhouding, de auditfile en de koppeling met Dropbox werken
dan niet meer, dus die exporteer je eerst. [Zo beschrijft Jortt het in zijn
hulp](https://www.jortt.nl/boekhouder/boekhouder-uitleg/weggaan-bij-jortt/).
