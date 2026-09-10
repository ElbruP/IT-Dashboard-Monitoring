# Bereitstellung auf der virtuellen Maschine

Angepasst an die vorhandene Umgebung:

| Angabe | Wert |
|---|---|
| Virtualisierung | VMware Workstation, Netzwerkmodus NAT |
| Netz | 192.168.220.0/24 |
| Adresse der Maschine | 192.168.220.50 |
| Gateway und DNS | 192.168.220.2 |
| Netzwerkkarte | ens33 |
| Netzverwaltung | NetworkManager |
| Zertifikat | selbst ausgestellt, auf die IP-Adresse ausgestellt |

Alle Befehle als `root`. Mit **(S)** gekennzeichnete Stellen eignen sich
als Bildschirmfoto fuer den Anhang der Projektdokumentation.

---

## 1 Netz pruefen

Vor allem anderen wird sichergestellt, dass die feste Adresse gesetzt ist
und Namensaufloesung funktioniert. Ohne DNS sind die Informationsquellen
nicht erreichbar.

```bash
ip -brief address show                # (S) 192.168.220.50/24 auf ens33
ip route                              # default via 192.168.220.2
ping -c2 192.168.220.2
ping -c2 1.1.1.1
getent hosts endoflife.date           # muss eine Adresse liefern
```

Falls die letzte Zeile nichts ausgibt, fehlt der Namensserver:

```bash
nmcli connection modify "Wired connection 1" ipv4.dns "192.168.220.2 1.1.1.1"
nmcli connection up "Wired connection 1"
```

Doppelte Netzverwaltung abschalten, damit sich die Konfiguration nicht
gegenseitig ueberschreibt:

```bash
systemctl disable --now networking 2>/dev/null || true
systemctl is-active NetworkManager    # active
```

---

## 2 Projekt auf die Maschine bringen

**Weg A – aus dem Repository** (bevorzugt, wenn bereits hochgeladen):

```bash
apt-get install -y git
cd /tmp
git clone https://github.com/BENUTZER/it-informationsplattform.git projekt
cd projekt
```

**Weg B – vom Windows-Rechner uebertragen**, falls das Repository noch
nicht besteht. In PowerShell auf dem Wirtsystem:

```powershell
cd C:\Projekt\it-monitoring-dashboard
scp -r monitoring-dashboard srv-itinfo@192.168.220.50:/tmp/projekt
```

Danach auf der Maschine:

```bash
cd /tmp/projekt
```

---

## 3 Einrichtung

Zuerst die Datenbank absichern. Dieser Schritt verlangt Eingaben und
bleibt deshalb bewusst manuell:

```bash
apt-get update && apt-get install -y mariadb-server
mariadb-secure-installation
```

Empfohlene Antworten:

| Frage | Antwort |
|---|---|
| Enter current password for root | Eingabetaste (noch keines gesetzt) |
| Switch to unix_socket authentication | n |
| Change the root password | Y, Kennwort vergeben und notieren |
| Remove anonymous users | Y |
| Disallow root login remotely | Y |
| Remove test database | Y |
| Reload privilege tables | Y |

**(S)** – Abschluss der Absicherung.

Danach die uebrigen Schritte ueber das beiliegende Skript:

```bash
bash deployment/installieren.sh
```

Das Skript fragt einmal nach einem Kennwort fuer den Datenbankbenutzer
`monitoring` und erledigt anschliessend:

1. Pakete nachinstallieren (Python, nginx, ufw)
2. Firewall einrichten – geoeffnet sind nur 22, 80 und 443 **(S)**
3. Dienstbenutzer `monitoring` anlegen, Projekt nach `/opt/monitoring` kopieren
4. Virtuelle Python-Umgebung erstellen und Abhaengigkeiten installieren
5. `.env` erzeugen, Sitzungsschluessel bilden, Rechte auf 600 setzen **(S)**
6. Alle vier Datenbankskripte einspielen und die Rechte ausgeben **(S)**
7. Systemdienst einrichten, starten und die Schnittstelle pruefen **(S)**

Erwartetes Ergebnis am Ende: `Dienst laeuft` und
`Schnittstelle antwortet mit 200`.

Bei einem Abbruch zeigt das Skript die letzten Zeilen des Protokolls.
Ausfuehrlicher:

```bash
journalctl -u monitoring-dashboard -n 50 --no-pager
```

---

## 4 Reverse Proxy einrichten

Das Zertifikat wurde bereits erstellt. Falls nicht, hier erneut:

```bash
openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
  -keyout /etc/ssl/private/itinfo.key \
  -out /etc/ssl/certs/itinfo.crt \
  -subj "/CN=192.168.220.50"
chmod 600 /etc/ssl/private/itinfo.key
```

Konfiguration uebernehmen:

```bash
cp /opt/monitoring/deployment/nginx-monitoring-ip.conf \
   /etc/nginx/sites-available/monitoring
ln -sf /etc/nginx/sites-available/monitoring /etc/nginx/sites-enabled/monitoring
rm -f /etc/nginx/sites-enabled/default

nginx -t                      # (S) muss "syntax is ok" und "test is successful" melden
systemctl reload nginx
```

Pruefen:

```bash
curl -Ik https://192.168.220.50 | head -3
curl -s -o /dev/null -w "%{http_code}\n" http://192.168.220.50    # 301
```

Der Schalter `-k` ist noetig, weil das Zertifikat selbst ausgestellt ist.

**Vom Windows-Rechner** im Browser `https://192.168.220.50` aufrufen. Es
erscheint eine Zertifikatswarnung; ueber *Erweitert* fortfahren. **(S)**

Diese Warnung gehoert in die Dokumentation: sie entsteht, weil kein
oeffentlich gueltiger Name vorliegt. Im Produktivbetrieb waere ein
Zertifikat der internen Zertifizierungsstelle oder ein oeffentlicher Name
mit Let's Encrypt vorzusehen. Das gehoert in den Ausblick.

---

## 5 Erste Inbetriebnahme

Anmelden mit `admin` / `Start!2026`.

Schaltflaeche **Jetzt aktualisieren** betaetigen. Die Anwendung fragt
alle 16 Quellen ab; der erste Durchlauf dauert bis zu einer Minute. **(S)**

Anschliessend den Reiter **Quellen** oeffnen. **(S)**

Nicht jede Quelle wird antworten. Anbieter aendern ihre Adressen; genau
dafuer gibt es die Zustandsanzeige. Eine gestoerte Quelle erzeugt keine
Meldung, sondern wird ausgewiesen und im Protokoll mit Fehlertext
gefuehrt – das ist ein Erfolgskriterium aus dem Projektantrag.

Adressen lassen sich ohne Aenderung am Programm anpassen:

```bash
mariadb monitoring -e \
  "UPDATE quellen SET adresse='<neue Adresse>' WHERE bezeichnung='<Name>';"

mariadb monitoring -e \
  "UPDATE quellen SET aktiv=0 WHERE bezeichnung='<Name>';"

mariadb monitoring -e \
  "SELECT bezeichnung, zustand, LEFT(letzter_fehler,60) AS fehler FROM v_quellenstatus;"
```

---

## 6 Kennwoerter aendern

Die Anfangskennwoerter sind vor der Abnahme zu ersetzen.

```bash
cd /opt/monitoring/backend
/opt/monitoring/venv/bin/python -c \
  "from app.sicherheit import erzeuge_hash; print(erzeuge_hash('NeuesKennwort'))"
```

Den ausgegebenen Hash eintragen:

```bash
mariadb monitoring -e \
  "UPDATE benutzer SET passwort_hash='<Hash>' WHERE benutzername='admin';"
```

Fuer `lesend` entsprechend wiederholen. Die Aenderung gehoert in das
Uebergabeprotokoll.

---

## 7 Zugriffsschutz nachweisen

Fuer das Test- und Abnahmeprotokoll:

```bash
# ohne Anmeldung
curl -sk -o /dev/null -w "ohne Anmeldung: %{http_code}\n" \
     https://192.168.220.50/api/uebersicht          # erwartet 401

# als lesend anmelden
curl -sk -c /tmp/leser.txt -X POST https://192.168.220.50/api/anmeldung \
     -H 'Content-Type: application/json' \
     -d '{"benutzername":"lesend","kennwort":"<Kennwort>"}' > /dev/null

# lesender Zugriff erlaubt
curl -sk -b /tmp/leser.txt -o /dev/null -w "lesend, Uebersicht: %{http_code}\n" \
     https://192.168.220.50/api/uebersicht          # erwartet 200

# schreibender Zugriff verweigert
curl -sk -b /tmp/leser.txt -o /dev/null -w "lesend, Pruefung: %{http_code}\n" \
     -X POST https://192.168.220.50/api/aktualisieren   # erwartet 403
```

**(S)** – die drei Zeilen mit 401, 200 und 403 sind ein guter Beleg im
Anhang.

Zusaetzlich in der Oberflaeche: mit `lesend` anmelden, die Schaltflaeche
*Jetzt aktualisieren* ist gesperrt. **(S)**

---

## 8 Neustartfestigkeit

```bash
reboot
```

Nach dem Hochlauf ohne jeden Eingriff:

```bash
systemctl status monitoring-dashboard mariadb nginx --no-pager | grep -E "●|Active"
```

**(S)** – alle drei Dienste `active (running)`.

---

## 9 Datensicherung

```bash
cat > /etc/cron.daily/monitoring-sicherung <<'EOF'
#!/bin/sh
mariadb-dump monitoring | gzip > /var/backups/monitoring-$(date +%F).sql.gz
find /var/backups -name 'monitoring-*.sql.gz' -mtime +30 -delete
EOF
chmod +x /etc/cron.daily/monitoring-sicherung

/etc/cron.daily/monitoring-sicherung
ls -lh /var/backups/monitoring-*.sql.gz          # (S)
```

Wiederherstellung im Ernstfall:

```bash
zcat /var/backups/monitoring-JJJJ-MM-TT.sql.gz | mariadb monitoring
```

Zusaetzlich in VMware einen Snapshot `abnahmebereit` anlegen. **(S)**

---

## 10 Betrieb

| Aufgabe | Befehl |
|---|---|
| Zustand | `systemctl status monitoring-dashboard` |
| Protokoll mitlesen | `journalctl -u monitoring-dashboard -f` |
| Neu starten | `systemctl restart monitoring-dashboard` |
| Aktualisieren | `cd /opt/monitoring && git pull && systemctl restart monitoring-dashboard` |
| Quellenzustand | `mariadb monitoring -e "SELECT bezeichnung, zustand FROM v_quellenstatus;"` |

### Haeufige Stoerungen

| Beobachtung | Ursache und Abhilfe |
|---|---|
| 502 Bad Gateway | Dienst laeuft nicht: `journalctl -u monitoring-dashboard -n 30` |
| Anmeldeseite erscheint wiederholt | `SITZUNG_SCHLUESSEL` fehlt in `.env` |
| Anmeldung nicht moeglich, Fehler 500 | Kennwort in `.env` stimmt nicht mit der Datenbank ueberein |
| Alle Quellen `gestoert` | keine Namensaufloesung: `getent hosts endoflife.date` |
| Nur GitHub gestoert | Anfragekontingent erschoepft, `GITHUB_TOKEN` in `.env` eintragen |
| Browser meldet Zertifikatsfehler | erwartet bei selbst ausgestelltem Zertifikat |

---

## Bildschirmfotos fuer den Anhang

| Nr. | Inhalt | Abschnitt |
|---|---|---|
| 1 | Feste Adresse auf ens33 | 1 |
| 2 | Absicherung der Datenbank | 3 |
| 3 | Firewall: nur 22, 80, 443 | 3 |
| 4 | Rechte des Datenbankbenutzers (`SHOW GRANTS`) | 3 |
| 5 | Rechte der Datei `.env` | 3 |
| 6 | Dienst aktiv | 3 |
| 7 | `nginx -t` erfolgreich | 4 |
| 8 | Oberflaeche ueber HTTPS im Browser | 4 |
| 9 | Uebersicht nach der ersten Erfassung | 5 |
| 10 | Reiter *Quellen* mit gestoerter Quelle | 5 |
| 11 | 401 / 200 / 403 im Zugriffstest | 7 |
| 12 | Alle Dienste nach dem Neustart aktiv | 8 |
| 13 | Datensicherung angelegt | 9 |

Acht bis zehn davon genuegen. Vorzuziehen sind jene, die eine
Entscheidung belegen (3, 4, 5, 10, 11), nicht jene, die einen
Installationsassistenten zeigen.
