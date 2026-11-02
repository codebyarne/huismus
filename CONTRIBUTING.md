# Bijdragen aan Huismus

Fijn dat je wilt bijdragen. Dit document beschrijft hoe.

## Voordat je begint

Lees eerst `SPEC.md`: het ontwerp, wat er al gebouwd is en welke keuzes al
gemaakt zijn. Alle code van de app staat in `huismus/`
(import als `huismus.documents`, enz.); waar wat staat:
[`docs/architectuur.md`](docs/architectuur.md). Voor iets groter dan een kleine
bugfix: open eerst een issue om de aanpak te bespreken voordat je tijd
in code steekt — `SPEC.md` is de bron van waarheid voor ontwerpkeuzes,
en een pull request die daarvan afwijkt zonder overleg wordt waarschijnlijk
niet zomaar gemerged.

## Ontwikkelomgeving

Zie `README.md` voor installatie. De poort van dit project is
`./scripts/verify.sh` — draai dit voordat je een pull request opent:

```
./scripts/verify.sh
```

Dit controleert (in deze volgorde): dat er geen echte administratiedata in
git zit, lint en formatting (`ruff`), tests (`pytest`), en dat er geen
vergeten migratie is (`makemigrations --check`).

## Wat een goede bijdrage maakt

- **Eén concern per commit**, conventionele commitberichten
  (`feat(...)`, `fix(...)`, `docs(...)`, etc.).
- **Tests eerst voor factuurlogica** (totalen, nummering, onveranderlijkheid,
  creditnota's) — zie CLAUDE.md's harde regels.
- **Geen nieuwe dependency zonder reden** — de standaardbibliotheek en
  Django's eigen functionaliteit hebben de voorkeur.
- **Gettext voor alles wat de gebruiker ziet** (`gettext_lazy` in
  modellen/formulieren, `{% translate %}` in templates). Nederlands is de
  brontaal; Engels moet ook werken (`manage.py compilemessages`).
- **Geen echte data.** Fixtures en testdata zijn altijd fictief of volledig
  geanonimiseerd — nooit een echt Moneybird-export, IBAN, of
  klantgegeven, ook niet in een issue of pull request.

## Developer Certificate of Origin (DCO)

Huismus gebruikt een DCO in plaats van een CLA: door een commit te
"signen" verklaar je dat je het recht hebt om de bijdrage onder de
AGPL-3.0-or-later-licentie van dit project aan te bieden (de volledige
tekst staat in `LICENSE` en op
[developercertificate.org](https://developercertificate.org/)).

```
git commit -s -m "korte, duidelijke omschrijving"
```

Dit voegt een `Signed-off-by:`-regel toe aan je commitbericht. Pull
requests zonder deze regel worden niet gemerged.

## Pull requests

1. Fork de repository en maak een branch voor je wijziging.
2. Zorg dat `./scripts/verify.sh` groen is.
3. Open de pull request met een korte beschrijving van het "waarom", niet
   alleen het "wat" (de diff laat het "wat" al zien).

---

# Contributing to Huismus (English)

Thanks for wanting to contribute. This document describes how.

## Before you start

Read `SPEC.md` first: the design, what's already built and which decisions
have already been made. All of the app's code
lives in `huismus/` (imported as `huismus.documents`, etc.); where things
live: [`docs/architectuur.md`](docs/architectuur.md) (Dutch). For anything bigger than
a small bugfix: open an issue to discuss the approach before putting
time into code — `SPEC.md` is the source of truth for design decisions,
and a pull request that diverges from it without discussion is unlikely
to be merged as-is.

## Development environment

See `README.md` for setup. This project's gate is
`./scripts/verify.sh` — run it before opening a pull request:

```
./scripts/verify.sh
```

This checks (in this order): no real bookkeeping data in git, lint and
formatting (`ruff`), tests (`pytest`), and no forgotten migration
(`makemigrations --check`).

## What makes a good contribution

- **One concern per commit**, conventional commit messages
  (`feat(...)`, `fix(...)`, `docs(...)`, etc.).
- **Tests first for invoicing logic** (totals, numbering, immutability,
  credit notes) — see CLAUDE.md's hard rules.
- **No new dependency without a stated reason** — the standard library
  and Django's own functionality are preferred.
- **Gettext for everything user-facing** (`gettext_lazy` in
  models/forms, `{% translate %}` in templates). Dutch is the source
  language; English must also work (`manage.py compilemessages`).
- **No real data.** Fixtures and test data are always fictional or fully
  anonymised — never a real Moneybird export, IBAN, or customer detail,
  not even in an issue or pull request.

## Developer Certificate of Origin (DCO)

Huismus uses a DCO instead of a CLA: signing off a commit certifies that
you have the right to submit the contribution under this project's
AGPL-3.0-or-later license (full text in `LICENSE` and at
[developercertificate.org](https://developercertificate.org/)).

```
git commit -s -m "short, clear description"
```

This adds a `Signed-off-by:` line to your commit message. Pull requests
without it won't be merged.

## Pull requests

1. Fork the repository and create a branch for your change.
2. Make sure `./scripts/verify.sh` passes.
3. Open the pull request with a short description of *why*, not just
   *what* (the diff already shows the "what").
