/* =====================================================================
   Datenzugriff
   Der Rest der Anwendung kennt weder Adressen noch Statuscodes.
   ===================================================================== */

const BASIS = "api";

/** Wird geworfen, wenn keine gueltige Sitzung besteht. */
class NichtAngemeldet extends Error {}

/** Wird geworfen, wenn die Rolle fuer eine Aktion nicht ausreicht. */
class NichtBerechtigt extends Error {}

async function hole(pfad, einstellungen = {}) {
    const antwort = await fetch(`${BASIS}/${pfad}`, {
        credentials: "same-origin",          // sendet das Sitzungs-Cookie mit
        headers: { "Accept": "application/json", ...(einstellungen.headers || {}) },
        ...einstellungen
    });

    if (antwort.status === 401) throw new NichtAngemeldet("Sitzung abgelaufen");
    if (antwort.status === 403) throw new NichtBerechtigt("Rolle reicht nicht aus");

    if (!antwort.ok) {
        const daten = await antwort.json().catch(() => ({}));
        throw new Error(daten.detail || `Server antwortete mit ${antwort.status}`);
    }
    return antwort.json();
}

const Api = {
    /** Saemtliche Kennzahlen und Auswertungen in einem Aufruf. */
    uebersicht(einheit = "tag", anzahl = 14) {
        return hole(`uebersicht?trend_einheit=${einheit}&trend_anzahl=${anzahl}`);
    },

    /** Versionsstand der Systeme. */
    systeme()         { return hole("systeme"); },

    /** Stoesst alle Pruefungen sofort an. */
    aktualisieren()   { return hole("aktualisieren", { method: "POST" }); },

    /** Bestaetigt eine Meldung. */
    quittieren(id)    { return hole(`alarme/${id}/quittieren`, { method: "POST" }); },

    /* --- Reiter --- */
    produkte()        { return hole("produkte"); },
    regeln()          { return hole("regeln"); },
    bericht()         { return hole("bericht"); },

    bereiche()        { return hole("bereiche"); },
    quellen()         { return hole("quellen"); },

    quellenprotokoll(nurFehler) {
        return hole(`quellen/protokoll?nur_fehler=${nurFehler ? "true" : "false"}`);
    },

    meldungen(filter = {}) {
        const p = new URLSearchParams();
        if (filter.bereich)     p.set("bereich", filter.bereich);
        if (filter.kategorie)   p.set("kategorie", filter.kategorie);
        if (filter.relevanz)    p.set("relevanz", filter.relevanz);
        if (filter.suche)       p.set("suche", filter.suche);
        if (filter.nurUngelesen) p.set("nur_ungelesen", "true");
        return hole(`meldungen?${p}`);
    },

    gelesen(id) { return hole(`meldungen/${id}/gelesen`, { method: "POST" }); },

    abmelden()        { return hole("abmeldung", { method: "POST" }); }
};
