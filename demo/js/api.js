/* =====================================================================
   Datenzugriff der Vorfuehrung (GitHub Pages)
   Statt der REST-Schnittstelle werden zuvor aufgezeichnete Antworten aus
   dem Ordner daten/ gelesen. Die uebrige Anwendung ist unveraendert; sie
   kennt den Unterschied nicht. Schreibende Aufrufe werden angenommen,
   aber nicht ausgefuehrt.
   ===================================================================== */

class NichtAngemeldet extends Error {}
class NichtBerechtigt extends Error {}

const zwischenspeicher = {};

async function ladeDatei(name) {
    if (!zwischenspeicher[name]) {
        const antwort = await fetch(`daten/${name}.json`);
        if (!antwort.ok) throw new Error(`Datei ${name}.json nicht gefunden`);
        zwischenspeicher[name] = await antwort.json();
    }
    // Kopie zurueckgeben, damit Aenderungen die Aufzeichnung nicht veraendern
    return JSON.parse(JSON.stringify(zwischenspeicher[name]));
}

const Api = {
    async uebersicht() {
        const daten = await ladeDatei("uebersicht");
        daten.benutzer = { benutzername: "vorfuehrung", rolle: "leser" };
        return daten;
    },

    systeme()  { return ladeDatei("systeme"); },
    produkte() { return ladeDatei("produkte"); },
    regeln()   { return ladeDatei("regeln"); },
    bereiche() { return ladeDatei("bereiche"); },
    quellen()  { return ladeDatei("quellen"); },

    async quellenprotokoll(nurFehler) {
        const daten = await ladeDatei("protokoll");
        return { protokoll: nurFehler
            ? daten.protokoll.filter(l => !l.erfolgreich)
            : daten.protokoll };
    },
    bericht()  { return ladeDatei("bericht"); },

    async meldungen(filter = {}) {
        const daten = await ladeDatei("meldungen");
        let liste = daten.meldungen;
        if (filter.bereich)   liste = liste.filter(m => m.bereich === filter.bereich);
        if (filter.kategorie) liste = liste.filter(m => m.kategorie === filter.kategorie);
        if (filter.relevanz)  liste = liste.filter(m => m.relevanz === filter.relevanz);
        if (filter.nurUngelesen) liste = liste.filter(m => !m.gelesen_am);
        if (filter.suche) {
            const s = filter.suche.toLowerCase();
            liste = liste.filter(m =>
                m.titel.toLowerCase().includes(s) ||
                (m.zusammenfassung || "").toLowerCase().includes(s));
        }
        return { meldungen: liste };
    },

    gelesen() { throw new NichtBerechtigt("Vorfuehrung: nur lesend"); },

    // In der Vorfuehrung sind keine Aenderungen moeglich: die Daten sind
    // eine Aufzeichnung und es gibt keine Datenbank dahinter.
    aktualisieren() { throw new NichtBerechtigt("Vorfuehrung: nur lesend"); },
    quittieren()    { throw new NichtBerechtigt("Vorfuehrung: nur lesend"); },
    abmelden()      { return Promise.resolve(); }
};
