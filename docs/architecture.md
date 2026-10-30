# AI Radar – Softwarearchitektur

**Status:** Architekturentwurf, gemeinsam abgestimmte Grundsatzentscheidungen  
**Stand:** 30.10.2026  
**Geltungsbereich:** MVP

## 1. Ziel und Rahmen

AI Radar sammelt AI-/Tech-Nachrichten aus konfigurierbaren RSS-/Atom-Feeds, extrahiert soweit möglich Artikelvolltexte, analysiert sie mithilfe einer externen LLM-API und stellt sie in einem interaktiven Dashboard sowie einer automatisch aktualisierten News-Wall dar.

Die Anwendung ist im MVP für **einen Nutzer** vorgesehen. Entwicklung erfolgt auf macOS, der spätere Dauerbetrieb auf einem Ubuntu-Rechner. Zugriff zunächst lokal und im Heimnetz, nicht öffentlich über das Internet.

Die fachlichen Anforderungen sind in [`requirements.md`](requirements.md) beschrieben. Diese Architekturdatei ergänzt sie, ersetzt sie aber nicht.

## 2. Architekturprinzip

**Modularer Monolith:** Ein Python-Backend enthält fachlich getrennte Module. Es werden zunächst keine Microservices eingeführt. Das React-Frontend ist eine getrennt entwickelte Webanwendung und kommuniziert über eine HTTP-/JSON-API mit FastAPI.

```text
                       Browser / Monitor
                    React + TypeScript + Vite
                   Dashboard | News-Wall | Settings
                              |
                         HTTP / JSON
                              |
                         FastAPI API
                              |
         +--------------------+--------------------+
         |                    |                    |
    News Collector       AI Analyzer        Personalization
    RSS / Full text      LLM Provider        Interests / Feedback
         |                    |                    |
         +--------------------+--------------------+
                              |
                            SQLite
                   Articles / Analysis / Feeds
                  Interests / Feedback / Status

   Scheduler (15 min) --> Collector --> Analyzer --> Persistence
   External systems: RSS/Atom websites and configurable LLM API
```

Die Darstellung ist logisch: Module müssen nicht jeweils eigene Prozesse sein. Die genaue Aufteilung von API-Prozess und Hintergrund-Worker ist noch offen.

## 3. Technologieentscheidungen

| Bereich | Entscheidung | Begründung |
|---|---|---|
| Architekturstil | Modularer Monolith | Einfacher Betrieb und nachvollziehbare Modulgrenzen |
| Backend/API | Python + FastAPI | Python-basierte Verarbeitung und HTTP-Schnittstelle |
| Frontend | React + TypeScript + Vite | Interaktives Dashboard ohne unnötiges SSR |
| Persistenz | SQLite | Lokale, dateibasierte relationale Datenbank; kein separater DB-Server |
| KI-Analyse | Externe LLM-API, zunächst OpenAI | Modellqualität ohne lokale Inferenz-Infrastruktur |
| KI-Abstraktion | Austauschbare Analyzer-Schnittstelle | Anbieterwechsel und Tests ohne echte API-Aufrufe |
| Hintergrundjobs | Einfacher Python-Scheduler, begrenzte Parallelität | Keine Redis-/Celery-Infrastruktur im MVP |
| Entwicklung | macOS; Frontend und Backend separat startbar | Einfaches Debugging und iteratives Lernen |
| Deployment | Ubuntu, perspektivisch Docker Compose | Reproduzierbarer Betrieb |
| Zugriff | Single-User, lokal / Heimnetz | Kein öffentliches Hosting im MVP |

Bibliotheken für Feed-Parsing, HTTP-Abruf, Extraktion, ORM/Migrationen, Scheduling und Frontend-Routing werden bei Bedarf konkret ausgewählt. Es werden hier keine Versionsnummern festgeschrieben.

## 4. Verantwortlichkeiten der Komponenten

### 4.1 Frontend

- Interaktives Dashboard mit Volltextsuche, Filtern und Sortierung.
- Verwaltung von Feeds, Interessen und persönlichem Feedback.
- News-Wall für dauerhaften Vollbildbetrieb.
- Umschalter **Deutsch / Englisch** für Oberfläche, Zusammenfassungen und Relevanzbegründungen.
- Abfrage neuer Daten alle **60 Sekunden**; keine direkte Kommunikation mit SQLite oder dem LLM-Anbieter.

### 4.2 FastAPI / Application Layer

- HTTP-/JSON-Endpunkte für Artikel, Filter, Feeds, Interessen, Feedback und manuelles Aktualisieren.
- Eingabevalidierung, Fehlerbehandlung und Orchestrierung der fachlichen Module.
- Schutz administrativer Funktionen bei Heimnetzzugriff; konkretes Zugriffskonzept wird vor Freigabe im LAN festgelegt.
- Langlaufende News-/KI-Aufgaben werden **nicht** synchron in HTTP-Anfragen ausgeführt.

### 4.3 News Collector

- Konfigurierbare RSS-/Atom-Quellen im Intervall von **15 Minuten** abrufen.
- Artikel anhand geeigneter Merkmale deduplizieren.
- Artikelvolltext extrahieren, soweit technisch und rechtlich zugänglich; sonst Feed-Auszug nutzen.
- Erkennbar speichern, ob die Analyse auf Volltext oder Auszug beruht.
- Fehler einer Quelle isolieren; keine Umgehung von Paywalls.

### 4.4 AI Analyzer

- Texte zusammenfassen, einer Hauptkategorie und optional mehreren Nebenkategorien zuordnen.
- Allgemeine Bedeutung und persönliche Relevanz (1–5) bewerten und die Bewertung begründen.
- Ergebnisse für **Deutsch und Englisch** bereitstellen und persistent speichern, sodass ein Sprachwechsel keinen erneuten LLM-Aufruf erfordert.
- Anbieterunabhängige Schnittstelle; zunächst OpenAI-Implementierung sowie ein deterministischer FakeAnalyzer für Tests.
- Token-Verbrauch und geschätzte Kosten erfassen; konfigurierbares Kostenbudget vorsehen.

### 4.5 Personalization

- Explizite Interessen mit Priorität verwalten.
- Relevant-/Irrelevant-Feedback speichern und bei späteren Bewertungen berücksichtigen.
- Gelernte Präferenzen getrennt von expliziten Interessen speichern, anzeigen und zurücksetzen können.
- Explizite Interessen nicht automatisch überschreiben.

### 4.6 Persistence

- SQLite speichert Feeds, Artikel, extrahierte Inhalte, Analysen und Sprachversionen, Interessen, gelernte Präferenzen, Feedback und Verarbeitungsstatus.
- Nachrichten bleiben dauerhaft erhalten, sofern der Nutzer sie nicht ausdrücklich entfernt.
- Volltextsuche ist vorgesehen; die konkrete SQLite-FTS5-Integration wird später entschieden.
- Datenbankdatei und andere persistente Daten müssen bei Docker-Updates erhalten bleiben.

### 4.7 Scheduler / Background Processing

- Periodischer Abruf alle **15 Minuten**; manueller Abruf über die API anstoßbar.
- Neue Artikel asynchron zum Nutzerrequest verarbeiten; Parallelität begrenzen.
- Überlappende Läufe und Doppelverarbeitung verhindern.
- Fehlerstatus persistieren und Wiederholungen ermöglichen.
- Das konkrete Ausführungsmodell (im Backend-Prozess oder separater Worker-Prozess desselben Monolithen) bleibt eine Implementierungsentscheidung.

## 5. Wesentliche Datenflüsse

### Automatische Verarbeitung

1. Scheduler startet den Feed-Abruf.
2. Collector lädt Feeds, identifiziert neue Artikel und versucht die Volltextextraktion.
3. Artikel und Bearbeitungsstatus werden in SQLite gespeichert.
4. Analyzer verarbeitet neue Artikel über die konfigurierte externe LLM-API.
5. Kategorien, Scores, Begründungen und deutsche/englische Texte werden gespeichert.
6. Dashboard und News-Wall erhalten beim nächsten Polling die neuen Ergebnisse.

### Interaktion im Dashboard

1. Browser sendet HTTP-Anfrage an FastAPI.
2. API validiert Parameter und liest bzw. aktualisiert Daten in SQLite.
3. API antwortet mit JSON; React aktualisiert die Oberfläche.
4. Relevanzfeedback beeinflusst nachfolgende KI-Bewertungen; vorhandene Bewertungen werden nicht ohne gesonderte Entscheidung rückwirkend neu berechnet.

## 6. Betrieb, Sicherheit und Qualität

- API-Schlüssel nur serverseitig über Umgebungsvariablen / nicht eingecheckte Konfiguration; niemals im Frontend oder Repository.
- Externe Feed-Inhalte und LLM-Ausgaben gelten als nicht vertrauenswürdig. Eingaben validieren, HTML sicher darstellen und Abrufziele begrenzen (insbesondere SSRF-Risiko).
- Für Heimnetzzugriff ist ein geeignetes Zugriffsschutzkonzept erforderlich; Single-User bedeutet nicht automatisch, dass jede Person im LAN administrative Endpunkte nutzen darf.
- Wiederholbare Tests ohne kostenpflichtige LLM-Aufrufe mithilfe eines FakeAnalyzer.
- Automatisierte Prüfungen für Codequalität, Abhängigkeiten und Secrets sind für den Entwicklungsworkflow vorgesehen; konkrete Tools und CI-Konfiguration folgen später.
- Docker Compose wird erst eingeführt, wenn eine erste lauffähige Anwendung vorhanden ist.

## 7. Bewusst noch nicht festgelegt

- Konkrete Python-/Node-Versionen und Paketmanager.
- Datenbankschema, Migrationsstrategie und ORM.
- Feed-/Volltextextraktionsbibliotheken.
- Scheduler-Bibliothek, Queue-Mechanik und Prozessmodell.
- LLM-Modell, Prompt-Design, exakte Token-/Kostenlimits.
- Konkrete API-Endpunkte, UI-Routing und Authentisierung im Heimnetz.
- Repository-Verzeichnisstruktur, Testsuite und CI-Tooling.

Diese Punkte werden inkrementell entschieden, bevor sie implementiert werden. **Keine automatische Erweiterung des Scopes durch Coding-Agenten.**
