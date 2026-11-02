# Huismus via Tailscale (HTTPS)

Huismus zet zijn inlogcookie buiten `DEBUG` op "alleen via HTTPS" (SPEC.md
sectie 9). Open je de Pi via een gewoon Tailscale-adres
(`http://100.x.y.z:8000`), dan is het verkeer wel versleuteld door
Tailscale, maar ziet de browser HTTP: Safari, Firefox en Chrome weigeren dan
het cookie en inloggen lukt niet.

De oplossing is `tailscale serve`: Tailscale geeft de Pi een eigen
HTTPS-adres met een geldig certificaat, bijvoorbeeld
`https://huismus.jouw-tailnet.ts.net`, en stuurt het verkeer door naar de
container. Alleen apparaten in je eigen tailnet kunnen erbij.

## Stappen

1. Zet in de Tailscale-beheeromgeving (DNS) **MagicDNS** en
   **HTTPS-certificaten** aan.
2. Start de container zo dat poort 8000 alleen op de Pi zelf bereikbaar is
   (niet op je hele netwerk), met je tailnet-adres als host:

   ```
   docker run -d --name huismus \
     -e SECRET_KEY=<lange-willekeurige-string> \
     -e ALLOWED_HOSTS=huismus.jouw-tailnet.ts.net \
     -e CSRF_TRUSTED_ORIGINS=https://huismus.jouw-tailnet.ts.net \
     -v huismus-data:/app/data \
     -p 127.0.0.1:8000:8000 \
     huismus
   ```

3. Laat Tailscale HTTPS serveren en doorsturen naar de container:

   ```
   sudo tailscale serve --bg 8000
   ```

   `tailscale serve status` toont het adres. De precieze opties verschillen
   per Tailscale-versie; zie `tailscale serve --help` of de documentatie van
   Tailscale.

4. Open `https://huismus.jouw-tailnet.ts.net` op je laptop of telefoon (met
   Tailscale aan) en log in.

## Waarom `CSRF_TRUSTED_ORIGINS`

Django controleert bij elk formulier of het van dezelfde site komt. Achter
`tailscale serve` komt het verzoek bij Django binnen als HTTP van localhost,
terwijl de browser `https://…ts.net` meestuurt. Door dat adres in
`CSRF_TRUSTED_ORIGINS` te zetten, weet Django dat het klopt.

## Lokaal ontwikkelen

Met `DEBUG=true` (zie README) is het cookie niet beperkt tot HTTPS, en werkt
`http://localhost` gewoon.
