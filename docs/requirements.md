# AI Radar – Anforderungen (MVP)

**Status:** Fachliche Anforderungen abgestimmt · **Stand:** 30.10.2026  
**Zweck:** Verbindliche Grundlage für Architektur, Implementierung und Abnahmetests.  
**Nicht Bestandteil dieses Dokuments:** Technologiewahl, Datenbankschema, Projektstruktur und konkrete Implementierung.

## 1. Problem und Ziel

AI- und Technologieneuigkeiten sind über viele Quellen verteilt. Relevante Entwicklungen zu finden, einzuordnen und regelmäßig zu verfolgen ist zeitaufwendig.

**AI Radar** sammelt Nachrichten zentral, bereitet sie mithilfe von KI auf, bewertet sowohl ihre allgemeine Bedeutung als auch ihre **persönliche Relevanz** und stellt die Ergebnisse in einem interaktiven Dashboard sowie einer dauerhaft laufenden News-Wall bereit.

## 2. Funktionale Anforderungen

### 2.1 Nachrichtenquellen und Abruf

| ID | Anforderung |
|---|---|
| FR-01 | Nutzer können RSS-/Atom-Quellen hinzufügen, bearbeiten und entfernen. |
| FR-02 | Neue Artikel werden automatisch alle **15 Minuten** abgerufen. |
| FR-03 | Im Dashboard kann ein Abruf manuell ausgelöst werden. |
| FR-04 | Mehrfach gefundene Artikel werden dedupliziert und nicht doppelt gespeichert. |
| FR-05 | Fehler einer Quelle verhindern nicht die Verarbeitung anderer Quellen. |
| FR-06 | Wenn zugänglich, wird der **vollständige Artikeltext** abgerufen und von Navigation, Werbung und anderen irrelevanten Seitenelementen bereinigt. |
| FR-07 | Ist der Volltext nicht zugänglich, wird die verfügbare Feed-Beschreibung verwendet. Die Analysebasis (Volltext/Auszug) ist erkennbar. Paywalls und Zugriffsbeschränkungen werden nicht umgangen. |

### 2.2 KI-Aufbereitung

| ID | Anforderung |
|---|---|
| FR-08 | Jeder verarbeitbare Artikel erhält eine kurze KI-Zusammenfassung. |
| FR-09 | Jeder Artikel erhält **eine Hauptkategorie** und optional mehrere Nebenkategorien: `Releases`, `Features`, `Security`, `Use Cases`, `Other`. |
| FR-10 | AI Radar bewertet die **allgemeine Bedeutung** einer Nachricht getrennt von ihrer **persönlichen Relevanz**. |
| FR-11 | Die persönliche Relevanz wird auf einer Skala von **1–5** bewertet. |
| FR-12 | AI Radar zeigt eine verständliche Begründung für die persönliche Relevanzbewertung. |
| FR-13 | Fehler bei der KI-Analyse werden nachvollziehbar erfasst und dürfen die gesamte Nachrichtenverarbeitung nicht stoppen. Fehlgeschlagene Analysen können später erneut versucht werden. |

### 2.3 Interessenprofil und Feedback

| ID | Anforderung |
|---|---|
| FR-14 | Nutzer können Interessen/Themen hinzufügen, entfernen und mit **Niedrig / Mittel / Hoch** gewichten. |
| FR-15 | Nutzer können einzelne Nachrichten als **relevant** oder **irrelevant** markieren. |
| FR-16 | Dieses Feedback beeinflusst zukünftige persönliche Relevanzbewertungen. |
| FR-17 | Automatisch abgeleitete Interessen/Präferenzen sind sichtbar und von manuell festgelegten Interessen getrennt. |
| FR-18 | Gelernte Präferenzen können zurückgesetzt werden, ohne manuelle Interessen zu löschen. |
| FR-19 | Das Dashboard enthält einen Bereich **„Interessen & Personalisierung“**. |

### 2.4 Interaktives Dashboard

| ID | Anforderung |
|---|---|
| FR-20 | Artikel sind per Freitext in **Titel und Artikelinhalt** durchsuchbar. |
| FR-21 | Filter nach Kategorie, persönlicher Relevanz und Veröffentlichungszeitraum stehen bereit. |
| FR-22 | Artikel lassen sich nach Aktualität oder persönlicher Relevanz sortieren. |
| FR-23 | Dashboard-Daten werden spätestens alle **60 Sekunden** auf Aktualisierungen geprüft. |
| FR-24 | Das Dashboard ermöglicht Relevanzfeedback und die Verwaltung des Interessenprofils. |

### 2.5 News-Wall

| ID | Anforderung |
|---|---|
| FR-25 | Eine separate, für Vollbild/Dauerbetrieb geeignete News-Wall zeigt Nachrichten ohne notwendige Benutzerinteraktion. |
| FR-26 | Nachrichten werden standardmäßig nach persönlicher Relevanz sortiert. |
| FR-27 | Ein einstellbarer Mindest-Relevanzscore (**1–5**) bestimmt, welche Artikel erscheinen. |
| FR-28 | Neue, besonders relevante Nachrichten werden sichtbar hervorgehoben. |
| FR-29 | Die News-Wall prüft spätestens alle **60 Sekunden** auf Aktualisierungen. |

### 2.6 Dauerhafte Datenhaltung

| ID | Anforderung |
|---|---|
| FR-30 | Artikel, Quellen-URL, Veröffentlichungsdatum und extrahierter Inhalt werden dauerhaft gespeichert. |
| FR-31 | KI-Analysen einschließlich Kategorien, Scores, Begründungen und Analysebasis werden dauerhaft gespeichert. |
| FR-32 | Manuelle Interessen, gelernte Präferenzen und Artikel-Feedback werden dauerhaft gespeichert. |
| FR-33 | Verarbeitungsstatus und relevante Fehler werden gespeichert, um Wiederholungen zu ermöglichen. |
| FR-34 | Es erfolgt **keine automatische Löschung** älterer Nachrichten; historische Artikel bleiben durchsuchbar. |
| FR-35 | Mehrsprachigkeit AI Radar muss Deutsch und Englisch unterstützen. Nutzer können die Anzeigesprache im Frontend umschalten. Dies gilt für Dashboard, News-Wall, KI-Zusammenfassungen und Relevanzbegründungen.

Beide Sprachversionen der KI-Inhalte werden dauerhaft gespeichert. Kategorien und Relevanzscores bleiben sprachunabhängig. Originalartikel werden nicht verändert. |

## 3. Nichtfunktionale Anforderungen

| ID | Anforderung |
|---|---|
| NFR-01 | Die Anwendung soll lokal betrieben werden können und perspektivisch dauerhaft auf einem Ubuntu-Rechner laufen. |
| NFR-02 | Externe Artikel und Feed-Inhalte gelten als **nicht vertrauenswürdige Daten**; sie dürfen keine Anweisungen an das KI-System oder Entwicklungswerkzeuge erteilen. |
| NFR-03 | Netzwerkzugriffe, externe Inhalte und gespeicherte Daten müssen sicher verarbeitet werden; insbesondere sind SSRF, XSS und Secret-Leaks zu berücksichtigen. |
| NFR-04 | Einzelne Fehler in Quellenabruf oder KI-Analyse dürfen den Gesamtdienst nicht zum Absturz bringen. |
| NFR-05 | Die Entwicklung erfolgt schrittweise: kleine Aufgaben, nachvollziehbare Entscheidungen, geeignete Tests und menschliche Freigabe. |
| NFR-06 | Der Coding-Agent soll mit eingeschränkten Berechtigungen/Sandbox arbeiten. Security-Reviews und automatisierte Scans sollen vor Pull-Request-Merges stattfinden. |

## 4. Bewusste MVP-Grenzen

- Keine autonome Entdeckung neuer Nachrichtenquellen durch Websuche; Quellen werden konfiguriert.
- Keine Umgehung von Paywalls oder Zugriffsbeschränkungen.
- Keine automatische Löschung historischer Artikel.
- Keine Festlegung auf Datenbank, KI-Anbieter, Frontend-Framework oder Agenten-Skills in dieser Anforderungsdatei.

## 5. Noch fachlich zu klären

Diese Punkte sind **noch nicht entschieden** und werden nicht stillschweigend implementiert:

- **Zugriff:** Nur eine Person/lokal oder auch andere Geräte im Heimnetz?
- **Interessenlernen:** Nach welchen nachvollziehbaren Regeln beeinflusst Feedback spätere Scores? Wie gehen wir mit wenig Feedback um?
- **Volltext:** Welche Quellen und Nutzungsbedingungen erlauben Abruf, Speicherung und Verarbeitung? Wie verfahren wir mit nicht extrahierbaren Artikeln?
- **Bewertungsmaßstab:** Soll auch die allgemeine Bedeutung auf einer Skala von 1–5 liegen?
- **Darstellung:** Wie viele Nachrichten soll die Wall gleichzeitig zeigen und wie soll sie zwischen Inhalten wechseln?

## 6. Nächster Projektschritt

Die Anforderungen gemeinsam kurz prüfen, offene fachliche Entscheidungen priorisieren und **erst danach** eine einfache Systemarchitektur skizzieren. Entwicklungsumgebung, Sandbox, `CLAUDE.md`, Skills und Code folgen schrittweise, wenn sie benötigt werden.
