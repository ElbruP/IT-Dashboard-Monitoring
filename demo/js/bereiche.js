/* =====================================================================
   Die weiteren Reiter: Produkte, Meldungen, Regeln, Berichte
   Jeder Bereich wird erst beim ersten Aufruf geladen und danach nur noch
   auf Anforderung erneut. Das spart Abfragen, wenn ein Reiter gar nicht
   betrachtet wird.
   ===================================================================== */

/** Erzeugt eine Tabelle aus Kopfzeilen und Zeilenaufbau. */
function tabelle(kopf, datensaetze, zeilenbau) {
    const t = el("table", "datentabelle");

    const kopfzeile = el("tr");
    kopf.forEach(k => kopfzeile.appendChild(el("th", null, k)));
    t.appendChild(el("thead")).appendChild(kopfzeile);

    const koerper = el("tbody");
    if (!datensaetze.length) {
        const zeile = el("tr");
        const zelle = el("td", "platzhalter", "Keine Daten vorhanden.");
        zelle.colSpan = kopf.length;
        zeile.appendChild(zelle);
        koerper.appendChild(zeile);
    } else {
        datensaetze.forEach(d => koerper.appendChild(zeilenbau(d)));
    }
    t.appendChild(koerper);
    return t;
}

const Bereiche = {

    /* ---------------- Produkte ---------------- */
    async produkte() {
        const ziel = document.getElementById("produkte");
        ziel.innerHTML = '<p class="platzhalter">Lade …</p>';
        const daten = await Api.produkte();

        ziel.innerHTML = "";
        ziel.appendChild(tabelle(
            ["Produkt", "Hersteller", "Host", "Installiert", "Verfügbar",
             "Quelle", "Zuletzt geprüft", "Intervall"],
            daten.produkte,
            p => {
                const zeile = el("tr");

                const name = el("td");
                name.appendChild(el("div", "liste__system", p.name));
                name.appendChild(el("div", "mono", p.kategorie));

                const host = el("td", "mono",
                    [p.hostname, p.ip_adresse].filter(Boolean).join("  ") || "–");

                const zustand = VERSIONSTEXT[p.versionsstatus] || VERSIONSTEXT.unbekannt;
                const verfuegbar = el("td");
                verfuegbar.appendChild(el("span", "mono", p.verfuegbare_version || "–"));
                verfuegbar.appendChild(document.createTextNode(" "));
                verfuegbar.appendChild(el("span", `marke ${zustand.klasse}`, zustand.text));

                // Herkunft der Angabe: Art der Quelle und, sofern vorhanden,
                // der Verweis zum Nachvollziehen beim Hersteller.
                const quelle = el("td");
                const block = el("div", "quellenzeile");
                block.appendChild(el("span", "quellenzeile__art", p.quelle_beschreibung));
                if (p.quelle_url) {
                    const verweis = el("a", "mono", p.quelle_kennung || p.quelle_url);
                    verweis.href = p.quelle_url;
                    verweis.target = "_blank";
                    verweis.rel = "noopener noreferrer";
                    block.appendChild(verweis);
                }
                quelle.appendChild(block);

                zeile.append(
                    name,
                    el("td", "liste__leise", p.hersteller || "–"),
                    host,
                    el("td", "mono", p.installierte_version || "–"),
                    verfuegbar,
                    quelle,
                    el("td", "mono", p.geprueft_am ? zeitpunkt(p.geprueft_am) : "–"),
                    el("td", "mono", `${p.pruefintervall_min} min`)
                );
                return zeile;
            }
        ));
    },

    /* ---------------- Meldungen ---------------- */
    async meldungen() {
        const ziel = document.getElementById("alleMeldungen");
        ziel.innerHTML = '<p class="platzhalter">Lade …</p>';

        // Bereichsliste einmalig fuellen
        const auswahl = document.getElementById("filterBereich");
        if (auswahl.options.length <= 1) {
            const daten = await Api.bereiche();
            daten.bereiche.forEach(b => {
                const eintrag = document.createElement("option");
                eintrag.value = b.name;
                eintrag.textContent = `${b.name} (${b.offen})`;
                auswahl.appendChild(eintrag);
            });
        }

        const daten = await Api.meldungen({
            bereich:      auswahl.value,
            kategorie:    document.getElementById("filterKategorie").value,
            relevanz:     document.getElementById("filterRelevanz").value,
            suche:        document.getElementById("filterSuche").value.trim(),
            nurUngelesen: document.getElementById("filterUngelesen").checked
        });

        ziel.innerHTML = "";
        ziel.appendChild(tabelle(
            ["Relevanz", "Kategorie", "Bereich", "Meldung", "Quelle",
             "Veröffentlicht", "Status", ""],
            daten.meldungen,
            m => {
                const zeile = el("tr");

                const relevanz = el("td");
                relevanz.appendChild(el("span",
                    `marke ${RELEVANZKLASSE[m.relevanz] || ""}`, m.relevanz));
                if (m.cvss !== null && m.cvss !== undefined) {
                    relevanz.appendChild(el("div", "mono", `CVSS ${m.cvss}`));
                }

                // Titel mit Verweis auf die Originalmeldung: die Angabe
                // soll beim Anbieter nachvollziehbar bleiben.
                const meldung = el("td");
                if (m.verweis) {
                    const verweis = el("a", null, m.titel);
                    verweis.href = m.verweis;
                    verweis.target = "_blank";
                    verweis.rel = "noopener noreferrer";
                    meldung.appendChild(verweis);
                } else {
                    meldung.appendChild(document.createTextNode(m.titel));
                }
                if (m.zusammenfassung) {
                    meldung.appendChild(el("div", "mono",
                        m.zusammenfassung.slice(0, 150)));
                }
                if (m.system_name) {
                    meldung.appendChild(el("span", "marke marke--info", m.system_name));
                }

                const status = el("td");
                if (m.gelesen_am) {
                    status.appendChild(el("div", "mono", zeitpunkt(m.gelesen_am)));
                    if (m.gelesen_von) {
                        status.appendChild(el("div", "mono", `von ${m.gelesen_von}`));
                    }
                } else {
                    status.appendChild(el("span", "marke marke--warnung", "offen"));
                }

                const aktion = el("td");
                if (!m.gelesen_am) {
                    const knopf = el("button", "quittieren", "Bearbeitet");
                    knopf.disabled = !istBearbeiter;
                    knopf.title = istBearbeiter
                        ? "Meldung als bearbeitet kennzeichnen"
                        : "Erfordert mindestens die Rolle 'bearbeiter'";
                    knopf.addEventListener("click", async () => {
                        knopf.disabled = true;
                        try {
                            await Api.gelesen(m.meldung_id);
                            hinweis("Meldung als bearbeitet gekennzeichnet.");
                            Bereiche.meldungen();
                        } catch (fehler) {
                            knopf.disabled = false;
                            hinweis(`Fehlgeschlagen: ${fehler.message}`, true);
                        }
                    });
                    aktion.appendChild(knopf);
                }

                zeile.append(
                    relevanz,
                    el("td", "liste__leise", m.kategorie),
                    el("td", "liste__leise", m.bereich || "–"),
                    meldung,
                    el("td", "mono", m.quelle),
                    el("td", "mono", m.veroeffentlicht_am
                        ? zeitpunkt(m.veroeffentlicht_am) : "–"),
                    status,
                    aktion
                );
                return zeile;
            }
        ));
    },

    /* ---------------- Quellen ---------------- */
    async quellen() {
        const ziel = document.getElementById("quellen");
        ziel.innerHTML = '<p class="platzhalter">Lade …</p>';
        const daten = await Api.quellen();

        ziel.innerHTML = "";
        ziel.appendChild(tabelle(
            ["Zustand", "Quelle", "Typ", "Bereich", "Adresse", "Intervall",
             "Letzter Erfolg", "Meldungen", "Letzter Fehler"],
            daten.quellen,
            q => {
                const zeile = el("tr");

                const zustand = el("td");
                zustand.appendChild(el("span",
                    `marke ${ZUSTANDSKLASSE[q.zustand] || "marke--info"}`, q.zustand));
                if (q.fehler_in_folge > 0) {
                    zustand.appendChild(el("div", "mono",
                        `${q.fehler_in_folge} Fehler in Folge`));
                }

                const adresse = el("td", "mono",
                    (q.adresse || "–").slice(0, 46));
                adresse.title = q.adresse || "";

                zeile.append(
                    zustand,
                    el("td", "liste__system", q.bezeichnung),
                    el("td", "liste__leise", q.typ),
                    el("td", "liste__leise", q.bereich || "–"),
                    adresse,
                    el("td", "mono", `${q.pruefintervall_min} min`),
                    el("td", "mono", q.letzter_erfolg ? zeitpunkt(q.letzter_erfolg) : "–"),
                    el("td", "mono", String(q.meldungen)),
                    el("td", "mono", (q.letzter_fehler || "–").slice(0, 60))
                );
                return zeile;
            }
        ));

        await Bereiche.quellenprotokoll();
    },

    async quellenprotokoll() {
        const ziel = document.getElementById("quellenprotokoll");
        const nurFehler = document.getElementById("filterNurFehler").checked;
        const daten = await Api.quellenprotokoll(nurFehler);

        ziel.innerHTML = "";
        ziel.appendChild(tabelle(
            ["Zeitpunkt", "Quelle", "Ergebnis", "HTTP", "Gefunden", "Neu",
             "Dauer", "Fehlertext"],
            daten.protokoll,
            l => {
                const zeile = el("tr");
                const ergebnis = el("td");
                ergebnis.appendChild(el("span",
                    `marke ${l.erfolgreich ? "marke--ok" : "marke--kritisch"}`,
                    l.erfolgreich ? "erfolgreich" : "fehlgeschlagen"));

                zeile.append(
                    el("td", "mono", zeitpunkt(l.gestartet_am)),
                    el("td", "liste__system", l.quelle),
                    ergebnis,
                    el("td", "mono", l.http_status ?? "–"),
                    el("td", "mono", String(l.gefunden)),
                    el("td", "mono", String(l.neu)),
                    el("td", "mono", l.dauer_ms !== null ? `${l.dauer_ms} ms` : "–"),
                    el("td", "mono", l.fehlertext || "–")
                );
                return zeile;
            }
        ));
    },

    /* ---------------- Regeln ---------------- */
    async regeln() {
        const ziel = document.getElementById("regeln");
        ziel.innerHTML = '<p class="platzhalter">Lade …</p>';
        const daten = await Api.regeln();

        ziel.innerHTML = "";
        ziel.appendChild(tabelle(
            ["System", "Kennzahl", "Einheit", "Richtung", "Warnung",
             "Kritisch", "Letzter Wert", "Status"],
            daten.regeln,
            r => {
                const zeile = el("tr");

                const status = el("td");
                const klasse = r.status === "kritisch" ? "marke--kritisch"
                             : r.status === "warnung"  ? "marke--warnung"
                             : "marke--ok";
                status.appendChild(el("span", `marke ${klasse}`, r.status || "ohne Regel"));

                const wert = el("td", "mono",
                    r.wert === null || r.wert === undefined
                        ? "–" : `${r.wert} ${r.einheit}`);

                const richtung = r.richtung === "untergrenze"
                    ? "Untergrenze" : r.richtung === "obergrenze"
                    ? "Obergrenze" : "–";

                const bezeichnung = el("td");
                bezeichnung.appendChild(document.createTextNode(r.bezeichnung));
                if (r.beschreibung) {
                    bezeichnung.appendChild(el("div", "mono", r.beschreibung));
                }

                zeile.append(
                    el("td", "liste__system", r.system_name),
                    bezeichnung,
                    el("td", "mono", r.einheit),
                    el("td", "liste__leise", richtung),
                    el("td", "mono", r.grenze_warnung ?? "–"),
                    el("td", "mono", r.grenze_kritisch ?? "–"),
                    wert,
                    status
                );
                return zeile;
            }
        ));
    },

    /* ---------------- Berichte ---------------- */
    async berichte() {
        const ziel = document.getElementById("bericht");
        ziel.innerHTML = '<p class="platzhalter">Lade …</p>';
        const d = await Api.bericht();
        const k = d.kennzahlen;

        ziel.innerHTML = "";

        const kopf = el("div", "bericht__block");
        kopf.appendChild(el("p", "bericht__ueberschrift",
            `Erstellt am ${d.erstellt_am}`));

        const paare = el("div", "bericht__paare");
        [
            ["Überwachte Systeme", k.systeme_gesamt],
            ["Offene Meldungen", k.meldungen_offen],
            ["davon kritisch", k.meldungen_kritisch],
            ["Quellen erreichbar", `${k.quellen_online} / ${k.quellen_gesamt}`],
            ["Quittiert (30 Tage)", d.bearbeitung.quittiert_30_tage],
            ["Ø Bearbeitungsdauer", `${d.bearbeitung.durchschnitt_stunden} h`]
        ].forEach(([beschriftung, wert]) => {
            const feld = el("div", "bericht__paar");
            feld.appendChild(el("div", "bericht__wert", String(wert)));
            feld.appendChild(el("div", "bericht__beschriftung", beschriftung));
            paare.appendChild(feld);
        });
        kopf.appendChild(paare);
        ziel.appendChild(kopf);

        const risiko = el("div", "bericht__block");
        risiko.appendChild(el("p", "bericht__ueberschrift", "Risikobewertung je System"));
        risiko.appendChild(tabelle(
            ["System", "Versionsstand", "Risikowert"],
            d.risiko,
            r => {
                const zeile = el("tr");
                zeile.append(
                    el("td", "liste__system", r.system_name),
                    el("td", "liste__leise", r.versionsstatus),
                    el("td", "mono", r.wert.toFixed(1))
                );
                return zeile;
            }
        ));
        ziel.appendChild(risiko);

        const offen = el("div", "bericht__block");
        offen.appendChild(el("p", "bericht__ueberschrift", "Offene Meldungen"));
        offen.appendChild(tabelle(
            ["System", "Schweregrad", "Meldung", "Ausgelöst"],
            d.offene_meldungen,
            m => {
                const zeile = el("tr");
                const stufe = el("td");
                stufe.appendChild(el("span",
                    `marke ${STUFENKLASSE[m.stufe] || ""}`, m.stufe));
                zeile.append(
                    el("td", "liste__system", m.system_name),
                    stufe,
                    el("td", null, m.meldung),
                    el("td", "mono", zeitpunkt(m.ausgeloest_am))
                );
                return zeile;
            }
        ));
        ziel.appendChild(offen);
    }
};
