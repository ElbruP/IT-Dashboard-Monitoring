"""REST-Schnittstelle und Auslieferung der Oberflaeche.

Die Antwortstruktur entspricht exakt der Datei mock/dashboard.json, mit der
die Oberflaeche entwickelt wurde. Dadurch genuegt im Frontend das Umstellen
der Konstante MOCK, ein Eingriff in die Darstellungslogik ist nicht noetig.
"""

import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from app import config, db, sicherheit, zeitsteuerung
from app.dienste import (
    auswertung, benachrichtigung, meldungserfassung, schwellwertpruefung,
    simulator, versionspruefung,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(name)s  %(message)s",
)
log = logging.getLogger(__name__)

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lebenszyklus(app: FastAPI):
    if not db.pruefe_erreichbarkeit():
        log.error("Start ohne Datenbankverbindung – Abrufe werden fehlschlagen.")
    zeitsteuerung.starte()
    yield
    zeitsteuerung.beende()


app = FastAPI(
    title="IT-Monitoring-Dashboard",
    description="Zentrale Erfassung von Hersteller-, Update- und Sicherheitsmeldungen",
    version="1.0.0",
    lifespan=lebenszyklus,
)

if not config.SITZUNG_SCHLUESSEL:
    # Ohne festen Schluessel waeren alle Benutzer nach jedem Neustart
    # abgemeldet. Im Betrieb ist der Schluessel daher zwingend zu setzen.
    log.warning("SITZUNG_SCHLUESSEL ist nicht gesetzt – es wird ein "
                "temporaerer Schluessel verwendet.")

app.add_middleware(
    SessionMiddleware,
    secret_key=config.SITZUNG_SCHLUESSEL or secrets.token_urlsafe(48),
    session_cookie="monitoring_sitzung",
    max_age=config.SITZUNG_DAUER_MIN * 60,
    https_only=config.COOKIE_SICHER,
    same_site="lax",  # verhindert das Mitsenden bei Aufrufen von fremden Seiten
)

# Abkuerzungen fuer die Zugriffspruefung
NUR_ANGEMELDET = Depends(sicherheit.aktueller_benutzer)
NUR_BEARBEITER = Depends(sicherheit.erfordert_rolle("bearbeiter"))
NUR_ADMIN = Depends(sicherheit.erfordert_rolle("admin"))


class Anmeldedaten(BaseModel):
    benutzername: str
    kennwort: str


# --- Anmeldung ---------------------------------------------------------

@app.post("/api/anmeldung", tags=["Anmeldung"])
def anmeldung(daten: Anmeldedaten, request: Request):
    benutzer = sicherheit.melde_an(daten.benutzername, daten.kennwort)
    if not benutzer:
        # Bewusst keine Unterscheidung zwischen unbekanntem Benutzer und
        # falschem Kennwort: das erschwert das Erraten gueltiger Konten.
        raise HTTPException(status_code=401,
                            detail="Benutzername oder Kennwort ist falsch.")
    sicherheit.setze_sitzung(request, benutzer)
    return benutzer


@app.post("/api/abmeldung", tags=["Anmeldung"])
def abmeldung(request: Request):
    request.session.clear()
    return {"abgemeldet": True}


@app.get("/api/ich", tags=["Anmeldung"])
def ich(benutzer: dict = NUR_ANGEMELDET):
    """Liefert den angemeldeten Benutzer; vom Frontend beim Laden aufgerufen."""
    return benutzer


def _aufbereiten(zeile: dict) -> dict:
    """Wandelt Datenbanktypen in Werte, die sich als JSON uebertragen lassen."""
    ergebnis = {}
    for schluessel, wert in zeile.items():
        if isinstance(wert, Decimal):
            ergebnis[schluessel] = float(wert)
        elif isinstance(wert, datetime):
            ergebnis[schluessel] = wert.strftime("%Y-%m-%d %H:%M:%S")
        elif hasattr(wert, "isoformat"):
            ergebnis[schluessel] = wert.isoformat()
        else:
            ergebnis[schluessel] = wert
    return ergebnis


def _liste(sql: str, parameter: tuple = ()) -> list[dict]:
    return [_aufbereiten(z) for z in db.lese_alle(sql, parameter)]


# --- Lesende Endpunkte -------------------------------------------------

@app.get("/api/systeme", tags=["Uebersicht"])
def systeme(benutzer: dict = NUR_ANGEMELDET):
    """Versionsstand aller aktiven Systeme."""
    return {"systeme": _liste("SELECT * FROM v_systemstatus ORDER BY name")}


@app.get("/api/metriken", tags=["Uebersicht"])
def metriken(benutzer: dict = NUR_ANGEMELDET):
    """Letzter Messwert je Kennzahl inklusive Schwellwertbewertung."""
    return {"metriken": _liste(
        "SELECT * FROM v_metrikstatus ORDER BY system_name, metrik"
    )}


@app.get("/api/dashboard", tags=["Uebersicht"])
def dashboard(benutzer: dict = NUR_ANGEMELDET):
    """Beide Uebersichten in einer Antwort – spart dem Frontend einen Aufruf."""
    return {
        "systeme": _liste("SELECT * FROM v_systemstatus ORDER BY name"),
        "metriken": _liste("SELECT * FROM v_metrikstatus ORDER BY system_name, metrik"),
    }


@app.get("/api/uebersicht", tags=["Uebersicht"])
def uebersicht(trend_einheit: str = "tag", trend_anzahl: int = 14,
               benutzer: dict = NUR_ANGEMELDET):
    """Alle verdichteten Kennzahlen der Uebersichtsseite in einer Antwort.

    Der Zeitraum der Verlaufskurve laesst sich waehlen. Voreingestellt sind
    14 Tage: viele Quellen liefern nur Meldungen der juengsten Zeit, sodass
    eine Wochenreihe ueberwiegend leer waere.
    """
    if trend_einheit not in ("tag", "woche"):
        trend_einheit = "tag"
    daten = auswertung.uebersicht(trend_einheit, trend_anzahl)
    daten["kennzahlen"] = _aufbereiten(daten["kennzahlen"])
    for schluessel in ("dringende_meldungen", "trend", "nach_bereich",
                       "nach_kategorie", "risiko", "schwellwertmeldungen",
                       "schwellwerte_je_system"):
        daten[schluessel] = [_aufbereiten(z) for z in daten[schluessel]]
    daten["auftraege"] = zeitsteuerung.auftraege()
    daten["benutzer"] = benutzer
    return daten


@app.post("/api/aktualisieren", tags=["Wartung"])
def aktualisieren(benutzer: dict = NUR_BEARBEITER):
    """Fuehrt alle Pruefungen sofort aus.

    Bedient die Schaltflaeche "Jetzt aktualisieren". Der Aufruf ersetzt den
    Zeitplan nicht, sondern ergaenzt ihn fuer den Fall, dass ein Ergebnis
    sofort benoetigt wird.
    """
    ergebnis = {}
    if config.SIMULATION_AKTIV:
        ergebnis["messwerte"] = simulator.erzeuge_messwerte()
    ergebnis["quellen"] = vars(meldungserfassung.erfasse_alle(alle=True))
    ergebnis["versionen"] = vars(versionspruefung.pruefe_alle())
    ergebnis["schwellwerte"] = vars(schwellwertpruefung.pruefe_alle())
    return ergebnis


# --- Reiter der Oberflaeche -------------------------------------------

# Adresse, unter der die Versionsinformation eines Systems nachvollzogen
# werden kann. Der Anwender soll pruefen koennen, woher eine Angabe stammt.
def _quellenadresse(typ: str, kennung: str | None) -> str | None:
    if not kennung and typ != "php":
        return None
    return {
        "github": f"https://github.com/{kennung}/releases",
        "endoflife": f"https://endoflife.date/{kennung}",
        "php": "https://www.php.net/releases/",
    }.get(typ)


QUELLENBESCHREIBUNG = {
    "github": "GitHub Releases-API",
    "endoflife": "endoflife.date",
    "php": "php.net",
    "rss": "RSS-Feed des Herstellers",
    "manuell": "manuelle Pflege durch die Administration",
}


@app.get("/api/produkte", tags=["Reiter"])
def produkte(benutzer: dict = NUR_ANGEMELDET):
    """Alle ueberwachten Produkte samt Herkunft der Versionsangabe."""
    zeilen = _liste("""
        SELECT s.system_id, s.name, s.hersteller, k.bezeichnung AS kategorie,
               s.hostname, s.ip_adresse, s.standort, s.installierte_version,
               s.quelle_typ, s.quelle_kennung, s.pruefintervall_min, s.aktiv,
               v.verfuegbare_version, v.versionsstatus, v.geprueft_am,
               v.ist_sicherheitsupdate
        FROM systeme s
        JOIN system_kategorien k ON k.kategorie_id = s.kategorie_id
        LEFT JOIN v_systemstatus v ON v.system_id = s.system_id
        ORDER BY s.name
    """)
    for zeile in zeilen:
        zeile["quelle_beschreibung"] = QUELLENBESCHREIBUNG.get(
            zeile["quelle_typ"], zeile["quelle_typ"])
        zeile["quelle_url"] = _quellenadresse(
            zeile["quelle_typ"], zeile["quelle_kennung"])
    return {"produkte": zeilen}


@app.get("/api/bereiche", tags=["Reiter"])
def bereiche(benutzer: dict = NUR_ANGEMELDET):
    """Themenbereiche mit der Anzahl offener Meldungen."""
    return {"bereiche": _liste("""
        SELECT b.bereich_id, b.name, b.beschreibung,
               COUNT(m.meldung_id) AS offen,
               CAST(COALESCE(SUM(m.relevanz IN ('hoch','kritisch')), 0) AS UNSIGNED) AS dringend
        FROM bereiche b
        LEFT JOIN meldungen m
               ON m.bereich_id = b.bereich_id AND m.gelesen_am IS NULL
        GROUP BY b.bereich_id, b.name, b.beschreibung, b.sortierung
        ORDER BY b.sortierung
    """)}


@app.get("/api/meldungen", tags=["Reiter"])
def meldungen(bereich: str | None = None, kategorie: str | None = None,
              relevanz: str | None = None, nur_ungelesen: bool = False,
              suche: str | None = None, grenze: int = 150,
              benutzer: dict = NUR_ANGEMELDET):
    """Erfasste Hersteller-, Update- und Sicherheitsmeldungen."""
    bedingungen, werte = [], []
    if bereich:
        bedingungen.append("bereich = %s"); werte.append(bereich)
    if kategorie:
        bedingungen.append("kategorie = %s"); werte.append(kategorie)
    if relevanz:
        bedingungen.append("relevanz = %s"); werte.append(relevanz)
    if nur_ungelesen:
        bedingungen.append("gelesen_am IS NULL")
    if suche:
        bedingungen.append("(titel LIKE %s OR zusammenfassung LIKE %s)")
        werte += [f"%{suche}%"] * 2

    wo = ("WHERE " + " AND ".join(bedingungen)) if bedingungen else ""
    werte.append(min(grenze, 500))

    return {"meldungen": _liste(f"""
        SELECT * FROM v_meldungen
        {wo}
        ORDER BY FIELD(relevanz,'kritisch','hoch','mittel','info'),
                 CASE WHEN veroeffentlicht_am IS NOT NULL
                       AND veroeffentlicht_am <= NOW()
                  THEN veroeffentlicht_am ELSE erfasst_am END DESC
        LIMIT %s
    """, tuple(werte))}


@app.post("/api/meldungen/{meldung_id}/gelesen", tags=["Reiter"])
def meldung_gelesen(meldung_id: int, benutzer: dict = NUR_BEARBEITER):
    """Kennzeichnet eine Meldung als bearbeitet.

    Die Meldung bleibt erhalten. Damit ist nachvollziehbar, wer wann auf
    welche Information reagiert hat.
    """
    betroffen = db.schreibe("""
        UPDATE meldungen SET gelesen_am = NOW(), gelesen_von = %s
        WHERE meldung_id = %s AND gelesen_am IS NULL
    """, (benutzer["benutzer_id"], meldung_id))
    if betroffen == 0:
        raise HTTPException(status_code=404,
                            detail="Meldung nicht gefunden oder bereits bearbeitet.")
    return {"meldung_id": meldung_id, "gelesen": True}


@app.get("/api/quellen", tags=["Reiter"])
def quellen(benutzer: dict = NUR_ANGEMELDET):
    """Betriebszustand aller angebundenen Informationsquellen."""
    return {"quellen": _liste("SELECT * FROM v_quellenstatus ORDER BY typ, bezeichnung")}


@app.get("/api/quellen/protokoll", tags=["Reiter"])
def quellenprotokoll(nur_fehler: bool = False, grenze: int = 100,
                     benutzer: dict = NUR_ANGEMELDET):
    """Protokoll der Quellenabfragen.

    Erfuellt die Anforderung, fehlerhafte Abfragen nachvollziehbar
    darzustellen.
    """
    wo = "WHERE l.erfolgreich = FALSE" if nur_fehler else ""
    return {"protokoll": _liste(f"""
        SELECT l.lauf_id, q.bezeichnung AS quelle, q.typ,
               l.gestartet_am, l.dauer_ms, l.erfolgreich, l.http_status,
               l.gefunden, l.neu, l.fehlertext
        FROM quellen_laeufe l
        JOIN quellen q ON q.quelle_id = l.quelle_id
        {wo}
        ORDER BY l.lauf_id DESC
        LIMIT %s
    """, (min(grenze, 500),))}


@app.get("/api/regeln", tags=["Reiter"])
def regeln(benutzer: dict = NUR_ANGEMELDET):
    """Die hinterlegten Schwellwerte mit dem jeweils letzten Messwert."""
    return {"regeln": _liste("""
        SELECT m.metrik_id, m.bezeichnung, m.einheit, m.beschreibung, m.aktiv,
               s.name AS system_name,
               w.richtung, w.grenze_warnung, w.grenze_kritisch,
               v.wert, v.status, v.gemessen_am
        FROM metriken m
        JOIN systeme s      ON s.system_id = m.system_id
        LEFT JOIN schwellwerte w ON w.metrik_id = m.metrik_id
        LEFT JOIN v_metrikstatus v ON v.metrik_id = m.metrik_id
        ORDER BY s.name, m.bezeichnung
    """)}


@app.get("/api/bericht", tags=["Reiter"])
def bericht(benutzer: dict = NUR_ANGEMELDET):
    """Kennzahlen fuer den Berichtsreiter, aufbereitet zum Ausdrucken."""
    daten = auswertung.uebersicht()
    offen = _liste("""
        SELECT s.name AS system_name, a.stufe, a.typ, a.meldung, a.ausgeloest_am
        FROM alarme a
        JOIN systeme s ON s.system_id = a.system_id
        WHERE a.quittiert_am IS NULL
        ORDER BY FIELD(a.stufe,'kritisch','warnung','info'), a.ausgeloest_am
    """)
    quittiert = db.lese_einen("""
        SELECT COUNT(*) AS anzahl,
               ROUND(AVG(TIMESTAMPDIFF(HOUR, ausgeloest_am, quittiert_am)), 1) AS stunden
        FROM alarme
        WHERE quittiert_am IS NOT NULL
          AND ausgeloest_am >= NOW() - INTERVAL 30 DAY
    """)
    return {
        "erstellt_am": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "kennzahlen": _aufbereiten(daten["kennzahlen"]),
        "risiko": [_aufbereiten(z) for z in daten["risiko"]],
        "offene_meldungen": offen,
        "bearbeitung": {
            "quittiert_30_tage": quittiert["anzahl"],
            "durchschnitt_stunden": float(quittiert["stunden"] or 0),
        },
    }


@app.get("/api/alarme", tags=["Alarme"])
def alarme(nur_offene: bool = True, grenze: int = 100,
           benutzer: dict = NUR_ANGEMELDET):
    sql = """
        SELECT a.alarm_id, a.typ, a.stufe, a.meldung, a.messwert,
               a.ausgeloest_am, a.quittiert_am, s.name AS system_name
        FROM alarme a
        JOIN systeme s ON s.system_id = a.system_id
        {bedingung}
        ORDER BY a.ausgeloest_am DESC
        LIMIT %s
    """.format(bedingung="WHERE a.quittiert_am IS NULL" if nur_offene else "")
    return {"alarme": _liste(sql, (min(grenze, 500),))}


@app.get("/api/verlauf/{metrik_id}", tags=["Uebersicht"])
def verlauf(metrik_id: int, stunden: int = 24,
            benutzer: dict = NUR_ANGEMELDET):
    """Messwerte einer Kennzahl fuer die Verlaufsdarstellung."""
    return {"messwerte": _liste("""
        SELECT wert, gemessen_am
        FROM messwerte
        WHERE metrik_id = %s AND gemessen_am >= NOW() - INTERVAL %s HOUR
        ORDER BY gemessen_am
    """, (metrik_id, min(stunden, 720)))}


# --- Schreibende Endpunkte ---------------------------------------------

@app.post("/api/alarme/{alarm_id}/quittieren", tags=["Alarme"])
def quittieren(alarm_id: int, benutzer: dict = NUR_BEARBEITER):
    """Bestaetigt einen Alarm.

    Der Alarm bleibt erhalten und wird nur als bearbeitet gekennzeichnet,
    damit nachvollziehbar bleibt, wer wann reagiert hat.
    """
    betroffen = db.schreibe("""
        UPDATE alarme
        SET quittiert_am = NOW(), quittiert_von = %s
        WHERE alarm_id = %s AND quittiert_am IS NULL
    """, (benutzer["benutzer_id"], alarm_id))

    if betroffen == 0:
        raise HTTPException(
            status_code=404,
            detail="Alarm nicht gefunden oder bereits quittiert.",
        )
    return {"alarm_id": alarm_id, "quittiert": True}


@app.post("/api/pruefung/versionen", tags=["Wartung"])
def pruefung_versionen(benutzer: dict = NUR_ADMIN):
    """Startet die Versionspruefung ausserhalb des Zeitplans (fuer Vorfuehrung)."""
    return vars(versionspruefung.pruefe_alle())


@app.post("/api/pruefung/schwellwerte", tags=["Wartung"])
def pruefung_schwellwerte(benutzer: dict = NUR_ADMIN):
    return vars(schwellwertpruefung.pruefe_alle())


@app.post("/api/simulation", tags=["Wartung"])
def simulation(benutzer: dict = NUR_ADMIN):
    return {"erzeugte_messwerte": simulator.erzeuge_messwerte()}


@app.post("/api/benachrichtigung", tags=["Wartung"])
def benachrichtigung_senden(benutzer: dict = NUR_ADMIN):
    """Versendet offene Meldungen sofort statt nach Zeitplan."""
    return vars(benachrichtigung.versende_offene())


# --- Betriebszustand ---------------------------------------------------

@app.get("/api/status", tags=["Wartung"])
def status():
    erreichbar = db.pruefe_erreichbarkeit()
    return JSONResponse(
        status_code=200 if erreichbar else 503,
        content={
            "datenbank": "erreichbar" if erreichbar else "nicht erreichbar",
            "auftraege": zeitsteuerung.auftraege(),
        },
    )


# --- Oberflaeche -------------------------------------------------------
# Muss zuletzt eingebunden werden, damit die API-Pfade Vorrang haben.

@app.middleware("http")
async def zwischenspeicher_steuern(request: Request, call_next):
    """Verhindert, dass der Browser eine alte Fassung anzeigt.

    Waehrend der Entwicklung fuehrt der Zwischenspeicher sonst dazu, dass
    geaenderte Stil- oder Skriptdateien nicht geladen werden, obwohl die
    Seite selbst bereits aktuell ist.
    """
    antwort = await call_next(request)
    if not request.url.path.startswith("/api"):
        antwort.headers["Cache-Control"] = "no-cache, must-revalidate"
    return antwort


if FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
else:  # pragma: no cover
    log.warning("Frontend-Verzeichnis nicht gefunden: %s", FRONTEND)
