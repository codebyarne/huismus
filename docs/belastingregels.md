# Belastingregels

Naslag voor de `product-owner`-agent (`.claude/agents/product-owner.md`,
"Boekhouden in Nederland") en voor wie aan bedragen, btw of uitgaven in deze
codebase werkt. Hier staat wat de Belastingdienst over de btw publiceert, met
de bronpagina erbij. **Dit is geen boekhoudkundig of fiscaal advies.** Regels
kunnen wijzigen na het nakijken. Controleer bij twijfel de bronpagina's zelf
of vraag een boekhouder.

Nagekeken op 6 november 2026. Alleen officiële bronnen: belastingdienst.nl en
Ondernemersplein (sinds kort `ondernemersplein.overheid.nl`; het oude adres
`ondernemersplein.kvk.nl` stuurt daarheen door). Citaten staan tussen
aanhalingstekens en zijn letterlijk overgenomen, ook de u-vorm. Een bedrag of
termijn staat hier alleen als hij letterlijk op de bronpagina staat; anders
staat er **Bron ontbreekt**.

Zie `CLAUDE.md`: wat hier staat, komt nooit als juridische of fiscale
bewering in UI-tekst of codecommentaar. Factuureisen staan in
`docs/invoice-requirements.md`.

## 1. KOR (kleineondernemersregeling)

### Omzetgrens

- "Per kalenderjaar hebt u een omzet van maximaal € 20.000. De maximale
  omzet van € 20.000 geldt voor het kalenderjaar waarin u zich aanmeldt, én
  voor het kalenderjaar daarvóór."
- Andere voorwaarden: de onderneming is in Nederland gevestigd, en de
  geleverde goederen of diensten zijn met btw belast.
- Omzet zonder KOR telt exclusief btw; met KOR: "het totaal van alle bedragen
  die u aan uw klant berekent."
- Meerdere subnummers binnen één onderneming: omzet bij elkaar optellen; de
  KOR geldt voor alle subnummers of voor geen enkele.

Bron: [Voorwaarden voor deelname aan de kleineondernemersregeling (KOR)](https://www.belastingdienst.nl/wps/wcm/connect/nl/btw/content/kor-voorwaarden)
(Belastingdienst)

### Wat meedoen betekent

- "U berekent geen btw aan uw klanten. U draagt dus ook geen btw af."
- "U vermeldt geen btw op uw facturen. U hoeft zelfs helemaal geen facturen
  te versturen voor de btw. U moet wel uw inkoopfacturen bewaren."
- Factureer je toch: "U vermeldt dan op de factuur dat een vrijstelling van
  toepassing is." Een vaste formulering staat niet op de pagina (zie ook
  `docs/invoice-requirements.md`, KOR; in Huismus is het de instelbare
  `kor_text`).
- "U doet geen btw-aangifte meer. Behalve in een aantal gevallen, dan moet u
  toch incidentele aangifte doen."
- "U trekt de btw over uw zakelijke kosten en investeringen niet af." Ook
  niet voor btw uit een ander EU-land. "Bewaar uw inkoopfacturen wel."
- "In sommige gevallen moet u de btw herzien die u eerder hebt afgetrokken."

Bron: [Wat betekent meedoen met de kleineondernemersregeling (KOR)?](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/hoe_werkt_de_btw/kleineondernemersregeling/wat-betekent-meedoen-met-de-kleineondernemersregeling/wat-betekent-meedoen-met-de-kleineondernemersregeling)
(Belastingdienst)

### Aanmelden

- Online in Mijn Belastingdienst Zakelijk, pas nadat je als btw-ondernemer
  geregistreerd bent (brief met omzetbelastingnummer en
  btw-identificatienummer).
- "uw aanmelding [moet] uiterlijk 4 weken vóór de ingangsdatum van de KOR bij
  ons binnen zijn." Bij kwartaalaangifte: 3 maart (vanaf 1 april), 2 juni
  (1 juli), 2 september (1 oktober), 3 december (1 januari).
- Binnen 8 weken een brief met de definitieve ingangsdatum; tot dan blijf je
  btw-aangifte doen.

Bron: [Aanmelden voor de kleineondernemersregeling (KOR)](https://www.belastingdienst.nl/wps/wcm/connect/nl/btw/content/aanmelden-kor)
(Belastingdienst)

### Afmelden, minimale duur en boven de grens

- Vrijwillig: "Dan mag u zich op elk moment afmelden. Uw afmelding gaat dan
  in op de 1e dag van het volgende kwartaal." De afmeldpagina: "met ingang
  van de 1e dag van uw aangiftetijdvak", en "uiterlijk 4 weken voor u de
  afmelding in wilt laten gaan."
- Een minimale deelnameduur noemen de pagina's niet. Wel een wachttijd na
  afmelden: "de rest van het kalenderjaar waarin u bent afgemeld, en het jaar
  erop." Daarna kun je je opnieuw aanmelden.
- Boven de grens: "Zodra uw omzet boven de € 20.000 in 1 kalenderjaar komt,
  mag u namelijk geen gebruik meer maken van de KOR. U moet zich op dat
  moment direct afmelden." En: "Ook de omzetoverschrijdende handeling zelf
  valt niet meer onder de btw-vrijstelling. U moet daarom over het volledige
  bedrag van die levering of dienst btw aan uw klant in rekening brengen."
- Afmelden in Mijn Belastingdienst Zakelijk; een papieren formulier wordt niet
  meer behandeld. Binnen 8 weken een brief met de definitieve einddatum.

Bron: [Afmelden voor de kleineondernemersregeling (KOR)](https://www.belastingdienst.nl/wps/wcm/connect/nl/btw/content/afmelden-kor)
(Belastingdienst), [Wat betekent meedoen met de kleineondernemersregeling (KOR)?](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/hoe_werkt_de_btw/kleineondernemersregeling/wat-betekent-meedoen-met-de-kleineondernemersregeling/wat-betekent-meedoen-met-de-kleineondernemersregeling)
(Belastingdienst)

### Wijzigingen per 2025 en 2026

- 2025: "Sinds 1 januari 2025 is het voor ondernemers die zakendoen in andere
  EU-landen mogelijk om deel te nemen aan de kleineondernemersregeling in de
  EU (EU-KOR)." Volgens Ondernemersplein: "Uw totale omzet mag dan maximaal
  €100.000 per kalenderjaar zijn."
- Registratiedrempel: "Hebt u een jaaromzet van maximaal € 2.200? En bent u
  niet verplicht uw onderneming in te schrijven bij de Kamer van Koophandel
  (KVK)?" Dan hoef je je niet als btw-ondernemer aan te melden en gelden
  dezelfde gevolgen als bij de KOR. Sinds wanneer: **Bron ontbreekt**.
- Andere wijzigingen per 2025 (bijvoorbeeld van de deelnameduur) of per 2026:
  **Bron ontbreekt**. De nagekeken pagina's noemen er geen.

Bron: [Kleineondernemersregeling (KOR)](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/hoe_werkt_de_btw/kleineondernemersregeling/)
(Belastingdienst), [Registratiedrempel voor kleine ondernemers](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/hoe_werkt_de_btw/kleineondernemersregeling/registratiedrempel-voor-kleine-ondernemers)
(Belastingdienst), [Btw-regelingen en -vrijstellingen](https://ondernemersplein.overheid.nl/geldzaken-en-belastingen/omzetbelasting-btw/btw-regelingen/)
(Ondernemersplein, gepubliceerd door de Belastingdienst)

## 2. Btw-tarieven en btw verlegd

- "Het algemene btw-tarief is 21%. Voor sommige goederen en diensten geldt het
  lage tarief van 9%, het 0%-tarief of een vrijstelling."
- 21 % geldt voor alles wat niet vrijgesteld is en niet onder 9 % of 0 % valt.
  9 % geldt voor "een beperkt aantal goederen" en "een aantal diensten".
- 0 % meestal bij levering van goederen aan het buitenland; "u [vermeldt] op
  de factuur dat het 0%-tarief is toegepast."
- Welke goederen en diensten precies onder 9 % of 0 % vallen: niet hier
  overgenomen, zie de subpagina's van de bron.

Bron: [Tarieven en vrijstellingen](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/tarieven_en_vrijstellingen/)
(Belastingdienst)

- Btw verlegd: "In een aantal gevallen betaalt niet u de btw, maar de
  ondernemer aan wie u diensten of goederen levert." Onder meer bij zakendoen
  met het buitenland, onderaanneming in bouw, schoonmaak en hoveniers, en
  mobiele telefoons, chips, laptops en tablets.
- Op de factuur: "rekent u geen btw, maar vermeldt u op de factuur: 'btw
  verlegd' en het btw-identificatienummer van die afnemer. De vergoeding
  vermeldt u per btw-tarief."

Bron: [Verleggingsregeling](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/btw_berekenen_aan_uw_klanten/waarover_btw_berekenen/verleggingsregeling/)
(Belastingdienst), [Wanneer btw verleggen?](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/btw_berekenen_aan_uw_klanten/waarover_btw_berekenen/verleggingsregeling/wanneer_btw_verleggen/wanneer_btw_verleggen)
(Belastingdienst), [U maakt gebruik van de verleggingsregeling](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/administratie_bijhouden/facturen_maken/factuureisen/aangepaste_regels_facturen/u_maakt_gebruik_van_de_verleggingsregeling)
(Belastingdienst)

## 3. Zonder KOR: voorbelasting aftrekken

- "Als u uitgaven doet voor uw onderneming, mag u de btw hierover aftrekken.
  Dit noemen we: aftrekken als voorbelasting. U doet dit in uw btw-aangifte."
  Over inkopen, kosten en investeringen.
- Voorwaarden: je gebruikt het voor omzet belast met 21 %, 9 % of 0 % of met
  verlegde btw (niet voor vrijgestelde omzet); "U krijgt een factuur waarop
  btw staat. Deze factuur moet voldoen aan de eisen voor een btw-factuur.";
  en het is echt aan je geleverd.
- "Als ondernemer moet u zelf kunnen aantonen dat u btw mag aftrekken over
  zakelijke uitgaven."
- Wanneer: "in het aangiftetijdvak waarin die btw aan u in rekening is
  gebracht. Ook als u uw leveranciers nog niet hebt betaald."
- Niet aftrekbaar onder meer: privégebruik; relatiegeschenken en
  personeelsvoorzieningen maar beperkt.

Bron: [Welke btw mag u aftrekken?](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/btw_aftrekken/welke_btw_is_aftrekbaar/welke_btw_mag_u_aftrekken)
(Belastingdienst), [Hoe werkt aftrekken van btw?](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/btw_aftrekken/welke_btw_is_aftrekbaar/hoe_werkt_aftrekken_van_btw)
(Belastingdienst), [Btw aftrekken? Houd dan rekening met deze regels en voorwaarden](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/btw_aftrekken/)
(Belastingdienst)

### Eisen aan een inkoopfactuur of kassabon

- Een inkoopfactuur moet aan de gewone factuureisen voldoen; die staan in
  `docs/invoice-requirements.md`.
- Vereenvoudigde factuur: mag bij "het factuurbedrag is maximaal € 100
  (inclusief btw)". Daarop in elk geval: de datum van uitreiken, naam en
  adresgegevens van de leverancier, welke goederen of diensten, en "de btw of
  de gegevens aan de hand waarvan de btw kan worden berekend".
- Brandstofbon voor een landvoertuig: tot en met € 100 volstaat "aannemelijk
  [...] maken dat u de afnemer bent"; boven € 100 "moet u te identificeren zijn
  als afnemer", bijvoorbeeld door met pinpas, creditcard of tankpas te betalen.
- Openbaar vervoer en taxi: "Het vervoersbewijs geldt dan als factuur. U mag
  dan zelf 9% btw uit de factuur of het vervoersbewijs opvoeren als
  voorbelasting."
- Een gewone kassabon als zodanig: de nagekeken pagina's zeggen er niets apart
  over; ze spreken van een (vereenvoudigde) factuur. **Bron ontbreekt** voor
  een eigen regel over kassabonnen.

Bron: [Vereenvoudigde factuur](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/administratie_bijhouden/facturen_maken/factuureisen/aangepaste_regels_facturen/vereenvoudigde_factuur)
(Belastingdienst), [Btw aftrekken bij bijzondere facturen](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/btw_aftrekken/welke_btw_is_aftrekbaar/bijzondere_situaties/bijzondere_facturen)
(Belastingdienst)

## 4. Btw-aangifte

- "U kunt btw-aangifte doen per maand, per kwartaal of per jaar." "De meeste
  ondernemers doen btw-aangifte per kwartaal." Je krijgt een brief met je
  tijdvak.
- Ook zonder btw in een periode: "U moet altijd btw-aangifte doen" (een
  0-aangifte of nihilaangifte).
- Uiterste datum: per kwartaal of maand "uiterlijk op de laatste dag van de
  maand die volgt op het kwartaal of de maand waarover u aangifte doet"; per
  jaar "vóór 1 april van het eerstvolgende jaar." Uitstel alleen bij een
  calamiteit.
- Te laat aangifte doen of betalen: een naheffingsaanslag en boetes.

Bron: [Btw-aangifte: waar moet u aan denken?](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/btw_aangifte_doen_en_betalen/btw-aangifte-waar-moet-u-aan-denken/)
(Belastingdienst)

### Welke bedragen erin komen

- "In de aangifte vermeldt u de btw die u hebt berekend aan uw klanten, en de
  btw die uw leveranciers aan u hebben berekend." Het verschil betaal je of
  krijg je terug.
- Rubrieken die het stap-voor-stap-voorbeeld noemt:
  - 1a "Levering/diensten belast met hoog tarief": links de omzet exclusief
    btw, rechts de btw.
  - 3 en 4: leveringen en diensten met het buitenland.
  - 5a "Verschuldige btw (rubrieken 1 t/m 4)": het totaal.
  - 5b "Voorbelasting": de aftrekbare btw op inkopen.
- De andere rubrieken (zoals voor 9 %, 0 % of verlegde btw): **Bron
  ontbreekt**. Ze staan in de Toelichting bij de btw-aangifte (pdf op
  `download.belastingdienst.nl`, nog niet nagekeken).
- In de laatste aangifte van het jaar komen afrekeningen over het kalenderjaar,
  zoals privégebruik.

Bron: [Ik moet btw-aangifte doen - hoe vul ik die in?](https://www.belastingdienst.nl/wps/wcm/connect/nl/btw/content/ik-moet-btw-aangifte-doen-hoe-vul-ik-die-in)
(Belastingdienst), [Btw-aangifte invullen en versturen](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/btw_aangifte_doen_en_betalen/btw-aangifte-waar-moet-u-aan-denken/hoe-btw-aangifte-invullen-en-versturen)
(Belastingdienst), [Toelichting bij de btw-aangifte (omzetbelasting)](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/themaoverstijgend/brochures_en_publicaties/toelichting_bij_de_digitale_aangifte_omzetbelasting)
(Belastingdienst)

## 5. Bewaarplicht

- "U bent verplicht uw administratie 7 jaar te bewaren. Gegevens over
  onroerende zaken en rechten op onroerende zaken moet u 10 jaar bewaren."
- De termijn begint pas als een gegeven niet meer actueel is (voorbeeld: een
  leasecontract van 4 jaar, daarna 7 jaar).
- Kortere termijnen kun je afspreken, maar "De basisgegevens [...] zoals
  bijvoorbeeld de debiteuren- en crediteurenadministratie, de in- en
  verkoopadministratie en het grootboek, moet u altijd 7 jaar bewaren."
- Wat: "alle gegevens over uw onderneming die u vastlegt op papier of op een
  digitale manier", ook wat een boekhouder voor je bijhoudt, en ook na het
  stoppen van de onderneming.
- Hoe: "U bewaart de gegevens uit uw administratie in de originele vorm:
  digitaal of op papier." Digitaal: "moet u ervoor zorgen dat wij uw
  programma's en bestanden bij een controle kunnen gebruiken. Het is niet
  voldoende als u uw bestanden uitsluitend in afgedrukte vorm bewaart."
- Een papieren bon scannen en het papier weggooien: **Bron ontbreekt** op deze
  pagina's. Mogelijk staat het in de brochure "Uw geautomatiseerde
  administratie en de fiscale bewaarplicht" (nog niet nagekeken).

Bron: [Hoe lang moet u uw administratie bewaren voor de btw: 7 of 10 jaar?](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/administratie_bijhouden/administratie_bewaren/)
(Belastingdienst), [Wat moet u bewaren?](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/administratie_bijhouden/administratie_bewaren/wat_moet_u_bewaren)
(Belastingdienst), [Hoe bewaart u uw administratie?](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/administratie_bijhouden/administratie_bewaren/hoe_bewaart_u_uw_administratie)
(Belastingdienst)
