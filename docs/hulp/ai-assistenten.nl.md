# AI-assistenten

Je kunt een AI-assistent, zoals ChatGPT, Claude of Gemini, met je
administratie laten werken. De assistent kan dan lezen wat erin staat,
dingen bijwerken en, als jij het goedkeurt, uitgeven, mailen en boeken. Je werkt in
de app van de assistent. In Huismus koppel je hem alleen.

## Wat een assistent kan

- **Lezen:** het overzicht (omzet dit jaar, je grens voor de kleineondernemersregeling (KOR), wat openstaat en
  wat te laat is), en wat op je wacht, zoals onder Te doen. Facturen,
  creditnota's en offertes zoeken en openen, ook als pdf. Klanten zoeken, de
  uitgaven per jaar, je categorieën, wat onder Bank staat, het jaaroverzicht
  en de btw-aangifte van een kwartaal, maand of jaar, met wat niet meegeteld
  is. Van je instellingen ziet hij alleen wat hij nodig heeft: of de KOR aan
  staat, je standaardtaal, je betaaltermijn en het volgende nummer. Je
  adres, KvK-nummer, IBAN, wachtwoorden en sleutels ziet hij niet, en ook
  mailteksten en het maillog niet.
- **Concepten maken:** een concept voor een factuur of offerte maken en
  wijzigen, een kopie van een factuur of offerte als nieuw concept, een
  offerte omzetten naar een conceptfactuur, en een concept voor een
  creditnota bij een uitgegeven factuur.
- **Klanten:** een klant toevoegen, wijzigen en archiveren. Contactpersonen
  beheer je zelf in Huismus. Een uitgegeven document houdt de gegevens die
  erop stonden.
- **Uitgaven en categorieën:** een uitgave toevoegen of wijzigen, met het
  bedrag dat je betaald hebt. Een categorie die er nog niet is, maakt hij
  erbij. Een uitgave die de assistent maakte of wijzigde, staat bij
  Nakijken tot jij zegt dat hij klopt. Hij kan ook categorieën toevoegen en
  hernoemen.
- **Bonnetjes verwerken:** je assistent leest de bonnetjes zonder uitgave en
  maakt van elk bonnetje een uitgave, of hangt het aan een uitgave die er
  al is. Andere bijlagen ziet hij niet. Wil je dat Huismus dit zelf doet,
  zonder dat je het vraagt? Zie [Bonnetjes lezen](bonnetjes.nl.md#bonnetjes-lezen).
- **Bank:** een regel overslaan en weer terugzetten.
- **Met jouw toestemming:** wat niet terug kan of naar buiten gaat. Dat is
  een factuur of creditnota uitgeven, een offerte verzenden, een document
  mailen, een herinnering sturen voor een factuur die te laat is, een
  betaling registreren, een offerte beantwoorden, een concept, uitgave of
  categorie verwijderen, "Toch bewerken" en dat ongedaan maken, en op de
  bank een voorstel bevestigen, een regel boeken of een boeking
  terugdraaien. De assistent krijgt eerst een samenvatting om je te laten
  zien, zoals de klant, het bedrag en het nummer, of wat er openstaat na
  een betaling. Daarna vraagt de app van de assistent om je toestemming,
  met een knop die alleen jij kunt indrukken. Kies je daar "altijd
  toestaan", dan vraagt de app het niet meer. Huismus kan dat niet zien.

Wat de assistent leest, gaat naar het bedrijf achter die assistent (OpenAI,
Google of Anthropic). Huismus zelf wordt daarvoor niet bereikbaar vanaf
internet, behalve als je zelf een tunnel opzet.

## De Claude-app

Werk je met de Huismus-app op een Mac of Windows-computer, dan koppel je de
Claude-app met één knop:

1. Open in Huismus **Instellingen → AI-assistenten** en kies **Koppel met
   Claude**.
2. De Claude-app opent en vraagt of je Huismus wilt installeren. Bevestig
   dat.
3. Vraag Claude iets over je administratie, bijvoorbeeld: "Welke facturen
   staan nog open?"

Staat de Claude-app nog niet op je computer, dan zegt Huismus dat. Download
hem op [claude.ai/download](https://claude.ai/download) en kies daarna
opnieuw **Koppel met Claude**.

Claude kan alleen bij Huismus zolang het venster van Huismus open is. Is het
dicht, dan zegt Claude dat Huismus niet open is. Kies je **Nieuwe sleutel**
of **Ontkoppelen**, dan kan de Claude-app er ook niet meer bij. Opnieuw
koppelen is weer **Koppel met Claude**.

Draait Huismus op een Raspberry Pi of in Docker, dan is deze knop er niet.
Gebruik dan Claude Code, hieronder.

## Koppelen

1. Open in Huismus **Instellingen → AI-assistenten** en kies bij Adres en
   sleutel **Koppelen**. Huismus maakt een geheime sleutel en laat het adres
   en de sleutel zien. De sleutel staat als puntjes in beeld. Met **Toon**
   zie je hem, met **Kopiëren** kopieer je hem ook zonder hem te tonen.
2. Geef de assistent het adres en de sleutel. Hoe dat gaat, staat hieronder
   per assistent. De sleutel gaat mee als `Authorization: Bearer <sleutel>`.
3. Zodra de assistent iets heeft gevraagd, staat er **Gekoppeld**.

Alle assistenten die het adres gebruiken, delen één sleutel. Kies je
**Nieuwe sleutel** of **Ontkoppelen**, dan werkt de oude sleutel voor
niemand meer. De sleutel gaat niet mee in een back-up. Zet je een back-up
terug op een andere computer, dan koppel je opnieuw. Meer daarover lees je
bij [Naar een nieuwe computer](nieuwe-computer.nl.md).

## Welk adres je gebruikt

Op de pagina AI-assistenten staat het adres waarop je Huismus nu open hebt,
met `/mcp` erachter. In de desktop-app is dat `http://127.0.0.1:8765/mcp`.
Was poort 8765 bezet toen de app startte, dan gebruikt hij een andere poort,
en die staat dan op de pagina. Een assistent bereikt de desktop-app alleen
zolang het venster open is.

Draait Huismus in Docker, dan gebruikt een programma op dezelfde computer
`http://127.0.0.1:<poort>/mcp`, met de poort die je bij `docker run -p` hebt
opengezet. Zet `127.0.0.1` dan ook in `ALLOWED_HOSTS`, bijvoorbeeld
`-e ALLOWED_HOSTS=huismus.local,127.0.0.1`. Anders weigert Huismus het
verzoek.

## ChatGPT

ChatGPT kan niet zelf bij een adres op je eigen computer of Pi. Dat lukt wel
via de tunnel van OpenAI (Secure MCP Tunnel): een programma van OpenAI dat
je naast Huismus draait. Huismus levert het niet mee. Je haalt het, met de
uitleg, bij OpenAI. Geef het tunnelprogramma het adres en de sleutel. Of en
wanneer ChatGPT om toestemming vraagt, bepaalt OpenAI.

## Claude Code

```
claude mcp add --transport http huismus http://127.0.0.1:8765/mcp \
  --header "Authorization: Bearer <sleutel>"
```

Claude Code vraagt om toestemming voordat het een actie van Huismus
gebruikt, behalve als je die actie al eerder hebt toegestaan.

## Gemini CLI

Zet dit in `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "huismus": {
      "httpUrl": "http://127.0.0.1:8765/mcp",
      "headers": { "Authorization": "Bearer <sleutel>" }
    }
  }
}
```

De Gemini-app kan in Nederland nog niet met eigen koppelingen werken.
