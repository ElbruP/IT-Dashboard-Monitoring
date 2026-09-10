# Installation auf einem Server

Anleitung fuer einen frisch aufgesetzten Server mit Debian 12 oder
Ubuntu 24.04. Alle Befehle als `root` oder mit vorangestelltem `sudo`.

---

## 1 Grundinstallation

```bash
apt update && apt upgrade -y
apt install -y python3-venv python3-pip mariadb-server nginx git \
               certbot python3-certbot-nginx ufw
```

## 2 Firewall

Nur die tatsaechlich benoetigten Zugaenge werden geoeffnet. Die Anwendung
und die Datenbank sind von aussen nicht erreichbar.

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
ufw status
```

## 3 Datenbank absichern

```bash
mariadb-secure-installation
```

Empfohlene Antworten: Kennwort fuer `root` setzen, anonyme Benutzer
entfernen, Anmeldung von `root` aus der Ferne verbieten, Testdatenbank
entfernen.

## 4 Projekt bereitstellen

```bash
adduser --system --group --home /opt/monitoring monitoring
cd /opt
git clone https://github.com/BENUTZER/it-informationsplattform.git monitoring-app
mv monitoring-app/* /opt/monitoring/
chown -R monitoring:monitoring /opt/monitoring
```

## 5 Schema und Datenbankbenutzer

Vorher in `datenbank/03_benutzer.sql` den Platzhalter
`HIER_KENNWORT_EINSETZEN` durch ein eigenes Kennwort ersetzen.

```bash
cd /opt/monitoring
mariadb < datenbank/01_schema_monitoring.sql
mariadb < datenbank/03_benutzer.sql
mariadb < datenbank/04_erweiterung_benachrichtigung.sql
mariadb < datenbank/05_erweiterung_quellen_meldungen.sql

mariadb monitoring -e "SELECT bezeichnung, typ, zustand FROM v_quellenstatus LIMIT 5;"
```

## 6 Python-Umgebung

```bash
python3 -m venv /opt/monitoring/venv
/opt/monitoring/venv/bin/pip install -r /opt/monitoring/backend/requirements.txt
```

## 7 Konfiguration

```bash
cp /opt/monitoring/backend/.env.example /opt/monitoring/backend/.env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # Sitzungsschluessel
nano /opt/monitoring/backend/.env
```

Zu setzen sind mindestens:

```
DB_USER=monitoring
DB_PASSWORT=<das in Schritt 5 vergebene Kennwort>
SITZUNG_SCHLUESSEL=<erzeugter Wert>
COOKIE_SICHER=true
SIMULATION_AKTIV=false
GITHUB_TOKEN=<optional, erhoeht das Anfragekontingent von 60 auf 5000/h>
```

`COOKIE_SICHER=true` ist wichtig: das Sitzungs-Cookie wird dann nur ueber
HTTPS uebertragen.

```bash
chown monitoring:monitoring /opt/monitoring/backend/.env
chmod 600 /opt/monitoring/backend/.env
```

## 8 Dienst einrichten

```bash
cp /opt/monitoring/deployment/monitoring-dashboard.service /etc/systemd/system/
sed -i 's#/opt/monitoring-dashboard#/opt/monitoring#g' \
    /etc/systemd/system/monitoring-dashboard.service
systemctl daemon-reload
systemctl enable --now monitoring-dashboard
systemctl status monitoring-dashboard --no-pager
```

## 9 Reverse Proxy und Verschluesselung

```bash
cp /opt/monitoring/deployment/nginx-monitoring.conf \
   /etc/nginx/sites-available/monitoring
sed -i 's/BEISPIEL.DE/ihre-domain.de/g' /etc/nginx/sites-available/monitoring
ln -s /etc/nginx/sites-available/monitoring /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

certbot --nginx -d ihre-domain.de
nginx -t && systemctl reload nginx
```

certbot richtet die automatische Erneuerung selbst ein. Pruefen mit
`systemctl list-timers | grep certbot`.

## 10 Erste Anmeldung

Die Oberflaeche ist nun unter `https://ihre-domain.de` erreichbar.

```
Benutzer   admin
Kennwort   Start!2026
```

**Beide Kennwoerter sind sofort zu aendern.** Ein neuer Hash laesst sich
so erzeugen:

```bash
/opt/monitoring/venv/bin/python -c \
  "from app.sicherheit import erzeuge_hash; print(erzeuge_hash('NeuesKennwort'))"
```

Anschliessend in der Datenbank setzen:

```sql
UPDATE benutzer SET passwort_hash = '<der erzeugte Hash>'
WHERE benutzername = 'admin';
```

---

## Betrieb

| Aufgabe | Befehl |
|---|---|
| Zustand | `systemctl status monitoring-dashboard` |
| Protokoll | `journalctl -u monitoring-dashboard -f` |
| Neu starten | `systemctl restart monitoring-dashboard` |
| Aktualisieren | `cd /opt/monitoring && git pull && systemctl restart monitoring-dashboard` |

Die Datensicherung sollte die Datenbank und die Datei `.env` umfassen:

```bash
mariadb-dump monitoring | gzip > /var/backups/monitoring-$(date +%F).sql.gz
```

## Haeufige Stoerungen

| Beobachtung | Ursache |
|---|---|
| 502 Bad Gateway | Dienst laeuft nicht, siehe `journalctl` |
| Anmeldeseite erscheint wiederholt | `SITZUNG_SCHLUESSEL` fehlt in `.env` |
| Quellen dauerhaft `gestoert` | ausgehende Verbindungen gesperrt oder Adresse veraltet |
| Cookie wird nicht gesetzt | `COOKIE_SICHER=true` ohne HTTPS |
