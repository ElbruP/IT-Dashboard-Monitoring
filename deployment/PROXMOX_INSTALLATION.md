# Bereitstellung auf einer virtuellen Maschine (Proxmox VE)

Anleitung fuer die Projektumsetzung. Jeder mit **(S)** gekennzeichnete
Schritt eignet sich als Bildschirmfoto fuer den Anhang der
Projektdokumentation.

**Zeitrahmen:** rund 12 Stunden gemaess Projektantrag, aufgeteilt in
Abschnitt A (4 h), B (4 h), C (2 h) und D (2 h).

---

# Abschnitt A – Virtuelle Maschine und Grundsystem (rund 4 h)

## A.1 Ressourcen festlegen

Vor dem Anlegen der Maschine wird der Bedarf begruendet. Diese Begruendung
gehoert in die Dokumentation, nicht nur die gewaehlten Werte.

| Ressource | Wert | Begruendung |
|---|---|---|
| vCPU | 2 | Die Abfrage der Quellen erfolgt nacheinander; entscheidend ist die Wartezeit auf die Anbieter, nicht die Rechenleistung. |
| Arbeitsspeicher | 4 GB | MariaDB rund 1 GB, Anwendung und nginx rund 0,5 GB, Rest als Reserve fuer den Dateisystem-Zwischenspeicher. |
| Festplatte | 32 GB | Betriebssystem rund 3 GB. Die Tabelle `meldungen` waechst bei rund 20 Quellen um etwa 50 MB im Jahr. |
| Netzwerkkarte | VirtIO | Paravirtualisiert, dadurch geringere Last als bei emulierter Hardware. |
| Festplattenanbindung | VirtIO SCSI single | Empfehlung von Proxmox, unterstuetzt Discard und IO-Thread. |

## A.2 Installationsabbild bereitstellen

Im Proxmox-Web (Datacenter → Storage → *local* → ISO Images) das
Netzinstallations-Abbild von Debian 12 hochladen oder ueber
*Download from URL* beziehen. **(S)**

## A.3 Virtuelle Maschine anlegen

*Create VM* mit folgenden Angaben: **(S)**

- **General:** Name `srv-itinfo`, VM ID notieren
- **OS:** hochgeladenes ISO, Typ Linux, Version 6.x
- **System:** Machine `q35`, BIOS `OVMF (UEFI)`, EFI-Datentraeger anlegen,
  Haken bei *Qemu Agent*
- **Disks:** Bus `SCSI`, Controller `VirtIO SCSI single`, 32 GB,
  Haken bei *Discard* und *IO thread*
- **CPU:** 2 Kerne, Typ `host`
- **Memory:** 4096 MB, Ballooning abschalten (die Datenbank reagiert
  empfindlich auf schwankenden Speicher)
- **Network:** Bridge `vmbr0`, Modell `VirtIO`, gegebenenfalls VLAN-Kennung
  des Servernetzes

## A.4 Debian installieren

VM starten, Konsole oeffnen, *Install* waehlen. **(S)**

- Sprache Deutsch, Land Deutschland, Tastatur Deutsch
- Rechnername `srv-itinfo`, Domain nach interner Vorgabe
- Kennwort fuer `root` vergeben, zusaetzlich einen persoenlichen Benutzer
- **Partitionierung:** gefuehrt, gesamte Festplatte, *Alle Dateien auf eine
  Partition*. Fuer eine Maschine mit einem Dienst ist eine Aufteilung nicht
  erforderlich; ein eigener Datentraeger fuer die Datenbank waere
  Aufwand ohne Nutzen.
- **Softwareauswahl:** nur *SSH-Server* und *Standard-Systemwerkzeuge*.
  Keine grafische Oberflaeche: sie vergroessert die Angriffsflaeche und
  belegt Ressourcen ohne Zweck. **(S)**

## A.5 Feste Adresse vergeben

Nach dem ersten Start:

```bash
ip -brief address show
nano /etc/network/interfaces
```

```
auto ens18
iface ens18 inet static
    address 192.168.x.y/24
    gateway 192.168.x.1
    dns-nameservers 192.168.x.1
```

```bash
systemctl restart networking
ip -brief address show          # (S) zeigt die vergebene Adresse
ping -c2 <Gateway>
```

Eine feste Adresse ist noetig, weil die Anwendung ueber einen
DNS-Eintrag erreichbar sein soll und ein Wechsel der Adresse den Zugriff
unterbrechen wuerde.

## A.6 Gastwerkzeuge und Grundpakete

```bash
apt update && apt upgrade -y
apt install -y qemu-guest-agent sudo curl git
systemctl enable --now qemu-guest-agent
```

Der Gast-Agent meldet Proxmox die Adresse der Maschine und ermoeglicht
ein sauberes Herunterfahren sowie konsistente Sicherungen. **(S)** –
in Proxmox ist die IP-Adresse nun in der Uebersicht sichtbar.

## A.7 Zugang absichern

```bash
usermod -aG sudo <benutzer>
```

Auf dem eigenen Arbeitsplatz einen Schluessel erzeugen und uebertragen:

```powershell
ssh-keygen -t ed25519
ssh-copy-id benutzer@192.168.x.y
```

Danach auf dem Server in `/etc/ssh/sshd_config`:

```
PermitRootLogin no
PasswordAuthentication no
```

```bash
systemctl restart ssh
```

Vor dem Trennen der Verbindung in einem **zweiten Fenster** pruefen, ob
die Anmeldung mit Schluessel funktioniert. Andernfalls sperrt man sich
aus. **(S)**

## A.8 Erster Sicherungspunkt

In Proxmox einen Snapshot `grundsystem` anlegen. **(S)**
Damit laesst sich bei einem Fehler in den folgenden Schritten ohne
Neuinstallation zuruecksetzen.

---

# Abschnitt B – Anwendung bereitstellen (rund 4 h)

## B.1 Pakete installieren

```bash
apt install -y python3-venv python3-pip mariadb-server nginx ufw
```

## B.2 Firewall

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
ufw status verbose          # (S)
```

Geoeffnet sind ausschliesslich 22, 80 und 443. Datenbank (3306) und
Anwendung (8000) sind von aussen nicht erreichbar; beide sind nur ueber
die lokale Schleife ansprechbar.

## B.3 Datenbank absichern

```bash
mariadb-secure-installation
```

Kennwort fuer `root` setzen, anonyme Benutzer entfernen, Anmeldung aus
der Ferne verbieten, Testdatenbank entfernen. **(S)**

## B.4 Projekt einspielen

```bash
adduser --system --group --home /opt/monitoring monitoring
cd /tmp
git clone https://github.com/BENUTZER/it-informationsplattform.git
cp -r it-informationsplattform/* /opt/monitoring/
chown -R monitoring:monitoring /opt/monitoring
```

## B.5 Schema und Datenbankbenutzer

In `datenbank/03_benutzer.sql` den Platzhalter durch ein eigenes Kennwort
ersetzen, dann:

```bash
cd /opt/monitoring
mariadb < datenbank/01_schema_monitoring.sql
mariadb < datenbank/03_benutzer.sql
mariadb < datenbank/04_erweiterung_benachrichtigung.sql
mariadb < datenbank/05_erweiterung_quellen_meldungen.sql

mariadb monitoring -e "SELECT bezeichnung, typ, zustand FROM v_quellenstatus;"   # (S)
mariadb monitoring -e "SHOW GRANTS FOR 'monitoring'@'localhost';"                # (S)
```

Der zweite Befehl belegt, dass die Anwendung keine strukturellen
Aenderungen vornehmen kann – ein Punkt, der im Fachgespraech regelmaessig
angesprochen wird.

## B.6 Laufzeitumgebung

```bash
python3 -m venv /opt/monitoring/venv
/opt/monitoring/venv/bin/pip install -r /opt/monitoring/backend/requirements.txt
```

## B.7 Konfiguration

```bash
cd /opt/monitoring/backend
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
nano .env
```

Zu setzen:

```
DB_USER=monitoring
DB_PASSWORT=<aus Schritt B.5>
SITZUNG_SCHLUESSEL=<erzeugter Wert>
COOKIE_SICHER=true
SIMULATION_AKTIV=false
GITHUB_TOKEN=<optional: erhoeht das Kontingent von 60 auf 5000 Anfragen je Stunde>
```

```bash
chown monitoring:monitoring .env
chmod 600 .env
ls -l .env                  # (S) zeigt die eingeschraenkten Rechte
```

## B.8 Dienst einrichten

```bash
cp /opt/monitoring/deployment/monitoring-dashboard.service /etc/systemd/system/
sed -i 's#/opt/monitoring-dashboard#/opt/monitoring#g' \
    /etc/systemd/system/monitoring-dashboard.service
systemctl daemon-reload
systemctl enable --now monitoring-dashboard
systemctl status monitoring-dashboard --no-pager     # (S)
curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/api/status
```

Erwartet wird `200`.

---

# Abschnitt C – Erreichbarkeit und Verschluesselung (rund 2 h)

## C.1 Reverse Proxy

```bash
cp /opt/monitoring/deployment/nginx-monitoring.conf \
   /etc/nginx/sites-available/monitoring
sed -i 's/BEISPIEL.DE/itinfo.firma.intern/g' /etc/nginx/sites-available/monitoring
ln -s /etc/nginx/sites-available/monitoring /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t                    # (S)
systemctl reload nginx
```

## C.2 Zertifikat

Die Entscheidung haengt davon ab, ob der Name oeffentlich aufloesbar ist:

**Fall 1 – interner Name (`itinfo.firma.intern`).** Let's Encrypt
funktioniert nicht, da die Verfuegungsberechtigung nicht nachweisbar ist.
Zwei Wege stehen offen:

- Zertifikat der internen Zertifizierungsstelle, sofern vorhanden. Dann
  vertrauen alle Arbeitsplaetze dem Zertifikat ohne Warnung.
- Selbst ausgestelltes Zertifikat. Der Browser warnt beim ersten Aufruf;
  dies ist in der Dokumentation zu benennen.

```bash
openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
  -keyout /etc/ssl/private/itinfo.key \
  -out /etc/ssl/certs/itinfo.crt \
  -subj "/CN=itinfo.firma.intern"
```

Danach in der nginx-Datei die beiden Pfade auf diese Dateien setzen.

**Fall 2 – oeffentlicher Name.** Dann ist Let's Encrypt moeglich:

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d itinfo.firma.de
systemctl list-timers | grep certbot          # (S) automatische Erneuerung
```

## C.3 DNS-Eintrag

Im internen DNS einen A-Eintrag auf die Adresse der Maschine anlegen.
**(S)** – Nachweis der Aufloesung:

```bash
nslookup itinfo.firma.intern
```

## C.4 Zugriff pruefen

Von einem Arbeitsplatz aus `https://itinfo.firma.intern` aufrufen. **(S)**

```bash
curl -Ik https://itinfo.firma.intern | head -3
```

---

# Abschnitt D – Inbetriebnahme und Test (rund 2 h)

## D.1 Kennwoerter aendern

```bash
/opt/monitoring/venv/bin/python -c \
  "import sys; sys.path.insert(0,'/opt/monitoring/backend'); \
   from app.sicherheit import erzeuge_hash; print(erzeuge_hash('NeuesKennwort'))"
```

```sql
UPDATE benutzer SET passwort_hash = '<Hash>' WHERE benutzername = 'admin';
```

Die Aenderung der Anfangskennwoerter gehoert in das Uebergabeprotokoll.

## D.2 Erste Erfassung

Anmelden, *Jetzt aktualisieren* auslösen. **(S)** – die Uebersicht
enthaelt danach echte Meldungen.

Im Reiter *Quellen* pruefen, welche Quellen antworten. **(S)** – eine
nicht erreichbare Quelle wird als `gestoert` gekennzeichnet und im
Protokoll mit Fehlertext gefuehrt. Genau dieses Verhalten ist im
Projektantrag als Erfolgskriterium genannt.

Fehlerhafte Adressen lassen sich ohne Aenderung am Programm anpassen:

```sql
UPDATE quellen SET adresse = '<neue Adresse>' WHERE bezeichnung = '<Name>';
UPDATE quellen SET aktiv = 0 WHERE bezeichnung = '<Name>';
```

## D.3 Zugriffsschutz nachweisen

Mit dem Konto `lesend` anmelden: die Schaltflaeche *Jetzt aktualisieren*
ist gesperrt, das Kennzeichnen einer Meldung wird abgelehnt. **(S)**

Zur Ergaenzung ohne Anmeldung:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://itinfo.firma.intern/api/uebersicht
```

Erwartet wird `401`. **(S)**

## D.4 Neustartfestigkeit

```bash
reboot
```

Nach dem Hochlauf ohne Eingriff pruefen:

```bash
systemctl status monitoring-dashboard mariadb nginx --no-pager   # (S)
```

Alle drei Dienste muessen `active (running)` melden.

## D.5 Datensicherung

Sicherung der Datenbank einrichten:

```bash
cat > /etc/cron.daily/monitoring-sicherung <<'EOF'
#!/bin/sh
mariadb-dump monitoring | gzip > /var/backups/monitoring-$(date +%F).sql.gz
find /var/backups -name 'monitoring-*.sql.gz' -mtime +30 -delete
EOF
chmod +x /etc/cron.daily/monitoring-sicherung
/etc/cron.daily/monitoring-sicherung && ls -lh /var/backups/    # (S)
```

Zusaetzlich in Proxmox eine Sicherung der gesamten Maschine einrichten
(Datacenter → Backup): woechentlich, Modus *Snapshot*, mindestens drei
Staende aufbewahren. **(S)**

Der Gast-Agent aus Schritt A.6 sorgt dafuer, dass die Dateisysteme
waehrend der Sicherung in einem einheitlichen Zustand sind.

## D.6 Abschliessender Snapshot

Snapshot `abnahmebereit` anlegen. **(S)**

---

# Uebersicht der Bildschirmfotos

| Nr. | Inhalt | Abschnitt |
|---|---|---|
| 1 | Anlegen der virtuellen Maschine | A.3 |
| 2 | Softwareauswahl bei der Installation | A.4 |
| 3 | Feste Adresse (`ip -brief address show`) | A.5 |
| 4 | Adresse in der Proxmox-Uebersicht (Gast-Agent) | A.6 |
| 5 | Anmeldung mit Schluessel, Kennwort abgeschaltet | A.7 |
| 6 | Firewall (`ufw status verbose`) | B.2 |
| 7 | Rechte des Datenbankbenutzers (`SHOW GRANTS`) | B.5 |
| 8 | Zustand der Quellen in der Datenbank | B.5 |
| 9 | Rechte der Datei `.env` | B.7 |
| 10 | Dienst aktiv (`systemctl status`) | B.8 |
| 11 | Pruefung der nginx-Konfiguration | C.1 |
| 12 | Aufruf ueber HTTPS im Browser | C.4 |
| 13 | Uebersicht nach der ersten Erfassung | D.2 |
| 14 | Reiter *Quellen* mit gestoerter Quelle | D.2 |
| 15 | Rolle `lesend`: Schaltflaechen gesperrt | D.3 |
| 16 | Alle Dienste nach Neustart aktiv | D.4 |
| 17 | Sicherung der Datenbank | D.5 |
| 18 | Sicherungsauftrag in Proxmox | D.5 |

Fuer den Anhang genuegen etwa acht bis zehn dieser Aufnahmen. Zu
bevorzugen sind jene, die eine Entscheidung belegen (Nummern 6, 7, 9, 14,
15), nicht jene, die lediglich einen Installationsassistenten zeigen.
