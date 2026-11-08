import { useCallback, useEffect, useRef, useState } from "react";
import { formatDateTime } from "../articles/format";
import { fill } from "../i18n/dictionaries";
import { useLanguage } from "../i18n/language";
import { CARDS_PER_PAGE, ROTATION_INTERVAL_MS, SETTINGS_IDLE_MS, isHighlighted } from "./rules";
import { loadMinRelevance, saveMinRelevance } from "./settings";
import { useWallArticles } from "./useWallArticles";
import { WallCard } from "./WallCard";
import { WallSettings } from "./WallSettings";

/**
 * Full-screen news wall for an always-on display (FR-25 to FR-29, D10). It
 * needs no interaction. Settings open by keyboard (Tab to the invisible
 * trigger, then Enter) or by clicking anywhere on the wall.
 */
export function NewsWall() {
  const { lang, t } = useLanguage();
  const [minRelevance, setMinRelevance] = useState(loadMinRelevance);
  const state = useWallArticles(minRelevance);
  // One clock, so the page and the "new" highlight advance together.
  const [clock, setClock] = useState(() => ({ now: Date.now(), page: 0 }));
  const [settingsOpen, setSettingsOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const triggerIdle = useRef<number | undefined>(undefined);

  useEffect(() => {
    const timer = window.setInterval(
      () => setClock((previous) => ({ now: Date.now(), page: previous.page + 1 })),
      ROTATION_INTERVAL_MS,
    );
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => () => window.clearTimeout(triggerIdle.current), []);

  const closeSettings = useCallback(() => {
    setSettingsOpen(false);
    trigger.current?.focus();
  }, []);
  const hideSettings = useCallback(() => setSettingsOpen(false), []);

  const changeMinRelevance = (value: number) => {
    setMinRelevance(value);
    saveMinRelevance(value);
    setClock((previous) => ({ ...previous, page: 0 }));
  };

  const articles = state.status === "ready" ? state.articles : [];
  const pageCount = Math.max(1, Math.ceil(articles.length / CARDS_PER_PAGE));
  const page = clock.page % pageCount;
  const visible = articles.slice(page * CARDS_PER_PAGE, (page + 1) * CARDS_PER_PAGE);
  const updatedAt =
    state.status === "ready"
      ? formatDateTime(new Date(state.updatedAt).toISOString(), lang)
      : null;

  return (
    <main className="wall">
      <h1 className="visually-hidden">{t.nav.newsWall}</h1>

      <div className="wall__stage" onClick={() => setSettingsOpen((open) => !open)}>
        {state.status === "loading" && <p className="wall__message">{t.wall.loading}</p>}
        {state.status === "error" && (
          <p className="wall__message" role="alert">
            {t.wall.error}
          </p>
        )}
        {state.status === "ready" && articles.length === 0 && (
          <div className="wall__message">
            <h2>{t.wall.emptyTitle}</h2>
            <p>{fill(t.wall.emptyText, { score: minRelevance })}</p>
          </div>
        )}
        {visible.length > 0 && (
          <div className="wall__grid" key={page}>
            {visible.map((article, index) => (
              <WallCard
                key={article.id}
                article={article}
                lead={index === 0}
                highlighted={isHighlighted(article, clock.now)}
              />
            ))}
          </div>
        )}
      </div>

      <footer className="wall__footer">
        <span>{t.productName}</span>
        <span role="status">
          {state.status === "ready" && state.stale
            ? fill(t.wall.stale, { time: updatedAt ?? "" })
            : ""}
        </span>
        {pageCount > 1 && (
          <span>{fill(t.overview.pageOf, { page: page + 1, pages: pageCount })}</span>
        )}
      </footer>

      <button
        ref={trigger}
        type="button"
        className="wall__trigger"
        aria-haspopup="dialog"
        aria-expanded={settingsOpen}
        onClick={() => setSettingsOpen(true)}
        onFocus={() => {
          triggerIdle.current = window.setTimeout(
            () => trigger.current?.blur(),
            SETTINGS_IDLE_MS,
          );
        }}
        onBlur={() => window.clearTimeout(triggerIdle.current)}
      >
        {t.wall.settings}
      </button>

      {settingsOpen && (
        <WallSettings
          minRelevance={minRelevance}
          onChange={changeMinRelevance}
          onClose={closeSettings}
          onIdle={hideSettings}
        />
      )}
    </main>
  );
}
