"""Auswertungen fuer die Uebersichtsseite.

Die Rohdaten liegen in den Tabellen und Sichten. Dieser Dienst verdichtet
sie zu den Kennzahlen, die auf der Oberflaeche dargestellt werden. Die
Berechnung erfolgt bewusst hier und nicht im Frontend: so liefert die
Schnittstelle fertige Werte und die Darstellungslogik bleibt einfach.
"""

import logging
from datetime import date, datetime, timedelta

from app import db

log = logging.getLogger(__name__)

# Zuordnung der technischen Alarmarten zu den fachlichen Kategorien,
# die auf der Oberflaeche angezeigt werden.
KATEGORIEN = {
    ("version", "kritisch"): "Sicherheitswarnung",
    ("version", "warnung"): "Update",
    ("version", "info"): "Update",
    ("schwellwert", "kritisch"): "Schwellwert",
    ("schwellwert", "warnung"): "Schwellwert",
    ("schwellwert", "info"): "Schwellwert",
    ("verfuegbarkeit", "kritisch"): "Verfuegbarkeit",
    ("verfuegbarkeit", "warnung"): "Verfuegbarkeit",
    ("verfuegbarkeit", "info"): "Verfuegbarkeit",
}


def _kategorie(typ: str, stufe: str) -> str:
    return KATEGORIEN.get((typ, stufe), "Sonstiges")


def kennzahlen() -> dict:
    """Die Werte der Kachelreihe am oberen Rand."""
    meldungen = db.lese_einen("""
        SELECT
            (SELECT COUNT(*) FROM meldungen)                                 AS gesamt,
            (SELECT COUNT(*) FROM meldungen WHERE gelesen_am IS NULL)        AS ungelesen,
            (SELECT COUNT(*) FROM meldungen
              WHERE erfasst_am >= NOW() - INTERVAL 1 DAY)                    AS neu_24h,
            (SELECT COUNT(*) FROM meldungen
              WHERE gelesen_am IS NULL AND relevanz IN ('hoch','kritisch'))  AS handlungsbedarf,
            (SELECT COUNT(*) FROM meldungen
              WHERE gelesen_am IS NULL AND relevanz = 'kritisch')            AS kritisch,
            (SELECT COUNT(*) FROM meldungen
              WHERE relevanz = 'kritisch' AND erfasst_am >= NOW() - INTERVAL 1 DAY)
                                                                            AS kritisch_24h
    """)

    quellenzustand = db.lese_einen("""
        SELECT COUNT(*) AS gesamt,
               SUM(zustand = 'erreichbar') AS erreichbar,
               SUM(zustand IN ('gestoert','veraltet','auffaellig')) AS gestoert
        FROM v_quellenstatus WHERE aktiv = TRUE
    """)

    zahlen = db.lese_einen("""
        SELECT
            (SELECT COUNT(*) FROM alarme WHERE quittiert_am IS NULL)            AS offen,
            (SELECT COUNT(*) FROM alarme
              WHERE quittiert_am IS NULL AND ausgeloest_am >= NOW() - INTERVAL 1 DAY) AS offen_24h,
            (SELECT COUNT(*) FROM alarme
              WHERE quittiert_am IS NULL AND stufe = 'kritisch')                AS kritisch,
            (SELECT COUNT(*) FROM alarme
              WHERE quittiert_am IS NULL AND stufe = 'kritisch'
                AND ausgeloest_am >= NOW() - INTERVAL 1 DAY)                    AS kritisch_24h,
            (SELECT COUNT(*) FROM systeme WHERE aktiv = TRUE)                   AS systeme,
            (SELECT COUNT(*) FROM systeme
              WHERE aktiv = TRUE AND erstellt_am >= NOW() - INTERVAL 7 DAY)     AS systeme_neu
    """)

    # Eine Quelle gilt als erreichbar, wenn zu ihr in den letzten 24 Stunden
    # eine Pruefung gespeichert wurde. Systeme mit manueller Pflege besitzen
    # keine Quelle und werden nicht mitgezaehlt.
    quellen = db.lese_einen("""
        SELECT
            COUNT(*) AS gesamt,
            SUM(CASE WHEN letzte IS NOT NULL
                      AND letzte >= NOW() - INTERVAL 1 DAY THEN 1 ELSE 0 END) AS online
        FROM (
            SELECT s.system_id,
                   (SELECT MAX(v.geprueft_am) FROM versionspruefungen v
                     WHERE v.system_id = s.system_id) AS letzte
            FROM systeme s
            WHERE s.aktiv = TRUE AND s.quelle_typ <> 'manuell'
        ) AS q
    """)

    letzter = db.lese_einen("""
        SELECT GREATEST(
            COALESCE((SELECT MAX(geprueft_am) FROM versionspruefungen), '1970-01-01'),
            COALESCE((SELECT MAX(letzter_erfolg) FROM quellen), '1970-01-01')
        ) AS zeitpunkt
    """)

    return {
        "meldungen_gesamt": meldungen["gesamt"],
        "meldungen_ungelesen": meldungen["ungelesen"],
        "meldungen_neu_24h": meldungen["neu_24h"],
        "meldungen_handlungsbedarf": meldungen["handlungsbedarf"],
        "meldungen_kritisch": meldungen["kritisch"],
        "meldungen_kritisch_24h": meldungen["kritisch_24h"],
        "quellen_erreichbar": int(quellenzustand["erreichbar"] or 0),
        "quellen_gestoert": int(quellenzustand["gestoert"] or 0),
        "quellen_gesamt": int(quellenzustand["gesamt"] or 0),
        "meldungen_offen": zahlen["offen"],
        "meldungen_offen_24h": zahlen["offen_24h"],
        "meldungen_kritisch": zahlen["kritisch"],
        "meldungen_kritisch_24h": zahlen["kritisch_24h"],
        "systeme_gesamt": zahlen["systeme"],
        "systeme_neu": zahlen["systeme_neu"],
        "letzter_lauf": letzter["zeitpunkt"],
    }


def kritische_meldungen(grenze: int = 8) -> list[dict]:
    """Die dringendsten offenen Meldungen fuer die Tabelle links."""
    zeilen = db.lese_alle("""
        SELECT a.alarm_id, a.typ, a.stufe, a.meldung, a.ausgeloest_am,
               s.name AS system_name
        FROM alarme a
        JOIN systeme s ON s.system_id = a.system_id
        WHERE a.quittiert_am IS NULL
        ORDER BY FIELD(a.stufe, 'kritisch', 'warnung', 'info'), a.ausgeloest_am DESC
        LIMIT %s
    """, (grenze,))

    for zeile in zeilen:
        zeile["kategorie"] = _kategorie(zeile["typ"], zeile["stufe"])
    return zeilen


def trend(wochen: int = 8) -> list[dict]:
    """Anzahl der Meldungen je Kalenderwoche fuer die Verlaufskurve.

    Wochen ohne Meldungen liefert die Datenbank nicht mit. Wuerde man sie
    weglassen, entstuende eine verzerrte Kurve: die Abstaende zwischen den
    Punkten waeren unterschiedlich lang, ohne dass das erkennbar ist.
    Deshalb wird die vollstaendige Reihe erzeugt und fehlende Wochen mit
    dem Wert null aufgefuellt.
    """
    gemessen = db.lese_alle("""
        SELECT YEARWEEK(ausgeloest_am, 3) AS jahrwoche, COUNT(*) AS anzahl
        FROM alarme
        WHERE ausgeloest_am >= NOW() - INTERVAL %s WEEK
        GROUP BY jahrwoche
    """, (wochen,))
    nach_woche = {int(z["jahrwoche"]): int(z["anzahl"]) for z in gemessen}

    heute = date.today()
    reihe = []
    for versatz in range(wochen - 1, -1, -1):
        tag = heute - timedelta(weeks=versatz)
        jahr, kw, _ = tag.isocalendar()
        reihe.append({
            "jahrwoche": jahr * 100 + kw,
            "kalenderwoche": kw,
            "anzahl": nach_woche.get(jahr * 100 + kw, 0),
        })
    return reihe


def nach_system(grenze: int = 8) -> list[dict]:
    """Verteilung der offenen Meldungen auf die Systeme."""
    return db.lese_alle("""
        SELECT s.name AS system_name, COUNT(*) AS anzahl
        FROM alarme a
        JOIN systeme s ON s.system_id = a.system_id
        WHERE a.quittiert_am IS NULL
        GROUP BY s.system_id, s.name
        ORDER BY anzahl DESC
        LIMIT %s
    """, (grenze,))


def nach_kategorie() -> list[dict]:
    """Verteilung der offenen Meldungen auf die fachlichen Kategorien."""
    roh = db.lese_alle("""
        SELECT typ, stufe, COUNT(*) AS anzahl
        FROM alarme
        WHERE quittiert_am IS NULL
        GROUP BY typ, stufe
    """)

    gesammelt: dict[str, int] = {}
    for zeile in roh:
        schluessel = _kategorie(zeile["typ"], zeile["stufe"])
        gesammelt[schluessel] = gesammelt.get(schluessel, 0) + zeile["anzahl"]

    return [{"kategorie": k, "anzahl": v}
            for k, v in sorted(gesammelt.items(), key=lambda p: -p[1])]


def risiko() -> list[dict]:
    """Risikobewertung je System.

    Der Wert setzt sich additiv aus vier Bestandteilen zusammen und ist auf
    100 begrenzt. Die Gewichtung ist bewusst einfach gehalten und in der
    Dokumentation nachvollziehbar beschrieben:

        Versionsstand kritisch (Sicherheitsupdate)   40
        Versionsstand veraltet                       20
        je offener kritischer Alarm                  15
        je offener Warnungsalarm                      7
        Versionsstand unbekannt oder Pruefung alt    10
    """
    zeilen = db.lese_alle("""
        SELECT v.system_id, v.name, v.versionsstatus, v.geprueft_am,
               COALESCE(SUM(CASE WHEN a.stufe = 'kritisch' THEN 1 ELSE 0 END), 0) AS kritisch,
               COALESCE(SUM(CASE WHEN a.stufe = 'warnung'  THEN 1 ELSE 0 END), 0) AS warnung
        FROM v_systemstatus v
        LEFT JOIN alarme a
               ON a.system_id = v.system_id AND a.quittiert_am IS NULL
        GROUP BY v.system_id, v.name, v.versionsstatus, v.geprueft_am
    """)

    ergebnis = []
    for zeile in zeilen:
        wert = 0
        if zeile["versionsstatus"] == "kritisch":
            wert += 40
        elif zeile["versionsstatus"] == "update_verfuegbar":
            wert += 20
        elif zeile["versionsstatus"] == "unbekannt":
            wert += 10

        wert += int(zeile["kritisch"]) * 15
        wert += int(zeile["warnung"]) * 7

        veraltet = (zeile["geprueft_am"] is None
                    or (datetime.now() - zeile["geprueft_am"]).days > 7)
        if veraltet and zeile["versionsstatus"] != "unbekannt":
            wert += 10

        ergebnis.append({
            "system_name": zeile["name"],
            "versionsstatus": zeile["versionsstatus"],
            "wert": min(wert, 100),
        })

    ergebnis.sort(key=lambda e: -e["wert"])
    return ergebnis


def dringende_meldungen(grenze: int = 8) -> list[dict]:
    """Die Meldungen mit dem hoechsten Handlungsbedarf."""
    return db.lese_alle("""
        SELECT meldung_id, titel, kategorie, relevanz, cvss, bereich,
               system_name, quelle, verweis, veroeffentlicht_am, gelesen_am
        FROM v_meldungen
        WHERE gelesen_am IS NULL
        ORDER BY FIELD(relevanz,'kritisch','hoch','mittel','info'),
                 CASE WHEN veroeffentlicht_am IS NOT NULL
                       AND veroeffentlicht_am <= NOW()
                  THEN veroeffentlicht_am ELSE erfasst_am END DESC
        LIMIT %s
    """, (grenze,))


def meldungen_je_bereich() -> list[dict]:
    """Verteilung der offenen Meldungen auf die Themenbereiche."""
    return db.lese_alle("""
        SELECT b.name AS bereich,
               COUNT(m.meldung_id) AS anzahl,
               CAST(COALESCE(SUM(m.relevanz IN ('hoch','kritisch')), 0) AS UNSIGNED) AS dringend
        FROM bereiche b
        LEFT JOIN meldungen m
               ON m.bereich_id = b.bereich_id AND m.gelesen_am IS NULL
        GROUP BY b.bereich_id, b.name, b.sortierung
        ORDER BY b.sortierung
    """)


def meldungen_je_kategorie() -> list[dict]:
    return db.lese_alle("""
        SELECT kategorie, COUNT(*) AS anzahl
        FROM meldungen
        WHERE gelesen_am IS NULL
        GROUP BY kategorie
        ORDER BY anzahl DESC
    """)


def meldungstrend(einheit: str = "woche", anzahl: int = 8) -> list[dict]:
    """Erfasste Meldungen je Zeitabschnitt, als vollstaendige Reihe.

    Bei kurzen Zeitraeumen ist eine tageweise Darstellung aussagekraeftiger:
    viele Quellen liefern nur Meldungen der letzten Wochen, sodass eine
    Wochenreihe ueberwiegend aus Nullwerten bestuende.

    Fehlende Abschnitte werden mit null aufgefuellt. Wuerde man nur die
    Abschnitte mit Meldungen darstellen, waeren die Abstaende zwischen den
    Punkten unterschiedlich lang, ohne dass das erkennbar ist.
    """
    heute = date.today()

    if einheit == "tag":
        anzahl = min(max(anzahl, 3), 90)
        gemessen = db.lese_alle("""
            SELECT DATE(CASE WHEN veroeffentlicht_am IS NOT NULL
                                  AND veroeffentlicht_am <= NOW()
                             THEN veroeffentlicht_am ELSE erfasst_am END) AS abschnitt,
                   COUNT(*) AS anzahl
            FROM meldungen
            WHERE CASE WHEN veroeffentlicht_am IS NOT NULL
                            AND veroeffentlicht_am <= NOW()
                       THEN veroeffentlicht_am ELSE erfasst_am END
                  >= CURDATE() - INTERVAL %s DAY
            GROUP BY abschnitt
        """, (anzahl - 1,))
        nach_abschnitt = {z["abschnitt"]: int(z["anzahl"]) for z in gemessen}

        return [{
            "beschriftung": (heute - timedelta(days=v)).strftime("%d.%m."),
            "schluessel": (heute - timedelta(days=v)).isoformat(),
            "anzahl": nach_abschnitt.get(heute - timedelta(days=v), 0),
        } for v in range(anzahl - 1, -1, -1)]

    anzahl = min(max(anzahl, 2), 52)
    gemessen = db.lese_alle("""
        SELECT YEARWEEK(CASE WHEN veroeffentlicht_am IS NOT NULL
                       AND veroeffentlicht_am <= NOW()
                  THEN veroeffentlicht_am ELSE erfasst_am END, 3) AS jahrwoche,
               COUNT(*) AS anzahl
        FROM meldungen
        WHERE CASE WHEN veroeffentlicht_am IS NOT NULL
                       AND veroeffentlicht_am <= NOW()
                  THEN veroeffentlicht_am ELSE erfasst_am END >= NOW() - INTERVAL %s WEEK
        GROUP BY jahrwoche
    """, (anzahl,))
    nach_woche = {int(z["jahrwoche"]): int(z["anzahl"]) for z in gemessen}

    reihe = []
    for versatz in range(anzahl - 1, -1, -1):
        jahr, kw, _ = (heute - timedelta(weeks=versatz)).isocalendar()
        reihe.append({
            "beschriftung": f"KW {kw}",
            "schluessel": f"{jahr}-{kw:02d}",
            "kalenderwoche": kw,
            "anzahl": nach_woche.get(jahr * 100 + kw, 0),
        })
    return reihe


def uebersicht(trend_einheit: str = "woche",
               trend_anzahl: int = 8) -> dict:
    """Alle Auswertungen in einer Antwort."""
    return {
        "kennzahlen": kennzahlen(),
        "dringende_meldungen": dringende_meldungen(),
        "trend": meldungstrend(trend_einheit, trend_anzahl),
        "nach_bereich": meldungen_je_bereich(),
        "nach_kategorie": meldungen_je_kategorie(),
        "risiko": risiko(),
        # Die Schwellwertueberwachung bleibt als eigener Block erhalten.
        "schwellwertmeldungen": kritische_meldungen(5),
        "schwellwerte_je_system": nach_system(),
    }
