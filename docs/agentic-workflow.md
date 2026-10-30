# AI Radar – Issue-gesteuerter Agenten-Workflow

**Status:** eingerichtet, noch nicht im Echtbetrieb erprobt · **Stand:** 30.10.2026

Mit `/autonomous-feature` bearbeitet Claude Code **genau ein** freigegebenes GitHub-Issue: von der Auswahl über Implementierung, Tests und Reviews bis zum Pull Request. Der Merge bleibt immer eine menschliche Entscheidung.

## Rollen und Freigaben

| Schritt | Wer | Bedeutung |
|---|---|---|
| Issue anlegen (Vorlage *Feature* oder *Bug*) | Mensch | Bekommt automatisch `needs-triage` |
| Label `agent-ready` setzen | Mensch | Freigabe des Issue-Umfangs zur Implementierung |
| `/autonomous-feature [Nr.] [--dry-run]` aufrufen | Mensch | Autorisiert genau einen Durchlauf bis zum PR |
| PR prüfen und mergen | Mensch | Einzige Stelle, an der Code nach `main` gelangt |

Ein Issue ist nur `agent-ready`, wenn es prüfbare Akzeptanzkriterien und einen Abschnitt „Nicht im Umfang“ hat und keine Architektur- oder Abhängigkeitsentscheidung erfordert.

## Ablauf

Definiert in `.claude/skills/autonomous-feature/SKILL.md`; die Detailregeln stehen in den aufgerufenen Skills.

0. Vorprüfung: sauberer Arbeitsstand, GitHub-Zugriff, aktueller `origin/main`
1. Issue mit `agent-ready` auswählen (oder übergebene Nummer)
2. Anforderungen und Akzeptanzkriterien prüfen – bei `--dry-run` endet der Lauf hier
3. Branch `feat/issue-<Nr>-<kurzname>` von `origin/main`
4. –5. Implementierung und Tests über den Skill `feature-development`
6. Skills `code-review` und `security-review` über die gesamte Änderung gegen `origin/main`, einschließlich uncommitteter und neuer Dateien
7. Bestätigte Findings beheben – höchstens zwei Zyklen
8. Commit, Push des Feature-Branches, `gh pr create`
9. PR-Beschreibung: Umsetzung, Checks, Review-Ergebnisse, Risiken
10. CI prüfen, höchstens zwei Korrekturversuche; danach Ende, kein weiteres Issue

**Abbruch mit Rückfrage** u. a. bei unklaren Anforderungen, Architekturentscheidungen, neuen Abhängigkeiten oder kostenpflichtigen Diensten, bestätigten **High-/Critical**-Security-Findings, ausgeschöpften Zyklen und blockierten Befehlen.

## Sicherheitsgrenzen

1. **Maßgeblich: GitHub-Ruleset bzw. Branch Protection für `main`.** Nur sie verhindert technisch Direkt-Pushes, Force-Pushes und Merges ohne grüne CI.
2. **Zusätzlich: Deny-Regeln** in der Sitzungs-Konfiguration (z. B. `gh pr merge`, Force-Push). Sie sind präfixbasiert und daher umgehbar (etwa `git push origin HEAD:main`) – keine alleinige Sicherheitsgrenze.
3. **Sandbox:** Nur die gelisteten `gh`- und `git push`/`fetch`-Befehle laufen außerhalb der Sandbox; Tests, Builds und alle übrigen Befehle bleiben sandboxed.
4. Skill-Anweisungen und `CLAUDE.md` sind Leitlinien, keine Sicherheitsgrenze.

## Einmalige Einrichtung

1. **Labels** anlegen: `agent-ready`, `needs-triage`.
2. **Ruleset für `main`**: Pull Request erforderlich, Status-Checks der CI erforderlich (alle Jobs aus `ci.yml`), Force-Push und Löschen blockiert, keine Bypass-Rechte für den verwendeten Token.
3. **Sitzungs-Konfiguration** außerhalb des Repositorys ablegen, z. B. `~/.claude/ai-radar-autonomous.settings.json`, mit `sandbox.excludedCommands` für die benötigten `gh`-/`git`-Befehle und den Deny-Regeln. Ausnahmen aus `.claude/settings.json` des Projekts werden von Claude Code ignoriert; sie wirken nur aus User-Settings, Managed Policy oder einer per `--settings` übergebenen Datei.
4. **Start** einer Workflow-Sitzung:

   ```bash
   claude --settings ~/.claude/ai-radar-autonomous.settings.json
   ```

5. **GitHub-Login** prüfen: `gh auth status` (außerhalb der Sandbox).
6. **Testlauf:** `/autonomous-feature --dry-run`

## Nutzung

```text
/autonomous-feature --dry-run      # nur Auswahl und Bewertung, keine Änderungen
/autonomous-feature 12             # Issue #12 bis zum PR bearbeiten
/autonomous-feature                # ältestes geeignetes agent-ready-Issue
```

Der Skill ist mit `disable-model-invocation: true` markiert und startet nur durch ausdrücklichen Aufruf.
