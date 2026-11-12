#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Zet het ondertekenen van de Mac-app klaar (besluit 2026-11-12), één keer,
# nadat je lid bent van het Apple Developer Program. Het script:
#   1. maakt een sleutel en een aanvraag voor een Developer ID-certificaat;
#   2. laat je dat certificaat bij Apple ophalen;
#   3. laat je een API-sleutel voor het notariseren ophalen;
#   4. zet alles als geheim in GitHub, waar release.yml het gebruikt.
# De sleutels komen niet op het scherm en blijven niet op deze Mac achter.
#
# Gebruik: ./scripts/mac-ondertekenen.sh   (nodig: gh, ingelogd)
set -euo pipefail

REPO=codebyarne/huismus
DOWNLOADS="$HOME/Downloads"
openssl=/usr/bin/openssl  # LibreSSL: maakt een .p12 die macOS kan inlezen

if ! gh auth status >/dev/null 2>&1; then
    echo "Log eerst in bij GitHub: gh auth login" >&2
    exit 1
fi

work=$(mktemp -d)
chmod 700 "$work"
trap 'rm -rf "$work"' EXIT

newest() {
    # Het nieuwste bestand in Downloads dat op het patroon lijkt.
    find "$DOWNLOADS" -maxdepth 1 -name "$1" -newer "$work" -print0 \
        | xargs -0 ls -t 2>/dev/null | head -n 1
}

wait_for() {
    local pattern=$1 file
    while true; do
        read -r -p "Druk op Enter als het bestand in Downloads staat. "
        file=$(newest "$pattern")
        if [ -n "$file" ]; then
            echo "$file"
            return
        fi
        echo "Geen nieuw bestand $pattern in $DOWNLOADS gevonden. Probeer het nog eens." >&2
    done
}

echo
echo "Stap 1 van 3: het certificaat"
request="$DOWNLOADS/Huismus.certSigningRequest"
"$openssl" req -new -newkey rsa:2048 -nodes -keyout "$work/key.pem" \
    -subj "/CN=Huismus Developer ID/C=NL" -out "$request" 2>/dev/null
cat <<EOF
In je browser opent Apple de pagina voor een nieuw certificaat.
  - Kies "Developer ID Application" en klik op Continue.
  - Kies bij Profile Type "G2 Sub-CA".
  - Kies bij "Choose File" het bestand Huismus.certSigningRequest in Downloads.
  - Klik op Continue en dan op Download.
EOF
open "https://developer.apple.com/account/resources/certificates/add"
certificate=$(wait_for "developerID_application*.cer" 2>/dev/tty)

"$openssl" x509 -inform DER -in "$certificate" -out "$work/certificate.pem"
if [ "$("$openssl" x509 -noout -modulus -in "$work/certificate.pem")" != \
    "$("$openssl" rsa -noout -modulus -in "$work/key.pem" 2>/dev/null)" ]; then
    echo "Dit certificaat hoort niet bij de aanvraag van zojuist. Draai het script opnieuw." >&2
    exit 1
fi
name=$("$openssl" x509 -noout -subject -in "$work/certificate.pem" | sed -n 's/.*CN=\([^/]*\).*/\1/p')
password=$("$openssl" rand -hex 24)
"$openssl" pkcs12 -export -inkey "$work/key.pem" -in "$work/certificate.pem" \
    -out "$work/certificate.p12" -passout "pass:$password"
base64 -i "$work/certificate.p12" | gh secret set MACOS_CERTIFICATE --repo "$REPO"
printf %s "$password" | gh secret set MACOS_CERTIFICATE_PASSWORD --repo "$REPO"
rm -f "$request" "$certificate"
echo "Klaar: $name staat in GitHub."

echo
echo "Stap 2 van 3: de sleutel voor het notariseren"
cat <<EOF
In je browser opent App Store Connect, bij Gebruikers en toegang › Integraties.
  - Vraagt hij om toegang aan te vragen, klik dan op Request Access en ga akkoord.
  - Klik bij Team Keys op + (of "Generate API Key").
  - Naam: Huismus release. Toegang: Developer. Klik op Generate.
  - Klik bij de nieuwe sleutel op Download. Dat kan maar één keer.
  - Laat de pagina open: je hebt zo de Issuer ID nodig, die staat erboven.
EOF
open "https://appstoreconnect.apple.com/access/integrations/api"
key=$(wait_for "AuthKey_*.p8" 2>/dev/tty)
key_id=$(basename "$key" .p8)
key_id=${key_id#AuthKey_}
while true; do
    read -r -p "Plak de Issuer ID: " issuer
    if [[ $issuer =~ ^[0-9a-fA-F-]{36}$ ]]; then
        break
    fi
    echo "Een Issuer ID ziet eruit als 1a2b3c4d-1a2b-1a2b-1a2b-1a2b3c4d5e6f." >&2
done

echo
echo "Stap 3 van 3: naar GitHub"
base64 -i "$key" | gh secret set APPLE_API_KEY --repo "$REPO"
printf %s "$key_id" | gh secret set APPLE_API_KEY_ID --repo "$REPO"
printf %s "$issuer" | gh secret set APPLE_API_ISSUER --repo "$REPO"
rm -f "$key"

cat <<EOF

Klaar. Vanaf de volgende release ondertekent GitHub de Mac-app en laat Apple hem
notariseren. Hij opent dan met een dubbelklik.
De sleutels staan alleen nog in GitHub. Raak je ze kwijt, draai dit script
dan opnieuw: je mag meerdere certificaten en sleutels hebben.
EOF
