import { useCallback, useEffect, useId, useRef } from "react";
import { hrefFor } from "../shell/navigation";
import { useLanguage } from "../i18n/language";
import { SETTINGS_IDLE_MS } from "./rules";
import { MIN_RELEVANCE_OPTIONS } from "./settings";

interface Props {
  minRelevance: number;
  onChange: (value: number) => void;
  /** Closed by the user: focus returns to the trigger. */
  onClose: () => void;
  /** Hidden after idling: focus is not moved, so no control reappears. */
  onIdle: () => void;
}

/**
 * Discreet settings overlay (design decision 5). It hides itself after a
 * period without input, so it cannot stay on an unattended display.
 */
export function WallSettings({ minRelevance, onChange, onClose, onIdle }: Props) {
  const { t } = useLanguage();
  const selectId = useId();
  const selectRef = useRef<HTMLSelectElement>(null);
  const idleTimer = useRef<number | undefined>(undefined);

  const restartIdle = useCallback(() => {
    window.clearTimeout(idleTimer.current);
    idleTimer.current = window.setTimeout(onIdle, SETTINGS_IDLE_MS);
  }, [onIdle]);

  useEffect(() => {
    selectRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      } else {
        restartIdle();
      }
    };
    restartIdle();
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.clearTimeout(idleTimer.current);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose, restartIdle]);

  return (
    <div
      className="wall-settings"
      role="dialog"
      aria-label={t.wall.settings}
      onPointerMove={restartIdle}
    >
      <label htmlFor={selectId}>{t.overview.minRelevance}</label>
      <select
        id={selectId}
        ref={selectRef}
        value={minRelevance}
        onChange={(event) => {
          restartIdle();
          onChange(Number(event.target.value));
        }}
      >
        {MIN_RELEVANCE_OPTIONS.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      <div className="wall-settings__actions">
        <a href={hrefFor("overview")}>{t.wall.exit}</a>
        <button type="button" onClick={onClose}>
          {t.wall.close}
        </button>
      </div>
    </div>
  );
}
