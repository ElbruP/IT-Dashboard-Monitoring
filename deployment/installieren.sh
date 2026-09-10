#!/bin/bash
# =====================================================================
#  IT-Informationsplattform – Einrichtung auf dem Server
#
#  Aufruf als root im Projektverzeichnis:
#      bash deployment/installieren.sh
#
#  Das Skript fasst die wiederkehrenden Schritte zusammen. Entscheidungen,
#  die eine Eingabe erfordern (Kennwoerter, Absicherung der Datenbank),
#  bleiben bewusst manuell und werden angesagt.
# =====================================================================

set -euo pipefail

ZIEL="/opt/monitoring"
DIENSTBENUTZER="monitoring"

blau()  { printf "\n\033[1;36m== %s\033[0m\n" "$1"; }
gut()   { printf "   \033[0;32mOK\033[0m  %s\n" "$1"; }
warn()  { printf "   \033[0;33m!\033[0m   %s\n" "$1"; }
fehler(){ printf "   \033[0;31mX\033[0m   %s\n" "$1"; exit 1; }

[ "$(id -u)" -eq 0 ] || fehler "Bitte als root ausfuehren."
[ -f "backend/app/api.py" ] || fehler "Bitte im Projektverzeichnis aufrufen."

QUELLE="$(pwd)"

# --- 1. Pakete --------------------------------------------------------
blau "Pakete installieren"
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip mariadb-server nginx ufw curl
gut "Pakete vorhanden"

# --- 2. Firewall ------------------------------------------------------
blau "Firewall einrichten"
ufw allow OpenSSH        >/dev/null
ufw allow 'Nginx Full'   >/dev/null
ufw --force enable       >/dev/null
gut "Nur 22, 80 und 443 sind geoeffnet"
ufw status verbose | sed 's/^/   /'

# --- 3. Dienstbenutzer und Ablage ------------------------------------
blau "Projekt bereitstellen"
if ! id "$DIENSTBENUTZER" >/dev/null 2>&1; then
    adduser --system --group --home "$ZIEL" "$DIENSTBENUTZER"
    gut "Dienstbenutzer $DIENSTBENUTZER angelegt"
else
    gut "Dienstbenutzer $DIENSTBENUTZER vorhanden"
fi

mkdir -p "$ZIEL"
# Nur kopieren, wenn das Projekt nicht bereits am Ziel liegt.
if [ "$QUELLE" != "$ZIEL" ]; then
    cp -r "$QUELLE"/. "$ZIEL"/
    gut "Dateien nach $ZIEL kopiert"
fi
chown -R "$DIENSTBENUTZER:$DIENSTBENUTZER" "$ZIEL"

# --- 4. Laufzeitumgebung ---------------------------------------------
blau "Python-Umgebung einrichten"
python3 -m venv "$ZIEL/venv"
"$ZIEL/venv/bin/pip" install --quiet --upgrade pip
"$ZIEL/venv/bin/pip" install --quiet -r "$ZIEL/backend/requirements.txt"
gut "Abhaengigkeiten installiert"

# --- 5. Konfiguration -------------------------------------------------
blau "Konfiguration erzeugen"
ENVDATEI="$ZIEL/backend/.env"

if [ -f "$ENVDATEI" ]; then
    warn ".env ist bereits vorhanden und wird nicht ueberschrieben"
else
    read -rsp "   Kennwort fuer den Datenbankbenutzer 'monitoring': " DBKENNWORT
    echo
    [ -n "$DBKENNWORT" ] || fehler "Kennwort darf nicht leer sein."

    SCHLUESSEL="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"

    cat > "$ENVDATEI" <<EOF
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=monitoring
DB_USER=monitoring
DB_PASSWORT=$DBKENNWORT

GITHUB_TOKEN=
HTTP_TIMEOUT=10
HTTP_VERSUCHE=3

SITZUNG_SCHLUESSEL=$SCHLUESSEL
SITZUNG_DAUER_MIN=480
COOKIE_SICHER=true

INTERVALL_VERSIONEN_MIN=60
INTERVALL_MELDUNGEN_MIN=15
INTERVALL_SCHWELLWERTE_MIN=5
INTERVALL_SIMULATION_MIN=5
SIMULATION_AKTIV=false
ZEITZONE=Europe/Berlin

MAIL_AKTIV=false
SMTP_HOST=
SMTP_PORT=587
SMTP_BENUTZER=
SMTP_KENNWORT=
SMTP_STARTTLS=true
MAIL_ABSENDER=monitoring@example.de
MAIL_EMPFAENGER=
INTERVALL_BENACHRICHTIGUNG_MIN=10
EOF
    gut ".env erzeugt, Sitzungsschluessel erstellt"

    # Dasselbe Kennwort in das Benutzerskript eintragen, damit beide
    # Angaben nicht auseinanderlaufen.
    sed -i "s/HIER_KENNWORT_EINSETZEN/$DBKENNWORT/g" "$ZIEL/datenbank/03_benutzer.sql"
    gut "Kennwort in 03_benutzer.sql eingesetzt"
fi

chown "$DIENSTBENUTZER:$DIENSTBENUTZER" "$ENVDATEI"
chmod 600 "$ENVDATEI"
gut "Rechte der .env auf 600 gesetzt"

# --- 6. Datenbank -----------------------------------------------------
blau "Datenbank einrichten"
for skript in 01_schema_monitoring.sql 03_benutzer.sql \
              04_erweiterung_benachrichtigung.sql \
              05_erweiterung_quellen_meldungen.sql; do
    mariadb --default-character-set=utf8mb4 < "$ZIEL/datenbank/$skript"
    gut "$skript"
done

echo
mariadb monitoring -e "SELECT bezeichnung, typ, zustand FROM v_quellenstatus LIMIT 5;" | sed 's/^/   /'
echo
mariadb monitoring -e "SHOW GRANTS FOR 'monitoring'@'localhost';" | sed 's/^/   /'

# --- 7. Dienst --------------------------------------------------------
blau "Systemdienst einrichten"
sed "s#/opt/monitoring-dashboard#$ZIEL#g" \
    "$ZIEL/deployment/monitoring-dashboard.service" \
    > /etc/systemd/system/monitoring-dashboard.service
systemctl daemon-reload
systemctl enable --now monitoring-dashboard
sleep 4

if systemctl is-active --quiet monitoring-dashboard; then
    gut "Dienst laeuft"
else
    warn "Dienst laeuft nicht. Ursache:"
    journalctl -u monitoring-dashboard -n 20 --no-pager | sed 's/^/   /'
    exit 1
fi

ANTWORT="$(curl -s -o /dev/null -w '%{http_code}' localhost:8000/api/status || true)"
[ "$ANTWORT" = "200" ] && gut "Schnittstelle antwortet mit 200" \
                       || warn "Schnittstelle antwortet mit $ANTWORT"

blau "Fertig"
cat <<'HINWEIS'
   Naechste Schritte:
     1. nginx einrichten  (siehe INSTALLATION_VMWARE.md, Abschnitt 4)
     2. Anfangskennwoerter aendern (Abschnitt 6)
     3. Datensicherung einrichten (Abschnitt 7)
HINWEIS
