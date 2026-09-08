/* =====================================================================
   Darstellung des Dashboards
   Aktualisierung per Polling; zusaetzlich manuell ueber die Schaltflaeche
   "Jetzt aktualisieren".
   ===================================================================== */

const INTERVALL_MS = 30000;

/* Farben der Kategorien im Ringdiagramm. Sie sind hier zentral definiert,
   damit Diagramm und Legende nicht auseinanderlaufen koennen. */
const KATEGORIEFARBEN = {
    "cve":                "#d92d20",
    "sicherheitswarnung": "#e8663c",
    "eol":                "#b45309",
    "update":             "#0d9488",
    "produktinformation": "#5b52c4",
    "sonstiges":          "#7b8697"
};

const KATEGORIETEXT = {
    "cve":                "CVE",
    "sicherheitswarnung": "Sicherheitswarnung",
    "eol":                "Supportende",
    "update":             "Update",
    "produktinformation": "Produktinformation",
    "sonstiges":          "Sonstiges"
};

/* Einstufung nach Handlungsbedarf. */
const RELEVANZKLASSE = {
    kritisch: "marke--kritisch",
    hoch:     "marke--kritisch",
    mittel:   "marke--warnung",
    info:     "marke--info"
};

/* Betriebszustand einer Quelle. */
const ZUSTANDSKLASSE = {
    erreichbar:  "marke--ok",
    auffaellig:  "marke--warnung",
    veraltet:    "marke--warnung",
    gestoert:    "marke--kritisch",
    deaktiviert: "marke--info",
    unbekannt:   "marke--info"
};

const STUFENKLASSE = {
    kritisch: "marke--kritisch",
    warnung:  "marke--warnung",
    info:     "marke--info"
};

const VERSIONSTEXT = {
    aktuell:           { text: "Aktuell",       klasse: "marke--ok" },
    update_verfuegbar: { text: "Update",        klasse: "marke--warnung" },
    kritisch:          { text: "Sicherheit",    klasse: "marke--kritisch" },
    unbekannt:         { text: "Unbekannt",     klasse: "marke--info" }
};

let istBearbeiter = false;

/* ---------- kleine Helfer ---------- */

function el(tag, klasse, text) {
    const knoten = document.createElement(tag);
    if (klasse) knoten.className = klasse;
    if (text !== undefined) knoten.textContent = text;
    return knoten;
}

function zeitpunkt(roh) {
    if (!roh) return "–";
    const datum = new Date(roh.replace(" ", "T"));
    return isNaN(datum) ? roh : datum.toLocaleString("de-DE", {
        day: "2-digit", month: "2-digit", year: "numeric",
        hour: "2-digit", minute: "2-digit"
    });
}

function hinweis(text, istFehler = false) {
    const box = document.getElementById("hinweisbox");
    box.textContent = text;
    box.classList.toggle("hinweisbox--fehler", istFehler);
    box.hidden = false;
    clearTimeout(hinweis.zeitgeber);
    hinweis.zeitgeber = setTimeout(() => { box.hidden = true; }, 4500);
}

function zurAnmeldung() { window.location.href = "anmeldung.html"; }

/* ---------- Kennzahlen ---------- */

function zeichneKennzahlen(k, auftraege) {
    const naechster = auftraege
        .map(a => a.naechste_ausfuehrung)
        .filter(Boolean)
        .sort()[0];

    const kacheln = [
        { beschriftung: "Neue Meldungen", wert: k.meldungen_neu_24h,
          zusatz: `${k.meldungen_gesamt} insgesamt erfasst` },
        { beschriftung: "Handlungsbedarf", wert: k.meldungen_handlungsbedarf,
          zusatz: `davon ${k.meldungen_kritisch} kritisch`,
          klasse: k.meldungen_handlungsbedarf > 0
              ? "kennzahl__wert--kritisch" : "kennzahl__wert--gut" },
        { beschriftung: "Unbearbeitet", wert: k.meldungen_ungelesen,
          zusatz: `+${k.meldungen_kritisch_24h} kritische seit gestern` },
        { beschriftung: "Quellen erreichbar",
          wert: `${k.quellen_erreichbar} / ${k.quellen_gesamt}`,
          zusatz: k.quellen_gestoert
              ? `${k.quellen_gestoert} gestört oder veraltet`
              : "alle Quellen liefern Daten",
          klasse: k.quellen_gestoert > 0
              ? "kennzahl__wert--kritisch" : "kennzahl__wert--gut" },
        { beschriftung: "Überwachte Produkte", wert: k.systeme_gesamt,
          zusatz: `Schwellwertmeldungen: ${k.meldungen_offen}` },
        { beschriftung: "Letzte Abfrage", wert: zeitpunkt(k.letzter_lauf),
          zusatz: naechster ? `nächste ${zeitpunkt(naechster)}` : "automatisch",
          klasse: "kennzahl__wert--klein" }
    ];

    const ziel = document.getElementById("kennzahlen");
    ziel.innerHTML = "";
    kacheln.forEach(kachel => {
        const feld = el("article", "kennzahl");
        feld.append(
            el("div", "kennzahl__beschriftung", kachel.beschriftung),
            el("div", `kennzahl__wert ${kachel.klasse || ""}`, String(kachel.wert)),
            el("div", "kennzahl__zusatz", kachel.zusatz)
        );
        ziel.appendChild(feld);
    });
}

/* ---------- Tabelle der Meldungen ---------- */

function zeichneMeldungen(meldungen) {
    const ziel = document.getElementById("meldungen");
    ziel.innerHTML = "";

    if (!meldungen.length) {
        const zeile = ziel.insertRow();
        const zelle = zeile.insertCell();
        zelle.colSpan = 5;
        zelle.className = "platzhalter";
        zelle.textContent = "Kein Handlungsbedarf. Alle Meldungen bearbeitet.";
        return;
    }

    meldungen.forEach(m => {
        const zeile = el("tr");

        const titel = el("td");
        if (m.verweis) {
            const verweis = el("a", "liste__system", m.titel.slice(0, 70));
            verweis.href = m.verweis;
            verweis.target = "_blank";
            verweis.rel = "noopener noreferrer";
            titel.appendChild(verweis);
        } else {
            titel.appendChild(el("span", "liste__system", m.titel.slice(0, 70)));
        }
        titel.title = m.titel;

        const relevanz = el("td");
        relevanz.appendChild(el("span",
            `marke ${RELEVANZKLASSE[m.relevanz] || ""}`, m.relevanz));

        const aktion = el("td");
        const knopf = el("button", "quittieren", "Bearbeitet");
        knopf.disabled = !istBearbeiter;
        knopf.addEventListener("click", () => markiereGelesen(m.meldung_id, knopf));
        aktion.appendChild(knopf);

        zeile.append(
            el("td", "liste__leise", m.bereich || "–"),
            titel,
            el("td", "liste__leise", KATEGORIETEXT[m.kategorie] || m.kategorie),
            relevanz,
            aktion
        );
        ziel.appendChild(zeile);
    });
}

async function markiereGelesen(meldungId, knopf) {
    knopf.disabled = true;
    try {
        await Api.gelesen(meldungId);
        hinweis("Meldung als bearbeitet gekennzeichnet.");
        await aktualisieren();
    } catch (fehler) {
        knopf.disabled = false;
        if (fehler instanceof NichtAngemeldet) return zurAnmeldung();
        hinweis(fehler instanceof NichtBerechtigt
            ? "Ihre Rolle erlaubt diese Aktion nicht."
            : `Fehlgeschlagen: ${fehler.message}`, true);
    }
}

async function quittiere(alarmId, knopf) {
    knopf.disabled = true;
    try {
        await Api.quittieren(alarmId);
        hinweis("Meldung quittiert.");
        await aktualisieren();
    } catch (fehler) {
        knopf.disabled = false;
        if (fehler instanceof NichtAngemeldet) return zurAnmeldung();
        hinweis(fehler instanceof NichtBerechtigt
            ? "Ihre Rolle erlaubt das Quittieren nicht."
            : `Quittieren fehlgeschlagen: ${fehler.message}`, true);
    }
}

/* ---------- Rangliste Risiko ---------- */

function zeichneRisiko(eintraege) {
    const ziel = document.getElementById("risiko");
    ziel.innerHTML = "";

    eintraege.forEach((eintrag, i) => {
        const farbe = eintrag.wert >= 60 ? "var(--kritisch)"
                    : eintrag.wert >= 30 ? "var(--warnung)"
                    : "var(--akzent)";

        const zeile = el("div", "rang");
        zeile.append(
            el("span", "rang__nummer", String(i + 1)),
            el("span", "rang__name", eintrag.system_name)
        );

        const rechts = el("div");
        const spur = el("div", "rang__balken");
        const fuellung = el("div", "rang__fuellung");
        fuellung.style.width = `${Math.max(eintrag.wert, 2)}%`;
        fuellung.style.background = farbe;
        spur.appendChild(fuellung);

        const wert = el("div", "rang__wert", eintrag.wert.toFixed(1));
        rechts.append(spur, wert);
        zeile.appendChild(rechts);

        zeile.title = `Versionsstand: ${eintrag.versionsstatus}`;
        ziel.appendChild(zeile);
    });
}

/* ---------- Versionsstand ---------- */

function zeichneSysteme(systeme) {
    const ziel = document.getElementById("systeme");
    ziel.innerHTML = "";

    systeme.forEach(s => {
        const zeile = el("div", "version");

        const links = el("div");
        links.appendChild(el("div", "version__name", s.name));

        const stand = el("div", "version__stand");
        stand.appendChild(document.createTextNode(s.installierte_version || "–"));
        if (s.verfuegbare_version && s.versionsstatus !== "aktuell") {
            stand.appendChild(document.createTextNode("  →  "));
            const neu = el("span",
                s.versionsstatus === "kritisch"
                    ? "version__neu version__neu--kritisch"
                    : "version__neu",
                s.verfuegbare_version);
            stand.appendChild(neu);
        }
        links.appendChild(stand);

        const zustand = VERSIONSTEXT[s.versionsstatus] || VERSIONSTEXT.unbekannt;
        const marke = el("span", `marke ${zustand.klasse}`, zustand.text);

        zeile.append(links, marke);
        ziel.appendChild(zeile);
    });
}

/* ---------- Ablauf ---------- */

function zeigeVerbindung(inOrdnung) {
    document.getElementById("verbindung")
        .classList.toggle("punkt--fehler", !inOrdnung);
}

async function aktualisieren() {
    try {
        const [einheit, anzahl] =
            (document.getElementById("zeitraum").value || "tag:14").split(":");
        const daten = await Api.uebersicht(einheit, Number(anzahl));

        istBearbeiter = ["bearbeiter", "admin"].includes(daten.benutzer.rolle);
        document.getElementById("benutzer").textContent =
            `${daten.benutzer.benutzername} · ${daten.benutzer.rolle}`;
        document.getElementById("aktualisieren").disabled = !istBearbeiter;

        zeichneKennzahlen(daten.kennzahlen, daten.auftraege || []);
        zeichneMeldungen(daten.dringende_meldungen);
        zeichneRisiko(daten.risiko);

        Diagramm.verlauf(document.getElementById("trend"),
            daten.trend.map(t => ({
                beschriftung: t.beschriftung, wert: t.anzahl
            })));

        Diagramm.balken(document.getElementById("nachSystem"),
            daten.nach_bereich
                .filter(z => z.anzahl > 0)
                .map(z => ({ beschriftung: z.bereich, wert: z.anzahl })));

        Diagramm.ring(document.getElementById("nachKategorie"),
            daten.nach_kategorie.map(z => ({
                beschriftung: KATEGORIETEXT[z.kategorie] || z.kategorie,
                wert: z.anzahl,
                farbe: KATEGORIEFARBEN[z.kategorie] || KATEGORIEFARBEN.sonstiges
            })));

        const systeme = await Api.systeme();
        zeichneSysteme(systeme.systeme);

        document.getElementById("stand").textContent =
            new Date().toLocaleString("de-DE");
        document.getElementById("auftraege").textContent =
            `${(daten.auftraege || []).length} geplante Aufträge · Aktualisierung alle 30 s`;

        zeigeVerbindung(true);
    } catch (fehler) {
        if (fehler instanceof NichtAngemeldet) return zurAnmeldung();
        // Ein Ausfall der Verbindung darf keine Fehlmeldung erzeugen:
        // die zuletzt bekannten Werte bleiben stehen.
        console.error(fehler);
        zeigeVerbindung(false);
    }
}

/* ---------- Schaltflächen ---------- */

document.getElementById("aktualisieren").addEventListener("click", async () => {
    const knopf = document.getElementById("aktualisieren");
    const beschriftung = knopf.textContent;
    knopf.disabled = true;
    knopf.textContent = "Prüfung läuft …";

    try {
        const ergebnis = await Api.aktualisieren();
        const v = ergebnis.versionen || {};
        hinweis(`Prüfung abgeschlossen: ${v.geprueft || 0} Quellen abgefragt, ` +
                `${v.aktualisiert || 0} neue Versionsstände, ` +
                `${(ergebnis.schwellwerte || {}).neue_alarme || 0} neue Meldungen.`);
        await aktualisieren();
        if (aktiverBereich !== "uebersicht") await Bereiche[aktiverBereich]();
    } catch (fehler) {
        if (fehler instanceof NichtAngemeldet) return zurAnmeldung();
        hinweis(fehler instanceof NichtBerechtigt
            ? "Ihre Rolle erlaubt das Anstoßen einer Prüfung nicht."
            : `Prüfung fehlgeschlagen: ${fehler.message}`, true);
    } finally {
        knopf.disabled = false;
        knopf.textContent = beschriftung;
    }
});

document.getElementById("abmelden").addEventListener("click", async () => {
    try { await Api.abmelden(); } catch (fehler) { /* Sitzung ohnehin beendet */ }
    zurAnmeldung();
});

/* ---------- Reiter ---------- */

let aktiverBereich = "uebersicht";

async function zeigeBereich(name) {
    aktiverBereich = name;

    document.querySelectorAll(".reiter__knopf").forEach(knopf => {
        const gewaehlt = knopf.dataset.bereich === name;
        knopf.classList.toggle("reiter__knopf--aktiv", gewaehlt);
        knopf.setAttribute("aria-selected", gewaehlt);
    });
    document.querySelectorAll(".bereich").forEach(block => {
        block.hidden = block.id !== `bereich-${name}`;
    });

    if (name === "uebersicht") return;

    try {
        await Bereiche[name]();
    } catch (fehler) {
        if (fehler instanceof NichtAngemeldet) return zurAnmeldung();
        hinweis(`Bereich konnte nicht geladen werden: ${fehler.message}`, true);
    }
}

document.querySelectorAll(".reiter__knopf").forEach(knopf => {
    knopf.addEventListener("click", () => zeigeBereich(knopf.dataset.bereich));
});

document.getElementById("zeitraum")
    .addEventListener("change", () => aktualisieren());

["filterBereich", "filterKategorie", "filterRelevanz", "filterUngelesen"]
    .forEach(id => document.getElementById(id)
        .addEventListener("change", () => Bereiche.meldungen()));

// Bei der Suche erst nach kurzer Pause abfragen, damit nicht bei jedem
// Tastendruck eine Anfrage entsteht.
let sucheZeitgeber;
document.getElementById("filterSuche").addEventListener("input", () => {
    clearTimeout(sucheZeitgeber);
    sucheZeitgeber = setTimeout(() => Bereiche.meldungen(), 400);
});

document.getElementById("filterNurFehler")
    .addEventListener("change", () => Bereiche.quellenprotokoll());
document.getElementById("berichtDrucken")
    .addEventListener("click", () => window.print());

/* Der Zeitgeber aktualisiert nur den gerade sichtbaren Bereich. */
aktualisieren();
setInterval(() => {
    if (aktiverBereich === "uebersicht") aktualisieren();
    else Bereiche[aktiverBereich]().catch(() => zeigeVerbindung(false));
}, INTERVALL_MS);
