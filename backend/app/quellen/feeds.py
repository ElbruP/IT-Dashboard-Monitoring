"""Anbindung der Informationsquellen fuer Meldungen.

Die Auswertung der Feeds erfolgt mit der Standardbibliothek
(xml.etree.ElementTree). Eine zusaetzliche Abhaengigkeit waere fuer den
begrenzten Umfang nicht gerechtfertigt und muesste ueber die gesamte
Laufzeit des Systems gepflegt werden.
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from app import config
from app.quellen.basis import KontingentFehler, QuellenFehler

log = logging.getLogger(__name__)

# Namensraeume, die in Atom- und RSS-Feeds vorkommen.
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
}

CVE_MUSTER = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)

# Begriffe, aus denen die Kategorie einer Meldung abgeleitet wird.
# Die Reihenfolge ist bedeutsam: der erste Treffer gewinnt.
KATEGORIE_MUSTER = [
    ("cve", re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)),
    ("eol", re.compile(r"end[- ]of[- ](life|support)|abk[uü]ndigung|"
                       r"support\s?ende|extended support end", re.IGNORECASE)),
    ("sicherheitswarnung", re.compile(
        r"sicherheit|security|schwachstelle|vulnerabilit|advisory|"
        r"zero[- ]day|exploit|patch\s?day", re.IGNORECASE)),
    ("update", re.compile(r"\b(release|version|update|upgrade|"
                          r"ver[oö]ffentlich)", re.IGNORECASE)),
]

# Begriffe, die auf besonders dringenden Handlungsbedarf hinweisen.
DRINGEND = re.compile(
    r"zero[- ]day|aktiv ausgenutzt|actively exploited|"
    r"remote code execution|\bRCE\b|kritisch|critical|"
    r"privilege escalation", re.IGNORECASE)


@dataclass
class Rohmeldung:
    """Eine noch nicht bewertete Information aus einer Quelle."""
    externe_kennung: str
    titel: str
    zusammenfassung: str | None = None
    verweis: str | None = None
    veroeffentlicht_am: datetime | None = None
    kategorie: str | None = None
    cvss: float | None = None
    stichworte: list[str] = field(default_factory=list)


# --- Hilfsfunktionen ---------------------------------------------------

def _text(knoten, pfade: list[str]) -> str | None:
    """Liefert den Text des ersten gefundenen Unterknotens."""
    for pfad in pfade:
        gefunden = knoten.find(pfad, NS)
        if gefunden is not None:
            if gefunden.text and gefunden.text.strip():
                return gefunden.text.strip()
            # Atom-Verweise stehen im Attribut, nicht im Text
            if gefunden.get("href"):
                return gefunden.get("href")
    return None


def _bereinige(text: str | None, laenge: int = 600) -> str | None:
    """Entfernt Auszeichnungen und kuerzt auf eine lesbare Laenge."""
    if not text:
        return None
    ohne_tags = re.sub(r"<[^>]+>", " ", text)
    zusammengezogen = re.sub(r"\s+", " ", ohne_tags).strip()
    return zusammengezogen[:laenge] or None


def _datum(roh: str | None) -> datetime | None:
    if not roh:
        return None
    roh = roh.strip()
    try:                                    # RFC 822, uebliches RSS-Format
        return parsedate_to_datetime(roh).replace(tzinfo=None)
    except (TypeError, ValueError):
        pass
    for muster in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z",
                   "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(roh.replace("Z", "+0000"), muster) \
                           .replace(tzinfo=None)
        except ValueError:
            continue
    return None


def bestimme_kategorie(*texte: str | None) -> str:
    gesamt = " ".join(t for t in texte if t)
    for name, muster in KATEGORIE_MUSTER:
        if muster.search(gesamt):
            return name
    return "produktinformation"


def bestimme_relevanz(kategorie: str, cvss: float | None,
                      *texte: str | None) -> str:
    """Klassifizierung nach Handlungsbedarf.

    Liegt eine CVSS-Bewertung vor, richtet sich die Einstufung nach dieser
    Kennzahl; sie ist objektiver als jede eigene Regel. Andernfalls wird
    anhand der Kategorie und auffaelliger Begriffe eingestuft.
    """
    if cvss is not None:
        if cvss >= 9.0:
            return "kritisch"
        if cvss >= 7.0:
            return "hoch"
        if cvss >= 4.0:
            return "mittel"
        return "info"

    gesamt = " ".join(t for t in texte if t)
    if DRINGEND.search(gesamt):
        return "kritisch"
    if kategorie in ("cve", "sicherheitswarnung"):
        return "hoch"
    if kategorie == "eol":
        return "mittel"
    return "info"


def _kennung(*bestandteile: str | None) -> str:
    """Erzeugt eine stabile Kennung, wenn die Quelle keine mitliefert."""
    roh = "|".join(b or "" for b in bestandteile)
    return hashlib.sha256(roh.encode("utf-8")).hexdigest()[:40]


def _abrufen(url: str, kopfzeilen: dict | None = None) -> httpx.Response:
    kopf = {"User-Agent": "IT-Informationsplattform/1.0"}
    kopf.update(kopfzeilen or {})
    antwort = httpx.get(url, headers=kopf, timeout=config.HTTP_TIMEOUT,
                        follow_redirects=True)
    if antwort.status_code in (403, 429) and \
            antwort.headers.get("x-ratelimit-remaining") == "0":
        raise KontingentFehler("Anfragekontingent der Quelle erschoepft.")
    antwort.raise_for_status()
    return antwort


# --- RSS und Atom ------------------------------------------------------

def lies_feed(url: str, grenze: int = 40) -> tuple[list[Rohmeldung], int]:
    """Liest einen RSS- oder Atom-Feed.

    Beide Formate werden unterstuetzt, weil die Anbieter uneinheitlich
    sind: das BSI liefert RSS, andere Quellen Atom.
    """
    antwort = _abrufen(url, {"Accept": "application/rss+xml, application/xml"})

    try:
        wurzel = ElementTree.fromstring(antwort.content)
    except ElementTree.ParseError as fehler:
        raise QuellenFehler(f"Feed ist kein gueltiges XML: {fehler}") from fehler

    eintraege = wurzel.findall(".//item")                    # RSS
    if not eintraege:
        eintraege = wurzel.findall(".//atom:entry", NS)      # Atom
    if not eintraege:
        raise QuellenFehler("Feed enthaelt keine Eintraege.")

    meldungen = []
    for eintrag in eintraege[:grenze]:
        titel = _text(eintrag, ["title", "atom:title"])
        if not titel:
            continue

        verweis = _text(eintrag, ["link", "atom:link", "guid"])
        beschreibung = _bereinige(_text(eintrag, [
            "description", "atom:summary", "atom:content", "content:encoded"
        ]))
        veroeffentlicht = _datum(_text(eintrag, [
            "pubDate", "atom:updated", "atom:published", "dc:date"
        ]))

        # Bevorzugt die Kennung des Anbieters, sonst eine eigene aus
        # Verweis und Titel gebildete.
        kennung = _text(eintrag, ["guid", "atom:id"]) or _kennung(verweis, titel)

        cve = CVE_MUSTER.search(f"{titel} {beschreibung or ''}")
        meldungen.append(Rohmeldung(
            externe_kennung=kennung[:255],
            titel=titel[:300],
            zusammenfassung=beschreibung,
            verweis=verweis,
            veroeffentlicht_am=veroeffentlicht,
            stichworte=[cve.group(0).upper()] if cve else [],
        ))

    return meldungen, antwort.status_code


# --- Nationale Schwachstellendatenbank (NVD) ---------------------------

NVD_ADRESSE = "https://services.nvd.nist.gov/rest/json/cves/2.0"


def lies_nvd(suchbegriff: str, tage: int = 30,
             grenze: int = 40) -> tuple[list[Rohmeldung], int]:
    """Fragt Schwachstellen zu einem Produkt bei der NVD ab.

    Ohne Zugangsschluessel erlaubt die NVD nur wenige Anfragen je Zeitraum.
    Deshalb ist das Pruefintervall der NVD-Quellen bewusst gross gewaehlt.
    """
    ende = datetime.now(timezone.utc)
    beginn = ende - timedelta(days=tage)
    parameter = {
        "keywordSearch": suchbegriff,
        "resultsPerPage": grenze,
        "lastModStartDate": beginn.strftime("%Y-%m-%dT%H:%M:%S.000"),
        "lastModEndDate": ende.strftime("%Y-%m-%dT%H:%M:%S.000"),
    }
    frage = "&".join(f"{k}={httpx.URL(str(v)).raw_path.decode()}"
                     if False else f"{k}={v}" for k, v in parameter.items())
    antwort = _abrufen(f"{NVD_ADRESSE}?{frage}", {"Accept": "application/json"})

    daten = antwort.json()
    meldungen = []
    for eintrag in daten.get("vulnerabilities", [])[:grenze]:
        cve = eintrag.get("cve", {})
        kennung = cve.get("id")
        if not kennung:
            continue

        beschreibung = next(
            (b.get("value") for b in cve.get("descriptions", [])
             if b.get("lang") == "en"), None)

        # Hoechste verfuegbare CVSS-Bewertung ermitteln; die Version der
        # Metrik unterscheidet sich je nach Eintrag.
        punktwert = None
        metriken = cve.get("metrics", {})
        for schluessel in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            for messung in metriken.get(schluessel, []):
                wert = (messung.get("cvssData") or {}).get("baseScore")
                if wert is not None:
                    punktwert = max(punktwert or 0, float(wert))

        meldungen.append(Rohmeldung(
            externe_kennung=kennung,
            titel=f"{kennung}: {(beschreibung or '')[:240]}".strip(),
            zusammenfassung=_bereinige(beschreibung),
            verweis=f"https://nvd.nist.gov/vuln/detail/{kennung}",
            veroeffentlicht_am=_datum(cve.get("published")),
            kategorie="cve",
            cvss=punktwert,
            stichworte=[kennung],
        ))

    return meldungen, antwort.status_code


# --- endoflife.date: Supportende ---------------------------------------

def lies_endoflife(produkt: str) -> tuple[list[Rohmeldung], int]:
    """Erzeugt Meldungen zu bevorstehendem oder erreichtem Supportende."""
    antwort = _abrufen(f"https://endoflife.date/api/{produkt}.json",
                       {"Accept": "application/json"})
    zyklen = antwort.json()
    if not isinstance(zyklen, list):
        raise QuellenFehler("Unerwartete Antwort von endoflife.date.")

    heute = datetime.now().date()
    meldungen = []

    for zyklus in zyklen[:8]:
        eol = zyklus.get("eol")
        if not isinstance(eol, str):
            continue
        try:
            datum = datetime.strptime(eol, "%Y-%m-%d").date()
        except ValueError:
            continue

        tage = (datum - heute).days
        # Nur berichten, was tatsaechlich Handlungsbedarf ausloest:
        # bereits abgelaufen oder in den kommenden sechs Monaten.
        if tage > 180:
            continue

        bezeichnung = zyklus.get("cycle")
        abgelaufen = tage < 0
        titel = (f"{produkt} {bezeichnung}: Support "
                 f"{'ist am' if abgelaufen else 'endet am'} "
                 f"{datum.strftime('%d.%m.%Y')}"
                 f"{' abgelaufen' if abgelaufen else ''}")

        meldungen.append(Rohmeldung(
            externe_kennung=f"eol:{produkt}:{bezeichnung}",
            titel=titel[:300],
            zusammenfassung=(
                f"Letzte Version dieses Zyklus: {zyklus.get('latest', 'unbekannt')}. "
                f"{'Der Hersteller liefert keine Sicherheitsaktualisierungen mehr.' if abgelaufen else f'Verbleibende Zeit: {tage} Tage.'}"
            ),
            verweis=f"https://endoflife.date/{produkt}",
            # Bewusst kein Datum: die Meldung entsteht im Augenblick der
            # Erfassung. Das Supportende liegt haeufig in der Zukunft und
            # wuerde die Meldung sonst in eine kuenftige Kalenderwoche
            # einsortieren.
            veroeffentlicht_am=None,
            kategorie="eol",
        ))

    return meldungen, antwort.status_code


# --- GitHub-Releases ---------------------------------------------------

def lies_github(kennung: str, grenze: int = 10) -> tuple[list[Rohmeldung], int]:
    """Erzeugt Meldungen aus den letzten Releases eines Projektes."""
    kopf = {"Accept": "application/vnd.github+json"}
    if config.GITHUB_TOKEN:
        kopf["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"

    antwort = _abrufen(
        f"https://api.github.com/repos/{kennung}/releases?per_page={grenze}", kopf)

    meldungen = []
    for eintrag in antwort.json():
        if eintrag.get("draft"):
            continue
        bezeichnung = eintrag.get("tag_name") or eintrag.get("name") or ""
        beschreibung = _bereinige(eintrag.get("body"), 400)
        meldungen.append(Rohmeldung(
            externe_kennung=str(eintrag.get("id")),
            titel=f"{kennung.split('/')[-1]} {bezeichnung} veroeffentlicht"[:300],
            zusammenfassung=beschreibung,
            verweis=eintrag.get("html_url"),
            veroeffentlicht_am=_datum(eintrag.get("published_at")),
        ))

    return meldungen, antwort.status_code
