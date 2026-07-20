# Präsentationsleitfaden: Ergebnisse Übung 2 Het Comp

Vorgabe für den Foliensatz. Zahlen aus `results/*.json`, geprüft gegen `report/essay/report.tex`.
Code und Implementierungsdetails aus `gpubench/`.

**Wichtig für die Umsetzung:** Der unter "Folientext" angegebene Wortlaut ist verbindlich und wird
wörtlich gesetzt. Er ist nicht als Rohmaterial gedacht, das noch umformuliert oder ausgeschmückt
werden soll. Was nicht im Folientext steht, gehört nicht auf die Folie.

## Rahmen

| Punkt | Vorgabe |
| --- | --- |
| Titel | Ergebnisse Übung 2 Het Comp |
| Dauer | 12 bis 15 Minuten, keine Live-Demo |
| Anlass | Übungsvortrag an der Universität Trier, Heterogeneous Computing 2026S |
| Publikum | Kommilitonen und Dozent, SIMT ist aus der Vorlesung bekannt |
| Umfang | 13 Folien plus Backup |

## Aufbau

Beide Aufgaben durchlaufen denselben Fünfschritt. Diese Parallelität ist gewollt und soll
gestalterisch erkennbar sein.

```
Folie 1        Titel
Folie 2        Die Suite

Folie 3        Aufgabe 1: Aufgabenstellung
Folie 4        Aufgabe 1: Lösung in Code
Folie 5        Aufgabe 1: Ergebnis Schritt 1, Auslastung
Folie 6        Aufgabe 1: Ergebnis Schritt 2, Divergenz
Folie 7        Aufgabe 1: Deutung

Folie 8        Aufgabe 2: Aufgabenstellung
Folie 9        Aufgabe 2: Lösung in Code
Folie 10       Aufgabe 2: Ergebnis Schritt 1, Zugriffsmuster
Folie 11       Aufgabe 2: Ergebnis Schritt 2, Occupancy
Folie 12       Aufgabe 2: Deutung

Folie 13       Fazit
```

### Die Trennung der beiden Ergebnisschritte

Das ist die tragende Struktur des Vortrags. Jede Aufgabe besteht aus zwei aufeinander aufbauenden
Messungen, und diese Abhängigkeit muss auf den Folien sichtbar sein, nicht nur im gesprochenen Wort.

```
Aufgabe 1
  Schritt 1   Wann ist die GPU überhaupt ausgelastet?
              Sweep über n, Abbildung scaling.png
              Ergebnis: Sättigung bei rund 3085,3 GFLOP/s

  Schritt 2   Was kostet Divergenz bei ausgelasteter GPU?
              n fest auf 2^25 aus Schritt 1, Sweep über DEGREE
              Abbildung divergence.png, Einbruch um Faktor 56,1

Aufgabe 2
  Schritt 1   Welches Zugriffsmuster trägt die Bandbreite?
              Sweep über coalesced, strided, gather, Abbildung patterns.png
              Ergebnis: coalesced mit 78,7 GB/s, Faktor 11,3 vor gather

  Schritt 2   Wie viel Parallelität braucht das beste Muster?
              coalesced fest aus Schritt 1, Sweep über die Work-Group-Größe
              Abbildung occupancy.png, Knick bei Warp-Breite 64
```

Der Übergang ist beide Male derselbe Gedanke: **Das Ergebnis von Schritt 1 wird zur festgehaltenen
Bedingung von Schritt 2.** Schritt 1 stellt sicher, dass überhaupt im relevanten Bereich gemessen
wird, erst dadurch ist Schritt 2 aussagekräftig. Ohne Sättigung wäre der Divergenzeffekt vom
Auslastungseffekt überlagert; ohne coalesced liefe die Occupancy-Kurve gegen die Bandbreitengrenze
des schlechten Musters.

Umsetzung:

- Jeder Schritt bekommt eine eigene Ergebnisfolie mit genau einem Diagramm, groß gesetzt.
- Die Kopfzeile der Schritt-2-Folie benennt die übernommene Bedingung, nicht nur den Befund.
- Eine schlichte visuelle Verbindung zeigt die Übernahme, etwa eine Zeile am Folienkopf im Sinne von "n fest auf 2^25 aus Schritt 1". Kein Pfeildiagramm, keine Prozessgrafik, keine nummerierten Kreise.
- Die Schrittfolge ist in beiden Aufgaben identisch, damit die Parallelität erkennbar wird.

## Stilregeln

Der Foliensatz ist ein wissenschaftlicher Kurzvortrag, kein Produktpitch.

**Sprache:**

- Keine Geviert- oder Halbgeviertstriche. Nur der einfache Bindestrich, ansonsten Komma, Doppelpunkt oder Punkt.
- Sachlicher Indikativ. Keine Superlative, keine Wertungen wie "beeindruckend", "dramatisch", "massiv", "revolutionär", "leistungsstark".
- Keine Fülleinleitungen wie "In diesem Abschnitt betrachten wir", "Werfen wir einen Blick auf", "Es zeigt sich, dass".
- Keine rhetorischen Fragen als Überschrift. Ausnahme: die beiden Aufgabenstellungs-Folien, dort ist die Frage der Inhalt.
- Keine Dreiklang-Formeln und keine Alliterationsketten.
- Fachbegriffe bleiben englisch, wenn sie in der Vorlesung englisch sind (Warp, Work-Item, Work-Group, Coalescing, Occupancy). Nicht eindeutschen.
- Zahlen mit deutschem Dezimalkomma, Einheit mit schmalem Leerraum: 78,7 GB/s.

**Gestaltung:**

- Keine Emoji, keine Icon-Sets, keine Piktogramme neben Aufzählungspunkten.
- Keine Farbverläufe, keine Schlagschatten, keine abgerundeten "Feature-Karten", keine Kacheln mit großen Zahlen als Blickfang.
- Kein Stockfoto und keine dekorative Grafik. Die einzigen Bilder sind die vier Messdiagramme.
- Eine Schriftfamilie, maximal zwei Schnitte. Serifenlos. Code in einer Festbreitenschrift.
- Zwei Farben plus Grau: eine Akzentfarbe für GPU-Daten, Grau für die CPU-Referenz, Schwarz für Text. Die Zuordnung gilt über alle Folien hinweg.
- Maximal fünf Aufzählungspunkte je Folie, je Punkt höchstens zwei Zeilen.
- Die Kopfzeile trägt eine Aussage, keine Kategorie.

**Code auf Folien:**

- Nur die angegebenen Ausschnitte, keine vollständigen Dateien. Syntaxhervorhebung dezent oder gar nicht.
- Die entscheidende Zeile wird hervorgehoben, nicht der ganze Block.
- Kommentare im Code sind Teil des Arguments und bleiben stehen.

**Abbildungen:**

- Die vier Diagramme liegen fertig unter `report/essay/figures/`: `scaling.png`, `divergence.png`, `patterns.png`, `occupancy.png`. Unverändert einbinden, nicht neu einfärben, nicht freistellen, nicht beschneiden.
- Genau ein Diagramm je Ergebnisfolie, großformatig.
- Jede Abbildung bekommt eine nummerierte Unterschrift im Fließtextstil.

## Erzählbogen

Ich habe eine kleine Benchmark-Suite gebaut. Der Aufwand lag nicht im Messen, sondern darin, die
Vergleiche so zu konstruieren, dass sie tatsächlich vergleichbar sind. Beide Aufgaben zeigen
dieselbe Konsequenz aus zwei Richtungen: Die GPU erreicht hohen Durchsatz nur bei einheitlichem
Kontrollfluss im Warp und bei regelmäßigem Datenlayout.

## Folien

### Folie 1: Titel

```
Ergebnisse Übung 2 Het Comp
GPU-Mikro-Benchmarks: SIMT-Ausführungsmodell und Speicherbandbreite

Jan-Niclas Loosen
Universität Trier, Heterogeneous Computing 2026S
```

Der Untertitel trägt den GPU-Bezug und wird nicht kleiner gesetzt als notwendig. Wer nur die
Titelfolie sieht, muss erkennen, dass der Vortrag GPUs vermisst.

### Folie 2: Die Suite

**Titel:** Eine Benchmark-Suite als gemeinsame Grundlage beider Aufgaben

**Folientext:**

```
Python-Paket gpubench mit CLI: info, compute, memory, baseline, all, plots
Zwei OpenCL-C-Dateien, drei Kernel: compute_uniform, compute_divergent, stream
NumPy-CPU-Referenz für dieselben Workloads
Zeitmessung über OpenCL-Profiling-Events, zwei Aufwärmläufe, Median aus sieben Läufen
Messläufe schreiben results/*.json, Abbildungen entstehen daraus ohne GPU
```

**Kommentar:**
Beide Aufgaben laufen durch dieselbe Infrastruktur, das ist der Grund für den Aufwand. Drei
Entscheidungen sind wesentlich. Erstens messe ich über Profiling-Events statt mit einer Uhr um den
Python-Aufruf, sonst gingen Host-Overhead und Queue-Latenz in die Zahl ein. Zweitens der Median
statt des Mittelwerts, damit Ausreißer durch Scheduling nicht durchschlagen. Drittens frage ich
die Warp-Breite beim Gerät ab, statt 32 anzunehmen; auf der Radeon 890M sind es 64, und genau an
dieser Zahl hängt später der Knick in der Occupancy-Kurve. Testgerät ist ein AMD Ryzen AI 9 HX PRO
370 mit Radeon 890M und 16 Compute Units. Hier einmal erwähnen, dass ich durchgehend die
NVIDIA-Nomenklatur der Vorlesung verwende, also Warp statt Wavefront.

### Folie 3: Aufgabe 1, Aufgabenstellung

**Titel:** Aufgabe 1: Was kostet Warp-Divergenz?

**Folientext:**

```
Rechenintensiver Kernel, ein Work-Item je Element, feste Zahl von FMA-Schritten
Schritt 1: ab welcher Problemgröße ist die GPU ausgelastet?
Schritt 2: was kostet es dann, wenn Lanes eines Warps verschiedene Pfade nehmen?
Messgröße: Durchsatz in GFLOP/s
```

**Kommentar:**
Hier die Zweiteilung ankündigen, damit das Publikum die beiden folgenden Ergebnisfolien einordnen
kann. Schritt 1 ist die Vorbedingung, Schritt 2 der eigentliche Gegenstand. Die Schwierigkeit bei
Schritt 2 liegt darin, dass ein naiver Aufbau nichts zeigt: Wenn mehr Pfade auch mehr Arbeit
bedeuten, misst man nur, dass mehr Arbeit länger dauert. Der Kernel muss also so gebaut sein, dass
die Arbeit je Work-Item konstant bleibt und sich ausschließlich die Divergenz ändert.

### Folie 4: Aufgabe 1, Lösung in Code

**Titel:** Konstante Arbeit, variable Divergenz

**Folientext:** Codeausschnitt aus `compute.cl`, die Schleife hervorgehoben.

```c
int lane = get_local_id(0) % DEGREE;

for (int b = 0; b < DEGREE; ++b) {
    if (lane == b) {
        x = work(x);        // KITERS mal FMA, 2 FLOPs je Schritt
    }
}
```

```
Jedes Work-Item durchläuft die Schleife, trifft aber genau einen Zweig
FLOP-Zahl je Work-Item bleibt konstant, unabhängig von DEGREE
DEGREE wird zur Build-Zeit über -D gesetzt, kein Laufzeit-Overhead
```

**Kommentar:**
Das ist der Kern der Aufgabe. Ich schleife über DEGREE Zweige, von denen je Work-Item genau einer
zutrifft. Die geleistete Arbeit bleibt damit konstant, es ändert sich nur, auf wie viele Pfade
sich die Lanes eines Warps verteilen. Der gemessene Einbruch ist deshalb reiner
Serialisierungsverlust und nicht Mehrarbeit. DEGREE kommt als Präprozessor-Makro zur Build-Zeit
hinein, der Kernel wird je Divergenzgrad neu übersetzt und enthält keine zusätzliche
Laufzeitlogik.

### Folie 5: Aufgabe 1, Ergebnis Schritt 1

**Titel:** Schritt 1: SIMT trägt erst bei ausreichender Auslastung

**Abbildung:** `scaling.png`, groß. Unterschrift: "Abbildung 1: Durchsatz über der Problemgröße n,
logarithmische n-Achse."

**Folientext:**

```
n = 1024: 23,4 GFLOP/s
n rund 6,7 mal 10 hoch 7: 3085,3 GFLOP/s
Sättigung, sobald genug Work-Items die 16 Compute Units füllen
```

**Kommentar:**
Schritt 1 läuft auf `compute_uniform`, dem Kernel ganz ohne Verzweigung. Der divergente Kernel
kommt erst in Schritt 2 zum Einsatz. Bei kleinem n sind zu wenige Threads vorhanden, um die
Compute Units zu füllen, und die Startkosten des Kernel-Launch dominieren. Der Anstieg über zwei Größenordnungen bedeutet nicht,
dass die GPU schneller rechnet, sondern nur, dass sie ausgelastet ist. Diese Folie zügig
abhandeln, sie ist die Vorbedingung und nicht der Befund. Am Ende den Übergang explizit machen:
Aus dieser Kurve wähle ich ein n im gesättigten Bereich und halte es für Schritt 2 fest.

### Folie 6: Aufgabe 1, Ergebnis Schritt 2

**Titel:** Schritt 2: Bei gesättigter GPU kostet Divergenz Faktor 56,1

**Kopfzeile der Bedingung:** "n fest auf 2^25 aus Schritt 1"

**Abbildung:** `divergence.png`, groß. Unterschrift: "Abbildung 2: Durchsatz über dem
Divergenzgrad, also der Zahl der Pfade je Warp."

**Folientext:**

```
Grad 1: 3088,2 GFLOP/s
Grad 64: 55,1 GFLOP/s
Einbruch um Faktor 56,1 bei konstanter FLOP-Zahl
```

**Kommentar:**
Erster Kernbefund, hier Zeit lassen. Zuerst darauf hinweisen, dass n jetzt festgehalten ist und
im gesättigten Bereich liegt. Ohne diese Bedingung wäre der Divergenzeffekt vom Auslastungseffekt
überlagert und die Kurve nicht interpretierbar. Dann der eigentliche Punkt: Es wird über alle
Divergenzgrade exakt gleich viel gerechnet, und trotzdem dauert es 56 mal länger. Der Sweep endet
bei 64, weil das die Warp-Breite ist und damit der Punkt, an dem jede Lane einen eigenen Pfad
nimmt. Mehr Divergenz ist innerhalb eines Warps nicht möglich.

### Folie 7: Aufgabe 1, Deutung

**Titel:** Lockstep-Ausführung serialisiert die Pfade

**Folientext:**

```
Ein Warp führt seine Lanes im Lockstep aus
Bei verschiedenen Verzweigungen werden die Pfade nacheinander abgearbeitet
Je Durchlauf ist nur eine Lane-Gruppe aktiv, die übrigen sind maskiert
Jeder Durchlauf kostet die volle Zeit, daher etwa 1/DEGREE
CPU-Referenz: Faktor 2,6 statt 56,1
```

**Kommentar:**
Der Vergleich mit der CPU trägt die Deutung. NumPy leistet dieselbe elementweise Arbeit und bricht
trotzdem nur um Faktor 2,6 ein, weil es keine Lockstep-Serialisierung gibt. Der verbleibende
Anstieg dort kommt vom Mehraufwand der Maskierung über das gesamte Feld, nicht von den
Verzweigungen selbst. Die Lücke zwischen gemessenen 56,1 und theoretischen 64 nicht als Messfehler
darstellen: Anteile im Kernel ohne Divergenz sowie Start- und Speicherkosten skalieren nicht mit.
Die Größenordnung bestätigt das Modell, der exakte Wert trägt keine Aussage.

### Folie 8: Aufgabe 2, Aufgabenstellung

**Titel:** Aufgabe 2: Was kostet unregelmäßiger Speicherzugriff?

**Folientext:**

```
Speicherintensiver Kernel mit sehr geringer arithmetischer Intensität
Schritt 1: wie stark unterscheiden sich coalesced, strided und gather?
Schritt 2: wie viel Parallelität braucht das beste Muster?
Messgröße: effektive Bandbreite in GB/s
```

**Kommentar:**
Dieselbe Zweiteilung wie bei Aufgabe 1 ankündigen, das ist der Wiedererkennungspunkt. Auch hier
liegt die Schwierigkeit in der Fairness: Drei Zugriffsmuster in drei getrennten Kerneln zu messen
wäre angreifbar, weil der Compiler jede Variante anders optimieren kann und die bewegten
Datenmengen auseinanderlaufen. Schritt 2 zielt auf das Latency-Hiding, also darauf, dass die GPU
Wartezeit nicht über Caches überbrückt, sondern über den Wechsel zwischen Warps.

### Folie 9: Aufgabe 2, Lösung in Code

**Titel:** Ein Kernel, drei Muster, gleiche Byte-Menge

**Folientext:** Codeausschnitt aus `memory.cl` und `bench_memory.py`.

```c
b[i] = a[idx[i]] * c;      // Muster steckt allein in idx
```

```python
coalesced: arange(n)
strided:   (arange(n) * 521) % n     # 521 prim, also teilerfremd zu n
gather:    default_rng(SEED).permutation(n)
```

```
idx wird für alle drei Muster materialisiert, auch für coalesced
Dadurch bewegen alle Varianten dieselbe Byte-Menge
Fester Seed macht das gather-Muster reproduzierbar
```

**Kommentar:**
Das Zugriffsmuster wird über das Indexfeld hineingereicht, alle drei Varianten laufen durch
identischen Code. Das Indexfeld wird auch für coalesced angelegt, wo es die Identität ist. Das
kostet dort Bandbreite, die man sparen könnte, aber nur so ist die bewegte Byte-Menge in allen
drei Fällen gleich. Die Schrittweite 521 ist prim und damit teilerfremd zu n. Das ist notwendig,
weil i mal stride modulo n sonst keine Bijektion ist und der Zugriff gar nicht das ganze Feld
abtastet. Der Code prüft das und bricht sonst ab.

### Folie 10: Aufgabe 2, Ergebnis Schritt 1

**Titel:** Schritt 1: Coalescing bestimmt die Bandbreite, nicht die Datenmenge

**Abbildung:** `patterns.png`, groß. Unterschrift: "Abbildung 3: Effektive Bandbreite je
Zugriffsmuster."

**Folientext:**

```
coalesced 78,7 GB/s, nahe der Kopier-Spitzenbandbreite von 79,4 GB/s
strided 6,9 GB/s
gather 6,9 GB/s, also Faktor 11,3 langsamer als coalesced
Alle drei Muster bewegen exakt gleich viele Bytes
```

**Kommentar:**
Die letzte Zeile ist der eigentliche Punkt und sollte betont werden. Der Unterschied kommt allein
aus der Anordnung der Adressen, nicht aus der Datenmenge. Am Ende den Übergang explizit machen:
coalesced ist das tragfähige Muster, deshalb halte ich es für Schritt 2 fest und variiere
stattdessen die Parallelität.

### Folie 11: Aufgabe 2, Ergebnis Schritt 2

**Titel:** Schritt 2: Bei coalesced-Zugriff sättigt die Bandbreite ab Warp-Breite

**Kopfzeile der Bedingung:** "Muster fest auf coalesced aus Schritt 1"

**Abbildung:** `occupancy.png`, groß. Unterschrift: "Abbildung 4: Bandbreite über der
Work-Group-Größe."

**Folientext:**

```
Work-Group 8: 45,0 GB/s
Work-Group 64: 79,4 GB/s
Darüber Plateau bis 80,2 GB/s
Der Knick liegt genau bei der Warp-Breite 64
```

**Kommentar:**
Zuerst darauf hinweisen, dass hier nur noch coalesced gemessen wird. Auf einem der schlechten
Muster liefe die Kurve gegen dessen eigene Bandbreitengrenze und würde über Occupancy nichts
aussagen. Dann auf den Knick zeigen: Er liegt exakt bei 64 und bestätigt nebenbei die vom Gerät
abgefragte Warp-Breite.

### Folie 12: Aufgabe 2, Deutung

**Titel:** Zerfallende Transaktionen und ungenutzte Lanes

**Folientext:**

```
Die GPU verschmilzt benachbarte Zugriffe eines Warps zu wenigen Transaktionen
Unregelmäßige Adressen zerfallen in viele Transaktionen, jede nur teilweise genutzt
Work-Group unter Warp-Breite belegt trotzdem einen ganzen Warp, Lanes bleiben ungenutzt
Plateau ab 64: genug residente Warps, der Scheduler kann Latenz bereits verbergen
CPU-Referenz: 12,9 GB/s sequenziell, 1,5 GB/s bei gather
```

**Kommentar:**
Zwei verschiedene Effekte auseinanderhalten. Der Anstieg bis 64 ist Lane-Auslastung, das Plateau
darüber ist die Aussage zum Latency-Hiding: Die GPU verbirgt Speicherlatenz nicht über große
Caches, sondern indem der Scheduler auf einen anderen lauffähigen Warp umschaltet. Genügend
residente Warps liegen durch die Gesamtzahl der Work-Items bereits vor, deshalb bringt eine
größere Work-Group nichts mehr. Die CPU verfolgt die andere Strategie und verbirgt Latenz über
Cache-Hierarchie und Prefetching, weshalb sie beim gather ebenfalls einbricht, dort aber über
Cache-Misses statt über zerfallende Transaktionen.

### Folie 13: Fazit

**Titel:** Zwei Regeln folgen unmittelbar aus dem SIMT-Modell

**Folientext:** Tabelle, GPU-Spalte in der Akzentfarbe, CPU-Spalte grau.

```
Messung                            GPU              CPU (NumPy)
Spitzen-Durchsatz                  3085,3 GFLOP/s   14,5 GFLOP/s
Divergenz-Einbruch Grad 1 zu 64    Faktor 56,1      Faktor 2,6
Bandbreite coalesced               78,7 GB/s        12,9 GB/s
Bandbreite gather                  6,9 GB/s         1,5 GB/s
```

```
Verzweigungen innerhalb eines Warps vermeiden
Datenstrukturen so anordnen, dass benachbarte Threads benachbarte Daten lesen
```

**Kommentar:**
Beide Aufgaben zeigen dieselbe Ursache aus zwei Richtungen. Einmal bricht der Kontrollfluss
auseinander, einmal das Datenlayout, und beide Male liegt die Strafe über einer Größenordnung. Wo
die CPU über Sprungvorhersage und Caches einzelne Unregelmäßigkeiten abfängt, bezieht die GPU
ihren Durchsatz ausschließlich aus Gleichförmigkeit. Der Vergleich ist belastbar, weil NumPy seine
Array-Operationen hardware-optimiert in C ausführt, es steht hier nicht Python gegen GPU. Als
Schlusssatz eignet sich: Die GPU ist keine schnellere CPU, sondern eine Maschine mit anderen
Vorbedingungen.

## Backup-Folien

Nur auf Nachfrage einblenden, im selben Stil gesetzt, ohne eigene Überleitung.

- `compute_divergent` vollständig, als Beleg für die konstante FLOP-Zahl.
- Vollständige Occupancy-Tabelle inklusive Warps je Work-Group.
- `make_index` mit der Prüfung auf teilerfremde Schrittweite.
- Geräteeigenschaften aus `results/device_info.json`.

## Erwartbare Fragen

- **Warum Faktor 56 und nicht 64?** Anteile im Kernel ohne Divergenz sowie Speicher- und Startkosten, die nicht mitskalieren. Die Größenordnung bestätigt das Modell, der exakte Wert trägt keine Aussage.
- **Warum sind strided und gather praktisch gleich schnell?** Beide zerstören das Coalescing vollständig. Ist die Lokalität verloren, spielt es für die Hardware keine Rolle, ob die Adressen regelmäßig oder zufällig weit auseinanderliegen.
- **Kostet Divergenz immer so viel?** Nein, sie ist warp-lokal. Verzweigen ganze Warps unterschiedlich, kostet es praktisch nichts. Der Kernel hier streut die Pfade über `get_local_id(0) % DEGREE` maximal fein und erzeugt damit den Worst Case. Wichtig: Das ist eine Ableitung aus dem Modell, nicht gemessen. Als Konsequenz formulieren, nicht als Befund.
- **Ist eine integrierte GPU aussagekräftig?** Die absoluten Werte liegen niedriger als bei einer dedizierten Karte. Die untersuchten Effekte sind Eigenschaften des SIMT-Modells und nicht der Baugröße.
- **Warum PyOpenCL und nicht CUDA?** Geräteunabhängigkeit. Derselbe Code läuft auf AMD, NVIDIA, Intel und als POCL-CPU-Fallback.

## Zeitbudget

| Abschnitt | Minuten |
| --- | --- |
| Folien 1 und 2, Titel und Suite | 1,5 |
| Folien 3 bis 7, Aufgabe 1 | 5,0 |
| Folien 8 bis 12, Aufgabe 2 | 5,0 |
| Folie 13, Fazit | 1,5 |
| Puffer und Fragen | 1,0 |

Die getrennten Ergebnisschritte kosten gegenüber der zusammengefassten Fassung rund zwei Minuten.
Bei einem harten 10-Minuten-Slot entfallen die Aufgabenstellungs-Folien 3 und 8, ihre Frage wandert
dann als Kopfzeile auf die jeweilige Code-Folie. Die Schritttrennung selbst sollte nicht geopfert
werden, sie trägt die Struktur des Vortrags.
