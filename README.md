# IT-Informationsplattform

[![Pruefung](https://github.com/USERNAME/it-informationsplattform/actions/workflows/pruefung.yml/badge.svg)](https://github.com/USERNAME/it-informationsplattform/actions/workflows/pruefung.yml)
[![Lizenz: MIT](https://img.shields.io/badge/Lizenz-MIT-blue.svg)](LICENSE)

Zentrale Erfassung und Aufbereitung von Hersteller-, Update- und
Sicherheitsmeldungen. Abschlussprojekt Fachinformatiker Systemintegration.

**Vorfuehrung:** https://USERNAME.github.io/it-informationsplattform/
(aufgezeichnete Daten, ohne Server und Datenbank)

> Vor dem ersten Hochladen `USERNAME` in dieser Datei und in
> `demo/index.html` durch den eigenen GitHub-Benutzernamen ersetzen.

## Struktur

```
monitoring-dashboard/
├── datenbank/
│   ├── 01_schema_monitoring.sql   Schema, Sichten, Testdaten
│   ├── 02_er_diagramm.mermaid     ER-Diagramm
│   ├── 03_benutzer.sql            Datenbankbenutzer mit Minimalrechten
│   ├── 04_erweiterung_benachrichtigung.sql
│   └── 05_erweiterung_quellen_meldungen.sql
├── backend/
│   ├── requirements.txt
│   ├── .env.example               Vorlage der Konfiguration
│   └── app/
│       ├── config.py              Konfiguration aus Umgebungsvariablen
│       ├── sicherheit.py          Anmeldung, bcrypt, Rollenpruefung
│       ├── db.py                  Datenbankzugriff
│       ├── api.py                 REST-Schnittstelle (FastAPI)
│       ├── zeitsteuerung.py       APScheduler
│       ├── quellen/               Anbindung der externen Quellen
│       │   ├── basis.py           Versionsvergleich, HTTP, Fehlerarten
│       │   ├── anbieter.py        GitHub, endoflife.date, php.net
│       │   └── feeds.py           RSS/Atom, NVD, Supportende
│       └── dienste/               Versionspruefung, Schwellwerte, Simulation
├── frontend/
│   ├── index.html                 Uebersichtsseite
│   ├── anmeldung.html             Anmeldung
│   ├── css/style.css              Gestaltung
│   └── js/
│       ├── api.js                 Zugriff auf die Schnittstelle
│       ├── diagramme.js           SVG-Diagramme ohne Bibliothek
│       ├── bereiche.js            Reiter Produkte, Meldungen, Regeln, Berichte
│       └── app.js                 Darstellung, Reiterwechsel, Aktualisierung
├── deployment/
│   ├── INSTALLATION_VMWARE.md     Bereitstellung Schritt fuer Schritt (angepasst)
│   ├── installieren.sh            fasst die wiederkehrenden Schritte zusammen
│   ├── nginx-monitoring-ip.conf   Reverse Proxy fuer Zugriff ueber IP-Adresse
│   ├── PROXMOX_INSTALLATION.md    Bereitstellung auf einer VM, Schritt fuer Schritt
│   ├── INSTALLATION.md            Kurzfassung fuer einen beliebigen Server
│   ├── monitoring-dashboard.service
│   └── nginx-monitoring.conf      Reverse Proxy mit TLS
├── demo/                          statische Vorfuehrung fuer GitHub Pages
└── .github/workflows/
    ├── pruefung.yml               automatische Pruefung bei jeder Aenderung
    └── vorfuehrung.yml            Veroeffentlichung der Vorfuehrung
```

## Lokal starten

```bash
mariadb < datenbank/01_schema_monitoring.sql
cd backend
python3 -m venv venv && . venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # Werte eintragen
uvicorn app.api:app --reload
```

Oberflaeche: http://localhost:8000 · Schnittstellendoku: http://localhost:8000/docs

## Auf dem Server einrichten

```bash
adduser --system --group --home /opt/monitoring-dashboard monitoring
# Projekt nach /opt/monitoring-dashboard kopieren
python3 -m venv /opt/monitoring-dashboard/venv
/opt/monitoring-dashboard/venv/bin/pip install -r backend/requirements.txt
mariadb < datenbank/01_schema_monitoring.sql
mariadb < datenbank/03_benutzer.sql        # Kennwort vorher setzen
chown -R monitoring:monitoring /opt/monitoring-dashboard
chmod 600 /opt/monitoring-dashboard/backend/.env
cp deployment/monitoring-dashboard.service /etc/systemd/system/
systemctl enable --now monitoring-dashboard
```

Der Dienst lauscht nur auf 127.0.0.1. Nach aussen wird ein Reverse Proxy
(nginx oder Apache) mit TLS vorgeschaltet; so ist der Anwendungsserver
selbst nicht direkt aus dem Netz erreichbar.

## Schnittstelle

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/api/uebersicht` | alle Kennzahlen und Auswertungen der Startseite |
| POST | `/api/aktualisieren` | Schaltflaeche "Jetzt aktualisieren" |
| GET | `/api/produkte` | Produkte samt Herkunft der Versionsangabe |
| GET | `/api/bereiche` | Themenbereiche mit Anzahl offener Meldungen |
| GET | `/api/meldungen` | Meldungen, filterbar nach Bereich, Kategorie, Relevanz, Text |
| POST | `/api/meldungen/{id}/gelesen` | Meldung als bearbeitet kennzeichnen |
| GET | `/api/quellen` | Betriebszustand aller Quellen |
| GET | `/api/quellen/protokoll` | Protokoll der Abfragen, auf Fehler filterbar |
| GET | `/api/regeln` | Schwellwerte mit letztem Messwert |
| GET | `/api/bericht` | Kennzahlen fuer den Berichtsreiter |
| GET | `/api/dashboard` | Systeme und Kennzahlen in einer Antwort |
| GET | `/api/systeme` | Versionsstand |
| GET | `/api/metriken` | Kennzahlen mit Schwellwertbewertung |
| GET | `/api/alarme` | offene bzw. alle Meldungen |
| GET | `/api/verlauf/{metrik_id}` | Messwerte fuer die Verlaufsdarstellung |
| POST | `/api/alarme/{id}/quittieren` | Meldung bestaetigen |
| POST | `/api/pruefung/versionen` | Pruefung ausserhalb des Zeitplans |
| POST | `/api/simulation` | Messwerte erzeugen |
| POST | `/api/anmeldung` | Anmeldung, setzt das Sitzungs-Cookie |
| POST | `/api/abmeldung` | Sitzung beenden |
| GET | `/api/ich` | angemeldeter Benutzer |
| POST | `/api/benachrichtigung` | offene Meldungen sofort versenden |
| GET | `/api/status` | Betriebszustand, 503 ohne Datenbank |

### Erforderliche Rolle

| Rolle | Rechte |
|---|---|
| `leser` | alle lesenden Endpunkte |
| `bearbeiter` | zusaetzlich Alarme quittieren |
| `admin` | zusaetzlich Pruefungen anstossen, Simulation, Versand |

Anfangskennwort beider Testkonten: `Start!2026` – **bei der Uebergabe aendern.**

## Angebundene Informationsquellen

| Art | Beispiele | Liefert |
|---|---|---|
| RSS/Atom | BSI CERT-Bund, Ubuntu Security Notices, Microsoft Security Update Guide, Proxmox-Ankuendigungen | Sicherheitshinweise, Versionsankuendigungen |
| NVD | Schwachstellensuche je Produkt (Nextcloud, VMware ESXi, Veeam, 3CX, Proxmox) | CVE mit CVSS-Bewertung |
| endoflife.date | je Produkt | Supportende, Produktabkuendigung |
| GitHub Releases | je Projekt | neue Versionen |

Die Adressen sind in der Tabelle `quellen` hinterlegt und lassen sich ohne
Aenderung am Programmcode anpassen. Eine nicht erreichbare Quelle wird im
Reiter "Quellen" ausgewiesen und im Protokoll festgehalten.

## Klassifizierung der Meldungen

**Kategorie** wird aus Titel und Text abgeleitet, in dieser Reihenfolge:
CVE, Supportende, Sicherheitswarnung, Update, sonst Produktinformation.

**Relevanz** richtet sich nach der CVSS-Bewertung, sofern der Anbieter eine
mitliefert: ab 9,0 kritisch, ab 7,0 hoch, ab 4,0 mittel. Ohne CVSS
entscheiden Kategorie und auffaellige Begriffe wie "zero-day" oder
"actively exploited".

## Bewusste Entscheidungen

- **Bewertung in Datenbanksichten.** `v_systemstatus` und `v_metrikstatus`
  liefern den Status bereits als `ok`, `warnung` oder `kritisch`. Die Logik
  ist damit an einer Stelle definiert; Oberflaeche und Benachrichtigung
  koennen nicht auseinanderlaufen.
- **Keine externen Ressourcen im Frontend.** Kein CDN, keine Bibliothek.
  Die Anwendung muss im internen Netz ohne Internetzugang bedienbar bleiben.
- **Ausfall einer Quelle erzeugt keinen Alarm.** Ein erschoepftes
  Anfragekontingent oder eine Netzstoerung wird protokolliert, aber nicht
  als Stoerung des ueberwachten Systems gemeldet.
- **Keine Alarmflut.** Ein bereits offener Alarm wird nicht wiederholt.
  Nur die Verschaerfung von `warnung` auf `kritisch` erzeugt einen weiteren
  Eintrag.
- **Alarme werden nicht geloescht,** sondern quittiert (`quittiert_am`,
  `quittiert_von`). Damit bleibt nachvollziehbar, wer wann reagiert hat.
- **Kennwoerter nur als bcrypt-Hash** (Kostenfaktor 12). Auch bei einem
  unbekannten Benutzernamen wird ein Hash geprueft, damit sich gueltige
  Konten nicht an der Antwortzeit erkennen lassen.
- **Signiertes Sitzungs-Cookie** mit `HttpOnly` und `SameSite=Lax`. Der
  Inhalt ist signiert, aber nicht verschluesselt: er enthaelt deshalb nur
  Kennung und Rolle, keine Berechtigungsnachweise.
- **E-Mails werden gebuendelt.** Alle offenen Meldungen eines Durchlaufs
  gehen in einer Nachricht heraus; `benachrichtigt_am` verhindert den
  erneuten Versand. Scheitert der Versand, bleibt das Feld leer und der
  naechste Durchlauf versucht es erneut – es geht keine Meldung verloren.
- **Feeds mit der Standardbibliothek ausgewertet.** RSS und Atom werden mit
  `xml.etree` gelesen. Eine zusaetzliche Abhaengigkeit waere fuer den
  Umfang nicht gerechtfertigt und muesste dauerhaft gepflegt werden.
- **Eine gestoerte Quelle erzeugt keine Meldung.** Sie wird im Reiter
  "Quellen" ausgewiesen und protokolliert. Andernfalls waere eine
  Netzstoerung nicht von einer echten Sicherheitsmeldung zu unterscheiden.
- **Meldungen werden nicht geloescht,** sondern als bearbeitet
  gekennzeichnet (`gelesen_am`, `gelesen_von`). Nur das technische
  Abfrageprotokoll wird nach 180 Tagen bereinigt.
- **Eindeutigkeit ueber (Quelle, externe Kennung).** Dieselbe Meldung wird
  bei wiederholtem Abruf nicht erneut gespeichert.
- **Diagramme als eigenes SVG statt Bibliothek.** Verlaufskurve,
  Ringdiagramm und Balken werden in `js/diagramme.js` selbst erzeugt. Eine
  Diagrammbibliothek waere nur ueber ein CDN oder als zusaetzlich zu
  pflegende Datei einzubinden gewesen; beides widerspricht der Vorgabe,
  ohne Internetzugang auszukommen.
- **Vollstaendige Wochenreihe in der Trendanalyse.** Die Datenbank liefert
  nur Wochen mit Meldungen. Wuerde man diese Luecken uebernehmen, waeren
  die Abstaende zwischen den Punkten unterschiedlich lang, ohne dass das
  erkennbar ist. Fehlende Wochen werden daher mit dem Wert null ergaenzt.
- **Herkunft jeder Versionsangabe ist nachvollziehbar.** Der Reiter
  "Produkte" nennt zu jedem System die Art der Quelle und verweist auf die
  Seite des Herstellers. Damit laesst sich jede Angabe pruefen, statt der
  Anwendung vertrauen zu muessen.
- **Risikobewertung je System.** Der Wert wird additiv gebildet
  (Sicherheitsupdate 40, veralteter Stand 20, je kritischer Alarm 15, je
  Warnung 7, unbekannter Stand 10) und auf 100 begrenzt. Die Gewichtung
  ist bewusst einfach und dadurch nachvollziehbar.
- **`SET NAMES utf8mb4` im Schemaskript.** Ohne diese Anweisung speichert
  der Client Zeichen wie `°C` doppelt kodiert.

## Offen

- [ ] Verwaltungsoberflaeche fuer Quellen, Produkte und Schwellwerte
- [ ] Zugangsschluessel fuer die NVD hinterlegen (hoeheres Kontingent)
- [ ] Auswahl des Zeitraums fuer die Trendanalyse
- [ ] Anbindung von BSI CERT-Bund und NVD zur Einstufung der Sicherheitsrelevanz
- [ ] Ersetzen der Simulation durch reale Messwertquellen

## Veroeffentlichung auf GitHub

```bash
git init
git add .
git commit -m "Grundgeruest: Datenbank, Backend, Anmeldung, Oberflaeche"
git branch -M main
git remote add origin https://github.com/USERNAME/it-informationsplattform.git
git push -u origin main
```

Anschliessend im Repository unter *Settings -> Pages* als Quelle
**GitHub Actions** auswaehlen. Der Ablauf `vorfuehrung.yml` stellt den
Ordner `demo/` danach automatisch bereit.

Die Datei `backend/.env` ist in `.gitignore` aufgefuehrt und gelangt nicht
in das Repository. Vor der Veroeffentlichung ist zu pruefen, dass in
`datenbank/03_benutzer.sql` kein produktives Kennwort steht.

## Automatische Pruefung

Bei jeder Aenderung laeuft `pruefung.yml` und prueft:

- Das Schema laesst sich in eine leere MariaDB einspielen.
- Die Sichten liefern die erwarteten Zustaende.
- Zeichen wie `Grad C` werden nicht doppelt kodiert gespeichert.
- Alle JavaScript-Dateien sind syntaktisch gueltig.
- Die Anwendung startet und antwortet auf allen Endpunkten.
- Ohne Anmeldung wird 401 geliefert, die Rolle `leser` erhaelt bei
  schreibenden Aufrufen 403.

Das Ergebnis eignet sich als Nachweis der Qualitaetssicherung im
Test- und Abnahmeprotokoll.

## Vorfuehrung neu aufzeichnen

Bei laufender Anwendung:

```bash
for pfad in uebersicht systeme produkte regeln bericht meldungen; do
  curl -s -b kekse.txt "localhost:8000/api/$pfad" > demo/daten/$pfad.json
done
```
