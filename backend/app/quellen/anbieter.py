"""Konkrete Versionsquellen.

Jede Quelle liefert eine Versionsinfo. Der Aufrufer kennt die Besonderheiten
der einzelnen Anbieter nicht; eine neue Quelle laesst sich ergaenzen, ohne
die uebrige Anwendung zu aendern.
"""

import logging
from datetime import date, datetime

from app import config
from app.quellen.basis import (
    Quelle,
    QuellenFehler,
    Versionsinfo,
    bereinige_version,
    erkenne_sicherheitsupdate,
    hole_json,
    ist_vorabversion,
)

log = logging.getLogger(__name__)


def _datum(roh: str | None) -> date | None:
    if not roh:
        return None
    for muster in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(roh[:19] if "T" in roh else roh, muster).date()
        except ValueError:
            continue
    return None


class GithubQuelle(Quelle):
    """Liest den letzten Release eines GitHub-Projektes.

    Kennung: 'eigentuemer/projekt', z. B. 'nextcloud/server'.
    """

    typ = "github"
    BASIS = "https://api.github.com/repos/{kennung}/releases"

    def _kopfzeilen(self) -> dict:
        kopf = {"Accept": "application/vnd.github+json"}
        if config.GITHUB_TOKEN:
            kopf["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
        return kopf

    def ermittle(self, kennung: str | None) -> Versionsinfo:
        if not kennung:
            raise QuellenFehler("Fuer die Quelle 'github' fehlt die Kennung.")

        # Nicht /releases/latest: dieser Endpunkt liefert bei manchen Projekten
        # einen aelteren Stand. Stattdessen die Liste holen und Vorabversionen
        # selbst aussortieren.
        daten = hole_json(self.BASIS.format(kennung=kennung) + "?per_page=20",
                          self._kopfzeilen())
        if not isinstance(daten, list) or not daten:
            raise QuellenFehler(f"Keine Releases fuer {kennung} gefunden.")

        for eintrag in daten:
            if eintrag.get("draft") or eintrag.get("prerelease"):
                continue
            version = bereinige_version(eintrag.get("tag_name") or eintrag.get("name") or "")
            if not version or ist_vorabversion(version):
                continue
            return Versionsinfo(
                verfuegbare_version=version,
                veroeffentlicht_am=_datum(eintrag.get("published_at")),
                ist_sicherheitsupdate=erkenne_sicherheitsupdate(
                    eintrag.get("name"), eintrag.get("body")
                ),
                changelog_url=eintrag.get("html_url"),
            )
        raise QuellenFehler(f"Kein stabiler Release fuer {kennung} gefunden.")


class EndoflifeQuelle(Quelle):
    """Liest Version und Supportende von endoflife.date.

    Kennung: Produktname, z. B. 'mariadb', 'php', 'nextcloud'.
    Die Schnittstelle befindet sich im Beta-Status, daher wird die Antwort
    defensiv ausgewertet und die aeltere, stabilere Fassung als Rueckfall
    verwendet.
    """

    typ = "endoflife"
    NEU = "https://endoflife.date/api/v1/products/{kennung}/"
    ALT = "https://endoflife.date/api/{kennung}.json"

    def ermittle(self, kennung: str | None) -> Versionsinfo:
        if not kennung:
            raise QuellenFehler("Fuer die Quelle 'endoflife' fehlt die Kennung.")
        try:
            daten = hole_json(self.NEU.format(kennung=kennung))
            zyklen = (daten.get("result") or {}).get("releases") or daten.get("releases")
        except Exception:
            daten = hole_json(self.ALT.format(kennung=kennung))
            zyklen = daten if isinstance(daten, list) else None

        if not zyklen:
            raise QuellenFehler(f"Keine Versionsdaten fuer {kennung}.")

        eintrag = zyklen[0]
        version = bereinige_version(
            str(eintrag.get("latest") or eintrag.get("name") or eintrag.get("cycle") or "")
        )
        if not version:
            raise QuellenFehler(f"Keine Version in der Antwort fuer {kennung}.")

        return Versionsinfo(
            verfuegbare_version=version,
            veroeffentlicht_am=_datum(
                str(eintrag.get("latestReleaseDate") or eintrag.get("releaseDate") or "")
            ),
            ist_sicherheitsupdate=False,  # Quelle liefert keine Einstufung
            changelog_url=f"https://endoflife.date/{kennung}",
        )


class PhpQuelle(Quelle):
    """Offizielle Versionsliste von php.net."""

    typ = "php"
    URL = "https://www.php.net/releases/index.php?json=1&max=1"

    def ermittle(self, kennung: str | None = None) -> Versionsinfo:
        daten = hole_json(self.URL)
        if not isinstance(daten, dict) or not daten:
            raise QuellenFehler("Unerwartete Antwort von php.net.")
        zweig = sorted(daten.keys())[-1]
        eintrag = daten[zweig] or {}
        version = bereinige_version(str(eintrag.get("version") or ""))
        if not version:
            raise QuellenFehler("Keine Version in der Antwort von php.net.")
        return Versionsinfo(
            verfuegbare_version=version,
            veroeffentlicht_am=_datum(str(eintrag.get("date") or "")),
            changelog_url="https://www.php.net/ChangeLog-8.php",
        )


class ManuelleQuelle(Quelle):
    """Fuer Systeme ohne offene Schnittstelle, z. B. Windows Server.

    Die verfuegbare Version wird durch einen Administrator gepflegt; ein
    automatischer Abruf findet nicht statt.
    """

    typ = "manuell"

    def ermittle(self, kennung: str | None = None) -> Versionsinfo:
        raise QuellenFehler("Manuelle Quelle: kein automatischer Abruf vorgesehen.")


_QUELLEN: dict[str, Quelle] = {
    q.typ: q() for q in (GithubQuelle, EndoflifeQuelle, PhpQuelle, ManuelleQuelle)
}


def hole_quelle(typ: str) -> Quelle:
    quelle = _QUELLEN.get(typ)
    if quelle is None:
        raise QuellenFehler(f"Unbekannter Quellentyp: {typ}")
    return quelle
