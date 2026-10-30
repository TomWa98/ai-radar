# AI Radar – Frontend Design Specification

**Status:** Approved visual direction  
**Applies to:** All current and future frontend implementation issues  
**Design language:** Silver / Monochrome · Dark mode · Intelligence × Editorial  
**Primary layout:** Editorial Grid  
**Information density:** Balanced  
**Binding decisions:** 1–8 of 2026-10-30, incorporated below and listed in section 11

## 1. Product and design goals

AI Radar is a self-hosted AI/technology intelligence application. The interface should help users rapidly understand new developments, assess relevance, and act on useful information. It is not a generic analytics dashboard or a traditional news portal.

The design combines:
- **Intelligence dashboard:** clear hierarchy, meaningful metadata, filters, status, and management controls.
- **Editorial news product:** strong headlines, readable summaries, prominent important stories, and a coherent article grid.

Priorities: readability, relevance, information hierarchy, restrained visual language, fast interaction, and operational clarity. Avoid decorative charts, exaggerated gradients, glowing borders, stock imagery, and excessive animation.

## 2. Visual system

### 2.1 Colors

| Token | Hex | Use |
|---|---|---|
| `--color-bg` | `#0C0D10` | Application background |
| `--color-surface` | `#1C1F24` | Cards, panels |
| `--color-surface-hover` | `#252A31` | Hovered cards and navigation |
| `--color-border` | `#2A2D33` | Decorative separators only (see 2.1 note) |
| `--color-text-primary` | `#F3F4F6` | Headlines, key information |
| `--color-text-secondary` | `#9AA3AE` | Descriptions, timestamps, metadata |
| `--color-accent` | `#D5D9DF` | Active navigation, selection, primary actions |
| `--color-focus` | `#D5D9DF` | Visible keyboard focus ring |

Use a predominantly monochromatic interface. The silver accent is not a reason to make every element bright. Category and severity indicators may use additional muted semantic colors, but these must remain secondary to the monochrome identity and must not be the sole way information is conveyed.

Ensure text/background contrast meets WCAG AA where applicable. Adjust secondary text or surfaces if measured contrast falls short.

**Interactive boundaries (binding, decision 8):** Boundaries that identify interactive UI components — e.g. input and select outlines, button borders, toggles, checkboxes — and focus indicators must meet WCAG 2.1 SC 1.4.11 (at least 3:1 against adjacent colors). `--color-border` (`#2A2D33`, about 1.2:1 on `--color-surface`) is only for decorative separators and card outlines; interactive boundaries need a separate, sufficiently contrasting token. `--color-focus` meets this (about 11.7:1 on `--color-surface`).

### 2.2 Typography and spacing

- **Font stack (binding, decision 2):** system font stack with Inter/Geist only as optional *locally installed* fonts, e.g. `font-family: Inter, Geist, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;`. No font files, no font package or other new dependency, no font download.
- Clear hierarchy: page title, section title, article headline, summary, metadata.
- Article headlines should be readable without oversized typography. Summaries use comfortable line height.
- Use a consistent spacing scale (4/8/12/16/24/32 px), rather than arbitrary values.
- Corners: generally 8–12 px; avoid pill-shaped cards.
- Borders and shadows: subtle; do not rely on heavy shadows to separate dark surfaces.
- Motion: brief and purposeful. Respect `prefers-reduced-motion`.

## 3. Information architecture

Primary desktop navigation uses a persistent left sidebar. The exact labels should match existing product terminology and available functionality:

1. **Overview** – overview and prioritized intelligence.
2. **Articles** – searchable/filterable article collection.
3. **Interests** – personalization and feedback settings.
4. **Sources** – feed management and refresh status.
5. **News Wall** – full-screen display mode.

A restrained top bar contains the product identity and relevant status/actions (e.g., last successful refresh, settings if implemented). Do not show invented system metrics or fake live status.

If a destination is not implemented yet, do not present it as a functional control. Either hide it until available or show a clearly disabled state, consistent with the existing issue scope.

**Binding decisions:**
- **Overview / Articles (decision 3):** The dashboard issue (#25) implements **Overview** as the Editorial Grid with search, filters, and sorting. **Articles** stays hidden until an issue covers it; no additional view is created.
- **Refresh status in the top bar (decision 6):** Label it **„Letzter abgeschlossener Abruf“ / “Last completed refresh”**, not “last successful refresh”, as long as the API provides no reliable success status (currently only `last_started_at`/`last_finished_at` from `GET /api/refresh`).

## 4. Dashboard: Editorial Grid

**Chosen layout: B – Editorial Grid.** This is the default article presentation, not a conventional uniform list.

### 4.1 Structure

- Compact overview heading and context; no oversized hero banner.
- At most a small number of useful summary metrics if real backend data exists.
- Search/filter/sort controls where supported by existing APIs.
- **One prominent lead story** when a suitable article exists, followed by a balanced grid of smaller cards.
- Lead story selection should use available relevance/recency data, with deterministic fallbacks. Do not fabricate rankings.
- Responsive columns: typically two columns on ordinary desktop content widths, optionally three on wide screens if readability remains good; one column on mobile.
- Provide clear empty, loading, error, and no-results states.

### 4.2 Article card content

Use only fields actually available in the API. Where available, show:

- Category / channel (e.g., Release, Feature, Security, Use Case).
- Headline and source.
- Publication time, with clear fallback for missing timestamps.
- AI-generated summary, visibly distinguished from original publisher content.
- Relevance score and/or general importance, clearly labeled and not conflated.
- **Analysis basis (binding, decision 7, FR-07):** whether the analysis is based on the full text or the feed excerpt must be visible for every article that has an analysis.
- Link to original article.
- Feedback controls when supported by the current feature.

The lead story may show a longer summary and stronger typography; regular cards should be scannable. Clamp long excerpts visually where appropriate while preserving access to the full text or source. Never generate placeholder article content in production views.

### 4.3 Interactions

- Clicking an article opens its detail view if implemented, otherwise the original source via an explicit link.
- Filters, search, sorting, feedback and manual refresh must communicate loading and error states.
- Do not hide important actions exclusively behind hover.
- Use semantic buttons and links, keyboard navigation, visible focus states and accessible names.
- An optional compact list view may be added **only if covered by an issue or explicitly approved**. It is not required for the initial frontend MVP.

## 5. News Wall

The News Wall is a **separate full-screen presentation mode**, not the dashboard with the sidebar removed.

- Intended for an always-on external monitor.
- No persistent dashboard sidebar, filters, or form controls.
- Large readable headlines and concise summaries, suitable for viewing from a distance.
- Asymmetric editorial layout: a prominent top story plus supporting cards, within a maximum of nine visible cards if consistent with the approved architecture.
- Auto-rotation and refresh follow the timing/selection rules already documented in `docs/architecture.md` and `docs/requirements.md`; do not redefine those rules in the visual spec.
- Display only grounded data; show an intentional empty/offline state when needed.
- **Settings (binding, decision 5):** wall settings (e.g. the minimum relevance score) are reached through a discreet, dismissible overlay. In normal operation no controls are visible; the overlay must still be keyboard-accessible and must not stay visible permanently.
- Provide discreet but accessible controls to exit or pause the wall if these are in scope.
- Avoid layout jumps and distracting transitions. Support reduced motion.
- Time/status indicators must be truthful; no simulated 'live' indicator.

## 6. Responsive behavior

- **Desktop:** fixed sidebar, generous article content width, editorial grid.
- **Tablet:** narrower navigation or collapsible sidebar, reduced grid columns.
- **Mobile:** single-column articles, accessible compact navigation, usable filters and touch targets.
- No horizontal scrolling for primary content at common viewport widths.
- Design the News Wall primarily for landscape displays but degrade gracefully at smaller sizes.

## 7. Data, UX, and operational states

- Use real backend responses in integrated views; mock data is acceptable in isolated tests, Storybook-like fixtures, or clearly marked development previews only.
- Clearly distinguish **importance** from **personal relevance**.
- Mark missing AI analysis or failed analysis honestly; show source excerpts where appropriate rather than pretending a summary exists.
- Loading, empty, error, stale, offline, and refresh-in-progress states must be deliberate and consistent.
- Use locale-aware date/time formatting. DE/EN behavior follows the existing requirements; do not create a new internationalization framework unless needed by the approved issue.
- Avoid adding charts or KPI panels unless they serve a real user decision and use actual data.

## 8. Implementation constraints

- Follow the stack and dependencies already approved in `docs/architecture.md` (React, TypeScript, Vite, testing tools, etc.).
- Use reusable design tokens and components for cards, buttons, inputs, navigation and status states.
- Avoid adding a UI component framework, icon package, animation package, or other dependency without checking existing decisions and the issue scope.
- Respect the existing API contracts; do not invent backend endpoints.
- Add appropriate component tests and accessibility checks for implemented interactions. **Accessibility checks (binding, decision 4)** use the existing Testing Library tools (role/name queries), semantic HTML, and keyboard and focus tests; no additional accessibility dependency (e.g. axe).
- Frontend changes should be reviewable in small, issue-scoped PRs.
- This document controls **visual/interaction design**, not functional scope. If it conflicts with accepted functional requirements or architecture decisions, surface the conflict for review rather than silently overriding them.

## 9. Acceptance checklist for frontend PRs

- [ ] Uses the Silver / Monochrome token palette consistently.
- [ ] Fits the Hybrid Intelligence × Editorial style and balanced density.
- [ ] Uses Editorial Grid for the primary article dashboard.
- [ ] Keeps News Wall visually and functionally distinct.
- [ ] Supports responsive layout and keyboard operation.
- [ ] Provides truthful loading, empty, error, and data states.
- [ ] Uses actual API fields in integrated views; no fake production content.
- [ ] Does not introduce unrelated features or unapproved dependencies.
- [ ] Includes appropriate tests and passes the established CI checks.

## 10. Implementation sequence

1. Establish global tokens, typography, responsive shell and sidebar navigation as part of the frontend foundation issue **#23** (decision 1) — without any functional views.
2. Build data-driven article cards and Editorial Grid in the dashboard issue.
3. Add filter/search/feedback interactions as their respective issues permit.
4. Build the dedicated News Wall under its own issue.

Do not implement all four steps in one PR. Each autonomous feature run should remain scoped to one GitHub issue.

## 11. Binding decisions (2026-10-30)

Decided by the project owner after the conflict review of this specification. They are incorporated in the sections above and reflected in the affected issues.

| # | Decision | Section / issue |
|---|---|---|
| 1 | #23 additionally covers design tokens, typography, responsive app shell, and sidebar navigation; no functional views. | 10, #23 |
| 2 | System font stack with Inter/Geist as optional local fonts and `system-ui` fallback; no new dependency, no font download. | 2.2, #23 |
| 3 | #25 first implements “Overview” as the Editorial Grid with search, filters, and sorting; “Articles” stays hidden; no new view. | 3, #25 |
| 4 | Accessibility checks with existing Testing Library means, semantic HTML, keyboard and focus tests; no new dependency. | 8, all frontend issues |
| 5 | News Wall settings via a discreet, dismissible overlay; no visible controls in normal operation. | 5, #29 |
| 6 | Top bar shows “Letzter abgeschlossener Abruf” instead of “Letzter erfolgreicher Abruf” as long as the API provides no reliable success status. | 3, #28 |
| 7 | #25 uses the Editorial Grid; the analysis basis (FR-07) must be visible for articles. | 4.2, #25 |
| 8 | Interactive UI boundaries meet WCAG 1.4.11; decorative separators may be subtler. | 2.1, all frontend issues |
