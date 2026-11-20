# Overstappen uit Excel

Houd je je facturen en uitgaven bij in Excel of Numbers? Dan laat je je
werkbladen door een AI-assistent omzetten naar het sjabloon van Huismus en
importeer je ze. Huismus doet eerst een proefdraai en slaat pas iets op als
jij dat kiest.

## Je bestanden klaarzetten

Zoek bij elkaar wat je hebt: je werkbladen met facturen, klanten en
uitgaven, de pdf's van je facturen en je bonnetjes. Hoe je werkbladen eruit
zien, maakt niet uit. Wel moet er per factuur een nummer, een datum, een
klant en een bedrag in staan.

Liever zelf invullen? Dat kan ook: zie [Importeren uit een ander pakket of
Excel](importeren.nl.md#het-sjabloon-invullen).

## Omzetten met een AI-assistent

1. Open in Huismus **Importeren**, kies **Uit een ander pakket of Excel** en
   klik op **Sjabloon downloaden**.
2. Open een AI-assistent, zoals ChatGPT of Claude. Dit is een gewone chat
   waarin je bestanden zet, niet de koppeling bij
   [AI-assistenten](ai-assistenten.nl.md).
3. Zet het sjabloon en al je bestanden uit Excel in de chat. Kopieer de
   opdracht hieronder en plak hem erbij.

Je laat die dienst dan wel je administratie lezen.

```text
Ik stap over van Excel naar Huismus. Zet mijn gegevens om naar het importsjabloon van Huismus.

Wat ik je geef:
- het importsjabloon van Huismus (een zip);
- mijn eigen werkbladen uit Excel of Numbers, en misschien de pdf's van mijn facturen en mijn bonnetjes.

Waar het hoort:
- Kijk eerst welke werkbladen en kolommen ik heb, en zeg me hoe je ze op het sjabloon wilt zetten. Begin pas als ik het goed vind.
- Staan mijn facturen alleen als totaal in een werkblad, zonder regels, maak dan één regel per factuur met het bedrag per btw-tarief.
- Een pdf van een factuur → de map voor pdf's van facturen.

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
omzet bij **Rapporten › Jaaroverzicht** met je eigen werkbladen.
