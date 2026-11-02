# Schrijfwijzer

Hoe Huismus praat: in de app (knoppen, meldingen, foutmeldingen, uitleg,
onboarding), in de hulppagina's (`docs/hulp/`) en in de documentatie. De toon
is die van Arne: vriendelijk, direct en eerlijk, zonder opsmuk. Een nieuwe
tekst voldoet hier meteen aan; een oude tekst gaat mee zodra je hem aanraakt.
Besluit: `huismus-intern/besluiten.md`, 2026-11-01, "Teksten in Arnes stem".

Teksten over wet of belasting (de KOR-tekst, wat er op een factuur moet
staan, de teksten in de pdf) herschrijf je niet zelf: dat is een vraag aan
Arne (`CLAUDE.md`, escalatielijst).

## De toon

- **Je en jij**, nooit u. De lezer is een zzp'er die gewoon zijn administratie
  wil doen.
- **Kort en actief.** "Huismus maakt elke dag een back-up", niet "Er wordt
  dagelijks een back-up gemaakt". Eén gedachte per zin.
- **Concreet.** Zeg wat er gebeurt, waar en wanneer: "elke dag, zolang
  Huismus open staat" in plaats van "regelmatig".
- **Eerlijk.** Kan iets niet, of heeft het een nadeel, zeg het gewoon: "Een
  back-up op dezelfde schijf helpt niet als die schijf kapotgaat."
- **Geen ik.** Huismus is geen persoon en Arne schrijft hier niet als
  blogger. "Huismus doet …" of de lezer aanspreken.
- **Geen grapjes in de app**, ook niet in lege schermen of foutmeldingen. In
  een hulppagina mag het iets losser, zolang het helpt.

## Per soort tekst

- **Knop:** een werkwoord dat zegt wat er gebeurt: "Opslaan", "Factuur
  uitgeven", "Back-up maken". Geen "OK" of "Doorgaan" als je kunt zeggen
  waarheen.
- **Melding:** eerst wat er aan de hand is, dan wat je kunt doen. "Je hebt
  nog geen back-up. Kies een map, dan gaat het vanzelf."
- **Foutmelding:** wat misging, in woorden van de gebruiker, en wat je nu
  doet. Geen foutcodes, geen "ongeldige invoer". Niet: "Fout 403". Wel:
  "Dropbox weigert de toegang. Koppel Dropbox opnieuw."
- **Uitleg op een scherm:** één of twee zinnen. Meer nodig? Link naar de
  hulp met "Zo werkt het →".
- **Hulppagina:** begin met wat de lezer wil doen, niet met hoe het werkt.
  Eerst in gewone taal waarom, dan de stappen, dan de details voor wie ze
  wil. Kopjes kort, liefst wat je gaat doen ("Een map koppelen").
- **Documentatie voor ontwikkelaars:** dezelfde toon; vakwoorden mogen, want
  de lezer kent ze.

## Woorden

- **Gewoon Nederlands** waar dat bestaat: "back-up terugzetten", niet
  "restoren"; "map", niet "directory". Vaste namen blijven: Docker, NAS,
  Dropbox, WebDAV, KOR.
- **Een vakwoord leg je één keer uit**, de eerste keer dat de lezer het
  tegenkomt, en daarna gebruik je steeds hetzelfde woord. Dus niet de ene
  keer "koppelen" en de andere keer "mounten" of "doorgeven".
- **Domeinwoorden** zoals in de app: factuur, offerte, creditnota, klant,
  uitgave, uitgeven. Een klant heet nooit "contact"; "contactpersoon" is een
  persoon bij een klant.
- **Na een dubbele punt** een kleine letter ("Leeg: het e-mailadres van je
  bedrijf.", "Omschrijving: vul dit in."), behalve bij een woord dat altijd
  hoofdletters heeft (IBAN, KvK).
- **Veldfouten** zeggen wat je invult: "Vul dit in.", "Vul een datum in.",
  niet "Dit veld is verplicht." Ze staan op één plek,
  `huismus/core/form_messages.py`, en gelden in elk formulier.
- **Niet doen:** u/uw; corporate taal ("naadloos", "cruciaal", "optimaal",
  "gelieve", "succesvol"); AI-trucs ("Het is niet X, het is Y", drie
  bijvoeglijke naamwoorden achter elkaar, een retorische vraag die je zelf
  beantwoordt, "Stel je voor…"); em-dashes (—) als verbinding in een zin:
  gebruik een punt, een dubbele punt of een komma. Een em-dash in de
  titelbalk ("Back-ups — Instellingen — Huismus") is geen zin en mag.

`tests/core/test_schrijfwijzer.py` bewaakt het meetbare deel: u/uw, de
verboden woorden en em-dashes in de Nederlandse teksten en de hulppagina's.
De rest is aan de schrijver en de review.

## Engels

Dezelfde toon in plain English. Vertaal de bedoeling, niet de woorden: een
Nederlandse zin die in het Engels stijf wordt, schrijf je opnieuw.
"Choose a folder and it happens by itself", niet "Choose a folder, then it
goes by itself". Geen "seamless", "leverage", "please note". Sentence case in
kopjes en knoppen ("Back up now", niet "Back Up Now").

---

# Writing guide (English)

How Huismus talks, in the app, the help pages (`docs/hulp/`) and the docs:
friendly, direct and honest, without fluff. New text follows this guide; old
text follows it as soon as you touch it. Text about law or tax (the KOR
notice, invoice requirements, PDF wording) is a question for the owner, not
something to rewrite.

- **You**, short and active sentences, one idea per sentence. Concrete: say
  what happens, where and when. Honest about limits and downsides.
- **No "I"** and no jokes in the app, not even in empty states or errors.
  Help pages may be a little looser.
- **Buttons** are verbs that say what happens. **Messages** say what's going
  on, then what you can do. **Errors** say what went wrong in the user's
  words and what to do now; no codes, no "invalid input". **On-screen
  explanations** are one or two sentences; for more, link to help with
  "How it works →". **Help pages** start with what the reader wants to do,
  then why, then the steps, then details.
- **Customer**, never "contact" for a customer. A small letter after a
  colon. Field errors say what to fill in ("Fill this in."), from
  `huismus/core/form_messages.py`.
- **Plain words.** Explain a technical word once, then always use the same
  one ("link a folder", never also "mount" or "pass on"). Keep fixed names
  (Docker, NAS, Dropbox, WebDAV, KOR).
- **Don't:** corporate words ("seamless", "leverage", "please note"),
  "It's not X, it's Y", triples of adjectives, rhetorical questions you
  answer yourself, em dashes (—) inside sentences. Sentence case in headings
  and buttons.
- **Translate the meaning, not the words.** Rewrite a sentence that turns
  stiff in English.

`tests/core/test_schrijfwijzer.py` checks the measurable part.
