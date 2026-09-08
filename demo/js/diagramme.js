/* =====================================================================
   Diagramme
   Bewusst als eigenes Modul und ohne fremde Bibliothek. Erzeugt werden
   reine SVG-Elemente; das Dashboard bleibt damit auch ohne
   Internetverbindung vollstaendig funktionsfaehig.
   ===================================================================== */

const NS = "http://www.w3.org/2000/svg";

/** Liest eine Farbe aus den CSS-Variablen.

    Dadurch sind die Farben nur an einer Stelle festgelegt: ein Wechsel
    der Gestaltung erfordert keine Aenderung an den Diagrammen. */
function farbe(name, ersatz = "#000000") {
    const wert = getComputedStyle(document.documentElement)
        .getPropertyValue(name).trim();
    return wert || ersatz;
}

/** Kleiner Helfer: erzeugt ein SVG-Element mit Attributen. */
function svgEl(name, attribute = {}) {
    const knoten = document.createElementNS(NS, name);
    for (const [schluessel, wert] of Object.entries(attribute)) {
        knoten.setAttribute(schluessel, wert);
    }
    return knoten;
}

/* ---------------------------------------------------------------------
   Hinweiskasten, der dem Zeiger folgt.
   Die eingebaute Anzeige ueber <title> erscheint erst nach einer Pause
   und laesst sich nicht gestalten. Deshalb ein eigener Kasten, der
   einmal erzeugt und danach nur noch bewegt wird.
   --------------------------------------------------------------------- */
const Hinweis = {
    kasten: null,

    _erzeuge() {
        if (this.kasten) return;
        this.kasten = document.createElement("div");
        this.kasten.className = "zeigerhinweis";
        this.kasten.hidden = true;
        document.body.appendChild(this.kasten);
    },

    /** zeilen: [{ beschriftung, wert, farbe }] oder Zeichenkette */
    zeige(ereignis, titel, zeilen = []) {
        this._erzeuge();
        this.kasten.innerHTML = "";

        const kopf = document.createElement("div");
        kopf.className = "zeigerhinweis__titel";
        kopf.textContent = titel;
        this.kasten.appendChild(kopf);

        zeilen.forEach(zeile => {
            const reihe = document.createElement("div");
            reihe.className = "zeigerhinweis__zeile";
            if (zeile.farbe) {
                const punkt = document.createElement("span");
                punkt.className = "zeigerhinweis__farbe";
                punkt.style.background = zeile.farbe;
                reihe.appendChild(punkt);
            }
            const text = document.createElement("span");
            text.textContent = zeile.beschriftung;
            const wert = document.createElement("strong");
            wert.className = "zeigerhinweis__wert";
            wert.textContent = zeile.wert;
            reihe.append(text, wert);
            this.kasten.appendChild(reihe);
        });

        this.kasten.hidden = false;
        this.bewege(ereignis);
    },

    bewege(ereignis) {
        if (!this.kasten || this.kasten.hidden) return;
        const abstand = 14;
        const breite = this.kasten.offsetWidth;
        const hoehe = this.kasten.offsetHeight;

        // Am rechten und unteren Rand auf die andere Seite klappen, damit
        // der Kasten nicht aus dem Fenster laeuft.
        let x = ereignis.clientX + abstand;
        let y = ereignis.clientY + abstand;
        if (x + breite > window.innerWidth - 8) x = ereignis.clientX - breite - abstand;
        if (y + hoehe > window.innerHeight - 8) y = ereignis.clientY - hoehe - abstand;

        this.kasten.style.left = `${Math.max(8, x)}px`;
        this.kasten.style.top = `${Math.max(8, y)}px`;
    },

    verbirg() {
        if (this.kasten) this.kasten.hidden = true;
    }
};

const Diagramm = {

    /* -----------------------------------------------------------------
       Verlaufskurve mit Flaechenfuellung.
       punkte: [{ beschriftung, wert }]
       ----------------------------------------------------------------- */
    verlauf(ziel, punkte) {
        ziel.innerHTML = "";
        if (!punkte.length) {
            ziel.innerHTML = '<p class="platzhalter">Keine Daten im Zeitraum.</p>';
            return;
        }

        const B = 620, H = 200;                        // Zeichenflaeche
        const rand = { oben: 12, rechts: 24, unten: 26, links: 38 };
        const breite = B - rand.links - rand.rechts;
        const hoehe  = H - rand.oben  - rand.unten;

        // Obergrenze auf einen glatten Wert aufrunden, damit die
        // Beschriftung der Achse lesbar bleibt.
        const groesster = Math.max(...punkte.map(p => p.wert), 1);
        const schritt = Math.max(1, Math.ceil(groesster / 4));
        const maximum = schritt * 4;

        const x = i => rand.links + (punkte.length === 1
            ? breite / 2
            : (i / (punkte.length - 1)) * breite);
        const y = w => rand.oben + hoehe - (w / maximum) * hoehe;

        const svg = svgEl("svg", {
            viewBox: `0 0 ${B} ${H}`,
            width: "100%",
            role: "img",
            "aria-label": "Verlauf der Meldungen je Kalenderwoche"
        });

        // Waagerechte Hilfslinien mit Achsenbeschriftung
        for (let i = 0; i <= 4; i++) {
            const wert = schritt * i;
            const yy = y(wert);
            svg.appendChild(svgEl("line", {
                x1: rand.links, y1: yy, x2: B - rand.rechts, y2: yy,
                stroke: farbe("--diagramm-gitter", "#e3e8f0"), "stroke-width": 1,
                "stroke-dasharray": i === 0 ? "0" : "3 4"
            }));
            const text = svgEl("text", {
                x: rand.links - 8, y: yy + 4,
                "text-anchor": "end", "font-size": 10, fill: farbe("--diagramm-achse", "#7b8697"),
                "font-family": "ui-monospace, monospace"
            });
            text.textContent = wert;
            svg.appendChild(text);
        }

        // Flaeche unter der Kurve
        const linie = punkte.map((p, i) => `${x(i)},${y(p.wert)}`).join(" ");
        const flaeche = `${rand.links},${rand.oben + hoehe} ${linie} ` +
                        `${x(punkte.length - 1)},${rand.oben + hoehe}`;

        const verlauf = svgEl("linearGradient", {
            id: "verlaufFuellung", x1: "0", y1: "0", x2: "0", y2: "1"
        });
        const kurvenfarbe = farbe("--akzent", "#0d9488");
        verlauf.appendChild(svgEl("stop", { offset: "0%",   "stop-color": kurvenfarbe, "stop-opacity": "0.24" }));
        verlauf.appendChild(svgEl("stop", { offset: "100%", "stop-color": kurvenfarbe, "stop-opacity": "0" }));
        const defs = svgEl("defs");
        defs.appendChild(verlauf);
        svg.appendChild(defs);

        svg.appendChild(svgEl("polygon", { points: flaeche, fill: "url(#verlaufFuellung)" }));
        svg.appendChild(svgEl("polyline", {
            points: linie, fill: "none", stroke: kurvenfarbe,
            "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round"
        }));

        // Senkrechte Fuehrungslinie, die beim Ueberfahren erscheint
        const fuehrung = svgEl("line", {
            y1: rand.oben, y2: rand.oben + hoehe,
            stroke: kurvenfarbe, "stroke-width": 1,
            "stroke-dasharray": "3 3", opacity: 0
        });
        svg.appendChild(fuehrung);

        // Letztes Teilstueck gestrichelt: die laufende Woche ist noch
        // nicht abgeschlossen und daher nicht vergleichbar.
        if (punkte.length >= 2) {
            const vorletzter = punkte.length - 2, letzter = punkte.length - 1;
            svg.appendChild(svgEl("line", {
                x1: x(vorletzter), y1: y(punkte[vorletzter].wert),
                x2: x(letzter),    y2: y(punkte[letzter].wert),
                stroke: farbe("--diagramm-grund", "#ffffff"), "stroke-width": 3
            }));
            svg.appendChild(svgEl("line", {
                x1: x(vorletzter), y1: y(punkte[vorletzter].wert),
                x2: x(letzter),    y2: y(punkte[letzter].wert),
                stroke: kurvenfarbe, "stroke-width": 2,
                "stroke-dasharray": "4 3", "stroke-linecap": "round"
            }));
        }

        const kreise = punkte.map((p, i) => {
            const kreis = svgEl("circle", {
                cx: x(i), cy: y(p.wert), r: 3.5,
                fill: farbe("--diagramm-grund", "#ffffff"), stroke: kurvenfarbe, "stroke-width": 2
            });
            svg.appendChild(kreis);
            return kreis;
        });

        // Unsichtbare Trefferflaechen: der Punkt selbst waere mit 3,5 px
        // Radius zu klein, um ihn bequem zu treffen. Jede Flaeche deckt
        // den waagerechten Bereich einer Woche ab.
        const spalte = breite / Math.max(punkte.length - 1, 1);
        punkte.forEach((p, i) => {
            const flaeche = svgEl("rect", {
                x: x(i) - spalte / 2, y: rand.oben,
                width: spalte, height: hoehe,
                fill: "transparent", style: "cursor: pointer"
            });

            const hervorheben = ereignis => {
                fuehrung.setAttribute("x1", x(i));
                fuehrung.setAttribute("x2", x(i));
                fuehrung.setAttribute("opacity", 0.7);
                kreise[i].setAttribute("r", 6);
                kreise[i].setAttribute("fill", kurvenfarbe);

                const vorher = i > 0 ? punkte[i - 1].wert : null;
                const zeilen = [{ beschriftung: "Meldungen", wert: p.wert,
                                  farbe: kurvenfarbe }];
                if (vorher !== null) {
                    const unterschied = p.wert - vorher;
                    zeilen.push({
                        beschriftung: "gegenüber Vorwoche",
                        wert: unterschied > 0 ? `+${unterschied}`
                            : unterschied < 0 ? String(unterschied) : "unverändert"
                    });
                }
                if (i === punkte.length - 1) {
                    zeilen.push({ beschriftung: "Woche", wert: "läuft noch" });
                }
                Hinweis.zeige(ereignis, p.beschriftung, zeilen);
            };

            flaeche.addEventListener("mouseenter", hervorheben);
            flaeche.addEventListener("mousemove", ereignis => Hinweis.bewege(ereignis));
            flaeche.addEventListener("mouseleave", () => {
                fuehrung.setAttribute("opacity", 0);
                kreise[i].setAttribute("r", 3.5);
                kreise[i].setAttribute("fill", farbe("--diagramm-grund", "#ffffff"));
                Hinweis.verbirg();
            });
            svg.appendChild(flaeche);
        });

        // Beschriftung der Waagerechten. Bei vielen Punkten wird nur
        // jede zweite gesetzt, damit sich die Texte nicht ueberlappen.
        const abstand = punkte.length > 10 ? Math.ceil(punkte.length / 8) : 1;
        punkte.forEach((p, i) => {
            if (i % abstand !== 0 && i !== punkte.length - 1) return;
            const text = svgEl("text", {
                x: x(i), y: H - 8,
                "text-anchor": i === 0 ? "start"
                              : i === punkte.length - 1 ? "end" : "middle",
                "font-size": 10, fill: farbe("--diagramm-achse", "#7b8697"),
                "font-family": "ui-monospace, monospace"
            });
            text.textContent = p.beschriftung;
            svg.appendChild(text);
        });

        ziel.appendChild(svg);
    },

    /* -----------------------------------------------------------------
       Ringdiagramm mit Legende.
       teile: [{ beschriftung, wert, farbe }]
       ----------------------------------------------------------------- */
    ring(ziel, teile) {
        ziel.innerHTML = "";
        const gesamt = teile.reduce((summe, t) => summe + t.wert, 0);

        if (!gesamt) {
            ziel.innerHTML = '<p class="platzhalter">Keine offenen Meldungen.</p>';
            return;
        }

        const G = 190, mitte = G / 2, radius = 66, staerke = 22;
        const umfang = 2 * Math.PI * radius;

        const svg = svgEl("svg", {
            viewBox: `0 0 ${G} ${G}`, width: G, height: G,
            role: "img", "aria-label": "Verteilung der Meldungen nach Kategorie"
        });

        const zahlKnoten = [];   // wird weiter unten befuellt

        let versatz = 0;
        const boegen = teile.map(teil => {
            const anteil = teil.wert / gesamt;
            const bogen = svgEl("circle", {
                cx: mitte, cy: mitte, r: radius,
                fill: "none", stroke: teil.farbe, "stroke-width": staerke,
                "stroke-dasharray": `${anteil * umfang} ${umfang}`,
                "stroke-dashoffset": -versatz,
                // Startpunkt oben statt rechts
                transform: `rotate(-90 ${mitte} ${mitte})`,
                style: "cursor: pointer; transition: stroke-width 0.12s"
            });
            svg.appendChild(bogen);
            versatz += anteil * umfang;
            return { bogen, teil, anteil };
        });

        // Beim Ueberfahren wird das Segment breiter, die uebrigen werden
        // blasser. So ist auch ohne Hinweiskasten erkennbar, welcher
        // Anteil gemeint ist.
        boegen.forEach(({ bogen, teil, anteil }) => {
            const hervorheben = ereignis => {
                boegen.forEach(b => b.bogen.setAttribute("opacity",
                    b.bogen === bogen ? 1 : 0.35));
                bogen.setAttribute("stroke-width", staerke + 6);
                if (zahlKnoten.length) {
                    zahlKnoten[0].textContent = teil.wert;
                    zahlKnoten[1].textContent = teil.beschriftung.toUpperCase().slice(0, 18);
                }
                Hinweis.zeige(ereignis, teil.beschriftung, [
                    { beschriftung: "Meldungen", wert: teil.wert, farbe: teil.farbe },
                    { beschriftung: "Anteil", wert: `${(anteil * 100).toFixed(1)} %` },
                    { beschriftung: "Gesamt", wert: gesamt }
                ]);
            };

            bogen.addEventListener("mouseenter", hervorheben);
            bogen.addEventListener("mousemove", ereignis => Hinweis.bewege(ereignis));
            bogen.addEventListener("mouseleave", () => {
                boegen.forEach(b => b.bogen.setAttribute("opacity", 1));
                bogen.setAttribute("stroke-width", staerke);
                if (zahlKnoten.length) {
                    zahlKnoten[0].textContent = gesamt;
                    zahlKnoten[1].textContent = "GESAMT";
                }
                Hinweis.verbirg();
            });
        });

        const zahl = svgEl("text", {
            x: mitte, y: mitte + 2, "text-anchor": "middle",
            "font-size": 26, "font-weight": "700", fill: farbe("--text", "#1a2029"),
            "font-family": "ui-monospace, monospace"
        });
        zahl.textContent = gesamt;
        svg.appendChild(zahl);
        zahlKnoten.push(zahl);

        const unterschrift = svgEl("text", {
            x: mitte, y: mitte + 19, "text-anchor": "middle",
            "font-size": 9, fill: farbe("--diagramm-achse", "#7b8697"), "letter-spacing": "1.4",
            "font-family": "ui-monospace, monospace"
        });
        unterschrift.textContent = "GESAMT";
        svg.appendChild(unterschrift);
        zahlKnoten.push(unterschrift);

        ziel.appendChild(svg);

        const legende = document.createElement("div");
        legende.className = "legende";
        teile.forEach(teil => {
            const eintrag = document.createElement("div");
            eintrag.className = "legende__eintrag";

            const farbe = document.createElement("span");
            farbe.className = "legende__farbe";
            farbe.style.background = teil.farbe;

            const name = document.createElement("span");
            name.textContent = teil.beschriftung;

            const anteil = document.createElement("span");
            anteil.className = "legende__anteil";
            anteil.textContent = `${Math.round(teil.wert / gesamt * 100)} %`;

            eintrag.append(farbe, name, anteil);
            eintrag.style.cursor = "default";
            eintrag.addEventListener("mouseenter", ereignis =>
                Hinweis.zeige(ereignis, teil.beschriftung, [
                    { beschriftung: "Meldungen", wert: teil.wert, farbe: teil.farbe },
                    { beschriftung: "Anteil",
                      wert: `${(teil.wert / gesamt * 100).toFixed(1)} %` }
                ]));
            eintrag.addEventListener("mousemove", ereignis => Hinweis.bewege(ereignis));
            eintrag.addEventListener("mouseleave", () => Hinweis.verbirg());
            legende.appendChild(eintrag);
        });
        ziel.appendChild(legende);
    },

    /* -----------------------------------------------------------------
       Waagerechte Balken.
       zeilen: [{ beschriftung, wert }]
       ----------------------------------------------------------------- */
    balken(ziel, zeilen) {
        ziel.innerHTML = "";
        if (!zeilen.length) {
            ziel.innerHTML = '<p class="platzhalter">Keine offenen Meldungen.</p>';
            return;
        }

        const groesster = Math.max(...zeilen.map(z => z.wert), 1);

        zeilen.forEach(zeile => {
            const reihe = document.createElement("div");
            reihe.className = "balkenzeile";

            const name = document.createElement("span");
            name.className = "balkenzeile__name";
            name.textContent = zeile.beschriftung;
            name.title = zeile.beschriftung;

            const spur = document.createElement("div");
            spur.className = "balkenzeile__spur";
            const wert = document.createElement("div");
            wert.className = "balkenzeile__wert";
            wert.style.width = `${Math.max(zeile.wert / groesster * 100, 3)}%`;
            spur.appendChild(wert);

            const zahl = document.createElement("span");
            zahl.className = "balkenzeile__zahl";
            zahl.textContent = zeile.wert;

            reihe.append(name, spur, zahl);
            reihe.style.cursor = "default";

            const summe = zeilen.reduce((a, z) => a + z.wert, 0);
            reihe.addEventListener("mouseenter", ereignis => {
                wert.style.filter = "brightness(1.25)";
                Hinweis.zeige(ereignis, zeile.beschriftung, [
                    { beschriftung: "Meldungen", wert: zeile.wert, farbe: farbe("--kritisch", "#d92d20") },
                    { beschriftung: "Anteil",
                      wert: `${(zeile.wert / summe * 100).toFixed(1)} %` }
                ]);
            });
            reihe.addEventListener("mousemove", ereignis => Hinweis.bewege(ereignis));
            reihe.addEventListener("mouseleave", () => {
                wert.style.filter = "";
                Hinweis.verbirg();
            });

            ziel.appendChild(reihe);
        });
    }
};
