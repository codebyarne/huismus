# Factuureisen

Dit document verzamelt de wettelijke factuureisen zoals de Belastingdienst
die publiceert, als referentie voor wie aan de PDF-template of
factuurformulieren in deze codebase werkt. **Dit is geen boekhoudkundig of
fiscaal advies.** Controleer bij twijfel de bronpagina's zelf of raadpleeg
een boekhouder — regels kunnen wijzigen na het schrijven van dit document
(25 september 2026).

Zie CLAUDE.md: juridische claims horen hier en in instelbare tekstvelden
thuis, nooit hardcoded in code of UI-tekst.

## Verplichte gegevens op een factuur

Bron: [Aan welke eisen moeten facturen voldoen voor uw btw-administratie?](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/administratie_bijhouden/facturen_maken/factuureisen/factuureisen)
(Belastingdienst)

- Uw volledige naam en die van uw afnemer.
- Uw volledige adres en dat van uw afnemer.
- Uw btw-identificatienummer.
- Als u bij de KVK bent ingeschreven: uw KVK-nummer.
- De datum waarop de factuur is uitgereikt.
- Een factuurnummer. Letterlijk: "Gebruik opeenvolgende nummers voor uw
  facturen, met 1 of meer reeksen. Elk factuurnummer mag maar 1 keer
  voorkomen." (nagekeken 13 november 2026). Waar een reeks bij hoort
  (vestiging, afdeling, apparaat) zegt de pagina niet.
- Bij goederen: wat voor goederen u hebt geleverd en hoeveel.
- Bij diensten: wat voor diensten u hebt geleverd en de omvang ervan.
- De datum waarop de goederen of diensten zijn geleverd.
- Het bedrag dat u in rekening brengt, exclusief btw.
- Het btw-tarief dat van toepassing is.
- Het btw-bedrag.

### Vereenvoudigde factuur

Voor bedragen tot en met €100 (inclusief btw) gelden minder eisen. Zie
[Vereenvoudigde factuur](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/administratie_bijhouden/facturen_maken/factuureisen/aangepaste_regels_facturen/vereenvoudigde_factuur)
(Belastingdienst). Huismus past dit niet automatisch toe — elke factuur
gebruikt dezelfde volledige indeling, ongeacht bedrag.

### Verzendtermijn

Bron: [Facturen maken voor uw btw-administratie](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/administratie_bijhouden/facturen_maken/)
(Belastingdienst).

> U verstuurt de factuur uiterlijk op de 15e dag van de maand die volgt op
> de maand waarin u hebt geleverd.

## KOR (kleineondernemersregeling)

Bron: [Wat betekent meedoen met de kleineondernemersregeling?](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/hoe_werkt_de_btw/kleineondernemersregeling/wat-betekent-meedoen-met-de-kleineondernemersregeling/)
(Belastingdienst).

- Met KOR bent u niet verplicht facturen te sturen voor de btw
  ("U hoeft zelfs helemaal geen facturen te versturen voor de btw"), maar
  Huismus stuurt ze altijd — dat is de kern van het product.
- Als u wel factureert: "U vermeldt geen btw op uw facturen", en de
  factuur moet aangeven dat een vrijstelling van toepassing is.
- De Belastingdienst schrijft geen exacte wettelijke formulering voor. In
  de praktijk wordt vaak een tekst als "Factuur vrijgesteld van
  omzetbelasting op grond van artikel 25 Wet OB" gebruikt — Huismus
  hardcodet dit niet: `kor_text` in Instellingen is vrij invulbaar, precies
  om dit soort formuleringen aanpasbaar te houden zonder een codewijziging.

## Hoe dit terugkomt in de code

- `business.models.Settings.kor_text`: de instelbare vrijstellingstekst
  hierboven, getoond op elke factuur zolang `kor_enabled` aan staat
  (`documents.issuing.issue`, `huismus/templates/pdf/invoice.html`).
- `documents.issuing.issue`: weigert uit te geven zonder `kor_text` wanneer
  KOR aan staat, en staat geen btw > 0% toe op nieuwe (niet-geïmporteerde)
  regels; een creditnota mag de tarieven houden van de factuur die hij
  crediteert — zie SPEC.md invariant 6 en `documents.vat`.
- Staat de KOR uit (SPEC.md M18), dan kiest de gebruiker per regel 0, 9 of
  21% btw. Het eigen btw-nummer staat op de pdf als het in Instellingen →
  Bedrijf is ingevuld; Huismus dwingt dat (nog) niet af.
- Btw verlegd (SPEC.md M18, deel 2): een regel kan "verlegd" zijn. De tekst
  die daarbij onder de factuur komt, vult de gebruiker zelf in
  (`Settings.reverse_charge_text`); Huismus stelt geen wettekst voor. Het
  btw-nummer van de klant staat op de pdf als het bij de klant is ingevuld
  (niet op KOR-facturen). Vaste teksten voor intracommunautaire leveringen of
  vrijstellingen zijn er niet.
- Verplichte velden hierboven (naam/adres, KvK, factuurnummer, datum,
  omschrijving, bedrag excl. btw, btw-tarief, btw-bedrag) staan allemaal in
  `Document`/`DocumentLine`/`business_snapshot`/`contact_snapshot` en op
  `huismus/templates/pdf/invoice.html` — er is geen apart "compliance-mode" nodig
  omdat de datamodel al aan deze lijst voldoet. Dat klopt alleen zolang
  `documents.issuing.issue` een gekoppeld contact blijft afdwingen: zonder
  contact is er geen `contact_snapshot` en laat de PDF naam/adres van de
  klant helemaal weg. Die eis staat expliciet in `issue()` — als die ooit
  verdwijnt, moet deze paragraaf opnieuw beoordeeld worden.
