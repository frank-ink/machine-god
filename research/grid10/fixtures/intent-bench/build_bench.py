"""Baut INTENT_BENCH_V1 (120 synthetische Aufgaben, Soll-Labels von Claude vorab, unabhaengig vom 4B; keine Pilotaufgaben). Format je Zeile: kategorie|labels(kommagetrennt, leer=ABSTAIN)|text"""
import hashlib, json, sys
RAW = """
indirekt|code|Der Build bricht seit dem letzten Merge mit einem Segfault ab und ich finde die Stelle nicht.
indirekt|code|Meine Schleife läuft endlos, sobald die Liste leer ist.
indirekt|code|Warum wirft mein Programm beim zweiten Aufruf einen NullPointer?
indirekt|code|Die Seite lädt nach meinem Update zehnmal langsamer, vermutlich wegen der Datenbankabfrage in der Controller-Klasse.
indirekt|code|Ich brauche etwas, das alle Dateien in einem Ordner nach Datum sortiert umbenennt, am liebsten in Bash.
indirekt|code|Kannst du mir die Sortierung in O(n log n) hinbekommen? Mein Ansatz ist quadratisch.
indirekt|code|Die Tests laufen lokal, aber in der CI nicht, und ich sehe nur exit 1.
indirekt|code|Kannst du dieses Regex so bauen, dass es auch Umlaute in Namen frisst?
indirekt|code|Der Parser verschluckt bei mir das letzte Element, da muss irgendwo ein Off-by-one sein.
indirekt|json|Ich möchte die Bestellung so zurückbekommen, dass mein Importer sie ohne Nachbearbeitung einlesen kann: Felder name, menge, preis.
indirekt|json|Mein Frontend erwartet für jeden Nutzer genau die Felder id, name und rolle, nichts sonst.
indirekt|json|Pack die Ergebnisse so ein, dass ich sie direkt in die Konfig-Datei der API werfen kann, Schlüssel-Wert-Paare reichen.
indirekt|json|Die Antwort muss maschinenlesbar sein, mein Skript parst sie mit einem Standard-Parser.
indirekt|json|Der Kunde will seine Daten in unserem Schema: ein Objekt mit einer Liste von Positionen, jede mit Artikelnummer und Anzahl.
indirekt|reason|Drei Schalter, eine Lampe im Nebenraum, ich darf nur einmal hingehen. Wie finde ich den richtigen?
indirekt|reason|Wenn ich fünf Prozent mehr Miete zahle, aber zwölf Prozent weniger Strom, lohnt sich der Umzug?
indirekt|reason|Alle Katzen, die ich kenne, mögen Fisch, Mimi mag keinen Fisch. Kann Mimi trotzdem eine Katze sein?
indirekt|reason|Zwei Züge fahren aufeinander zu, der eine mit 80, der andere mit 120 km/h, Abstand 300 km. Wann treffen sie sich?
indirekt|reason|Ich weiß nicht, ob ich das Angebot annehmen soll; geh es Punkt für Punkt mit mir durch, Vorteile gegen Risiken.
indirekt|reason|Ich habe zwei Verträge zur Auswahl, einer günstiger, einer flexibler; entscheide mit mir, welcher zu einer Gründung passt.
indirekt|reason|Warum gewinnt in dem Spiel immer, wer zuerst zieht? Beweise es oder widerlege es.
indirekt|reason|Kaufen oder weiter mieten? Ich möchte beide Varianten über zwanzig Jahre gegeneinander abgewogen sehen.
indirekt|long|Hier sind die gesamten 200 Seiten des Vertrags, was steht zu den Kündigungsfristen?
indirekt|long|Ich füge das komplette Protokoll der letzten sechs Sitzungen ein, zeig mir die roten Fäden.
indirekt|long|Das ganze Buch liegt unten, ich brauche pro Kapitel zwei Sätze.
indirekt|long|Im Anhang stehen die kompletten Logdateien der letzten Woche, wo beginnt das Problem?
indirekt|long|Ich muss mir ein ganzes Semester Skripte durchlesen, mach mir daraus eine Lernübersicht.
indirekt|long|Hier ist mein ganzer Mailverlauf der letzten zwei Jahre, was wurde mit dem Lieferanten eigentlich vereinbart?
indirekt|tool|Schau mal nach, ob die Datei config.yaml im Projektordner schon existiert.
indirekt|tool|Was kostet gerade der Flug Wien-Berlin am Freitag? Ich brauche den aktuellen Preis.
indirekt|tool|Ist der Server unter 10.0.0.5 erreichbar?
indirekt|tool|Leg mir einen Termin für morgen um neun an.
indirekt|tool|Wie viel Platz ist auf der Platte noch frei?
indirekt|tool|Schick die Zusammenfassung an das Team.
indirekt|tool|Mach ein Backup von meinem Dokumentenordner.
indirekt|tool|Der Dienst hängt, bring ihn bitte wieder zum Laufen.
indirekt|tool|Mein Skript soll jede Nacht um zwei laufen und die Ergebnisse als Datei ablegen, richte das ein.
indirekt|tool|Sieh nach, welche Prozesse gerade am meisten Speicher fressen.
indirekt|tool|Ruf die Webseite auf und lies mir die Öffnungszeiten vor.
indirekt|tool|Prüf bitte, ob mein Port 8080 gerade belegt ist.
explizit|code|Schreibe eine Python-Funktion, die alle Primzahlen bis n liefert.
explizit|code|Debugge diesen Stacktrace: IndexError in Zeile 42.
explizit|code|Implementiere eine verkettete Liste in Rust.
explizit|code|Refaktoriere die Klasse Kunde und teile sie in zwei Module.
explizit|json|Antworte ausschließlich als JSON mit den Feldern titel und autor.
explizit|json|Gib mir ein JSON-Schema für eine Adresse.
explizit|json|Liefere die Antwort als JSON-Objekt.
explizit|reason|Löse Schritt für Schritt: 3x + 7 = 25.
explizit|reason|Beweise, dass die Wurzel aus 2 irrational ist.
explizit|reason|Denke gründlich nach und begründe, warum das Argument ungültig ist.
explizit|reason|Berechne den Zinseszins über zehn Jahre bei vier Prozent und erkläre die Rechnung.
explizit|long|Fasse den folgenden langen Text zusammen.
explizit|long|Analysiere das gesamte Dokument mit allen Anhängen.
explizit|long|Verarbeite diese lange Konversation und liste alle offenen Punkte auf.
explizit|tool|Führe den Befehl ls -la im Home-Verzeichnis aus.
explizit|tool|Suche im Web nach dem aktuellen Wetter in Wien.
explizit|tool|Öffne die Datei notizen.txt und lies sie vor.
explizit|tool|Rufe die API unter /status auf und zeig das Ergebnis.
explizit|tool|Lösche die temporären Dateien im Ordner /tmp/build.
explizit|tool|Starte das Skript backup.sh jetzt.
mehrfach|code,json|Schreibe ein Skript, das die Log-Dateien einliest und mir das Ergebnis als JSON ausgibt.
mehrfach|tool,code|Führe die Tests aus und behebe den Fehler, den du findest.
mehrfach|tool,code|Such im Web nach der Dokumentation und implementiere damit den Client.
mehrfach|long,json|Fasse die langen Notizen zusammen und gib mir die Kernpunkte als JSON.
mehrfach|reason,json|Berechne Schritt für Schritt die Auslastung und liefere das Ergebnis als JSON.
mehrfach|long,reason|Lies den gesamten Bericht, überlege gründlich und sag mir, welche Option am besten ist.
mehrfach|tool,code|Öffne die Datei, finde den Bug und schreibe den Patch.
mehrfach|tool,reason,json|Hol die aktuellen Kurse per API, rechne den Durchschnitt aus und gib ihn als JSON zurück.
mehrfach|long,code|Analysiere das komplette Repository und schreibe eine Funktion, die den Fehler behebt.
mehrfach|tool,json|Rufe den Endpunkt ab und strukturiere die Antwort als JSON.
mehrfach|reason,code|Beweise die Korrektheit meiner Sortierfunktion und schreibe die Tests dazu.
mehrfach|tool,long|Durchsuche meinen Ordner nach allen Verträgen und fasse sie zu einer Übersicht zusammen.
mehrfach|code,reason|Implementiere die Funktion und erkläre Schritt für Schritt, warum sie terminiert.
mehrfach|tool,json|Lies die Konfigurationsdatei ein und gib mir die Einstellungen als JSON.
mehrfach|tool,code|Starte das Programm, beobachte die Ausgabe und schreib mir ein Skript, das den Fehler reproduziert.
mehrfach|reason,json|Prüfe gründlich, ob die Berechnung stimmt, und liefere die Korrektur als JSON-Patch.
mehrfach|tool,reason|Sieh im Netz nach den aktuellen Zahlen und rechne mir vor, ob sich die Investition rechnet.
mehrfach|long,code|Lies das ganze Handbuch und schreibe daraus ein Installationsskript.
mehrfach|long,json,tool|Generiere aus dem Dokument ein JSON mit allen Terminen und leg die Termine im Kalender an.
mehrfach|tool,reason|Führe die Messung aus, werte sie Schritt für Schritt aus und schreibe das Ergebnis in eine Datei.
falle|reason|Schreib bitte keinen Code, erkläre mir nur das Prinzip der Rekursion.
falle|code|Du sollst das Skript nicht ausführen, nur schreiben.
falle|code|Gib mir keine JSON-Ausgabe, sondern schreib die Funktion, die sie erzeugen würde.
falle|reason|Kein Skript nötig, rechne einfach Schritt für Schritt nach: 17 mal 23.
falle|tool|Lies nicht die ganze Datei, nur die erste Zeile von notizen.txt.
falle|tool|Auf keinen Fall löschen! Zeig mir nur, welche Dateien im Ordner liegen.
falle|tool|Statt JSON hätte ich gern eine Aufzählung der Städte, aus denen die Kunden kommen, hol sie aus der Kundendatei.
falle|tool|Es ist nicht nötig, das Netz zu durchsuchen, aber öffne bitte die lokale README.
falle||Ich will kein JSON, sondern ganz normalen Fließtext über Lieferzeiten.
falle||Führe nichts aus, sag mir nur kurz, was der Befehl rm -rf bewirken würde.
falle||Der Code-Review gestern war anstrengend.
falle||Mein Hund heißt Json.
falle||Ausführliche Antwort bitte: Wie war dein Tag?
falle||Ich suche nach dem Sinn des Lebens.
falle||Ich schreibe morgen eine Klausur über Tiefensuche und Suchbäume, drück mir die Daumen.
falle||Bitte nicht im Web suchen, antworte aus deinem Wissen: Wer schrieb Faust?
falle||Nicht zusammenfassen, übersetze nur den ersten Satz ins Englische.
falle||Ohne Rechenweg, nur das Ergebnis von 12 mal 12.
falle||Das Wort Funktion kommt in meiner Mathehausarbeit oft vor, kannst du Synonyme nennen?
falle||Ich habe heute keinen Code geschrieben und fühle mich schlecht.
abstain||Hallo, wie geht's?
abstain||Danke, das war's für heute.
abstain||Was ist die Hauptstadt von Frankreich?
abstain||Erzähl mir einen Witz.
abstain||Ich bin müde.
abstain||Mach was.
abstain||Hm.
abstain||Was meinst du dazu?
abstain||Welche Farbe hat der Himmel?
abstain||Kannst du mir helfen?
abstain||Schön, dass es dich gibt.
abstain||Ich habe eine Frage.
abstain||Wer war Goethe?
abstain||Übersetze Guten Morgen ins Spanische.
abstain||Gib mir ein Rezept für Pfannkuchen.
abstain||Wie schreibt man Rhythmus?
abstain||Das Wetter ist heute schön.
abstain||Wie heißt du?
abstain||Sag etwas Nettes.
abstain||Wie war dein Wochenende?
"""
out = []
for i, ln in enumerate([l for l in RAW.strip().split("\n") if l.strip()]):
    cat, lab, txt = ln.split("|", 2)
    out.append({"id": "IB%03d" % (i + 1), "kat": cat, "text": txt, "labels": sorted(x for x in lab.split(",") if x), "abstain": not lab})
body = "\n".join(json.dumps(o, ensure_ascii=False, sort_keys=True) for o in out) + "\n"
open("INTENT_BENCH_V1.jsonl", "w").write(body)
h = hashlib.sha256(body.encode()).hexdigest()
open("INTENT_BENCH_V1.sha256", "w").write(h + "\n")
from collections import Counter
print(len(out), dict(Counter(o["kat"] for o in out)), h)
