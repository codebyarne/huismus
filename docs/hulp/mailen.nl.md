# Mailen

Je mailt een factuur, creditnota of offerte rechtstreeks vanuit Huismus, met
de pdf als bijlage. Dat kan zodra de factuur of creditnota is uitgegeven, of
de offerte verzonden. De mail gaat via je eigen Gmail of via de mailserver
van je eigen domein. Er zit geen andere dienst tussen.

Mailen verandert niets aan het document. Elke poging komt op de tijdlijn van
het document, ook een mislukte, met de foutmelding erbij.

## Mailen instellen

Je stelt alles in bij **Instellingen → Mailen**. Kies eerst waarlangs je
mailt: **Gmail** of **Anders** (de mailserver van je eigen domein). Daarna
vul je de gegevens in, zoals hieronder per keuze staat.

Huismus laat je wachtwoord nooit zien, alleen of er een is. Laat je het veld
leeg bij opslaan, dan houdt Huismus het wachtwoord dat er al stond. Kies je
bij "Mailen via" voor **Niet ingesteld**, dan staat mailen uit en wist
Huismus het wachtwoord.

Je mailwachtwoord gaat niet mee in een back-up. Anders kan iedereen met een
kopie van je back-up in je mailbox komen. Zet je een back-up terug op een
andere computer, dan vul je het wachtwoord daar opnieuw in.

## Gmail

Gmail accepteert je gewone wachtwoord niet van een programma als Huismus. Je
maakt daarom een **app-wachtwoord**: een apart wachtwoord van 16 tekens,
alleen voor Huismus. Je kunt het altijd weer intrekken.

1. Zet tweestapsverificatie aan voor je Google-account, als dat nog niet aan
   staat: <https://myaccount.google.com/signinoptions/two-step-verification>.
   Zonder tweestapsverificatie geeft Google geen app-wachtwoorden.
2. Ga naar <https://myaccount.google.com/apppasswords>.
3. Geef het een naam, bijvoorbeeld `Huismus`, en kies **Maken**.
4. Google laat het wachtwoord één keer zien, in groepjes van vier tekens.
   Kopieer het en plak het alleen in Huismus.
5. Kies in Huismus bij **Instellingen → Mailen** voor **Gmail**. Vul je
   Gmail-adres in als gebruikersnaam en plak het app-wachtwoord bij
   Wachtwoord. De spaties mogen blijven staan, Huismus haalt ze weg. De
   server, de poort en de beveiliging vult Huismus zelf in.
6. Sla op en kies **Testmail sturen**.

Zie je de pagina met app-wachtwoorden niet? Bij een Google Workspace-account
kan de beheerder die hebben uitgezet. Vraag de beheerder om het aan te
zetten, of kies **Anders** en mail via een andere mailserver.

**Afzender.** Gmail verstuurt altijd vanaf het adres van het account waarmee
je inlogt, ook als je bij "Afzender" iets anders invult. Wil je een ander
adres als afzender, voeg het dan eerst in Gmail toe onder Instellingen →
Accounts → "Mail verzenden als".

**Intrekken.** Op dezelfde pagina met app-wachtwoorden verwijder je het
wachtwoord. Vanaf dat moment kan Huismus niet meer mailen. Wil je later weer
mailen, maak dan een nieuw app-wachtwoord en vul het in bij **Instellingen →
Mailen**.

## Je eigen domein (Anders)

Mail je vanaf een adres op je eigen domein, dan heb je de gegevens van je
hostingpartij nodig. Die noemt ze "uitgaande mail" of "SMTP". Meestal zijn
het deze:

| Veld | Meestal |
|---|---|
| SMTP-server | `smtp.<jouwdomein>` of `mail.<jouwdomein>` |
| Poort en beveiliging | 587 met STARTTLS, of 465 met SSL/TLS |
| Gebruikersnaam | je volledige e-mailadres |
| Wachtwoord | het wachtwoord van die mailbox |

Kies **Anders**, vul de velden in, sla op en kies **Testmail sturen**. Laat
je "Afzender" leeg, dan mailt Huismus vanaf het e-mailadres van je bedrijf.

## De standaardtekst aanpassen

Elke mail begint met een onderwerp en een tekst die je zelf instelt, bij
**Instellingen → Mailen → Standaardteksten**. Er is een tekst per soort
document (factuur, creditnota, offerte), in het Nederlands en in het Engels.
Een Engels document krijgt de Engelse tekst. Voordat je een mail verstuurt,
kun je alles nog aanpassen.

Met invulplekken zet Huismus de gegevens van het document in de tekst:

| Invulplek | Wordt |
|---|---|
| `{nummer}` | het nummer van het document |
| `{bedrag}` | het totaal, bijvoorbeeld € 850,00 |
| `{naam}` | de voornaam van de klant, of anders de naam van de klant |
| `{bedrijf}` | de naam van je bedrijf |
| `{vervaldatum}` | alleen bij een factuur: de vervaldatum |
| `{geldig_tot}` | alleen bij een offerte: tot wanneer hij geldig is |

Een tikfout zoals `{klant}` kun je niet opslaan. Zo komt hij nooit in een
mail aan een klant terecht. Heeft een offerte geen einddatum, dan laat
Huismus de regel met `{geldig_tot}` weg. Maak je een tekst leeg, dan
gebruikt Huismus weer zijn eigen tekst.

## Als mailen mislukt

De foutmelding staat op het scherm en op de tijdlijn van het document. Je
wachtwoord staat er nooit in. Dit zijn de meest voorkomende:

| De melding noemt | Wat er meestal mis is |
|---|---|
| `535` of `Username and Password not accepted` | Het wachtwoord of de gebruikersnaam klopt niet. Bij Gmail heb je een app-wachtwoord nodig, niet je gewone wachtwoord. |
| `timed out` of `Connection refused` | De server of de poort klopt niet, of je netwerk laat de verbinding naar buiten niet door. Huismus wacht hoogstens 20 seconden. |
| `SSL` of `wrong version number` | De poort en de beveiliging passen niet bij elkaar: 587 hoort bij STARTTLS, 465 bij SSL/TLS. |

Een mislukte poging verstuurt niets en verandert niets aan het document.
Verbeter de instelling en probeer het opnieuw.
