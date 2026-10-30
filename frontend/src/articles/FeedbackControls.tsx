import { useState } from "react";
import { useLanguage } from "../i18n/language";
import { clearFeedback, setFeedback, type Rating } from "./api";

interface Props {
  articleId: number;
  /** The feedback stored in the API, as last loaded. */
  feedback: Rating | null;
  /** Id of the article title; describes each button with its article. */
  describedBy?: string;
}

/**
 * Relevance feedback for one article (FR-15, FR-24): mark it as relevant or
 * not relevant, or take the feedback back.
 *
 * A choice is shown immediately; if saving fails, an error appears and the
 * display returns to the stored state. While a request runs, further clicks
 * are ignored; the buttons stay focusable (`aria-disabled` instead of
 * `disabled`) so keyboard focus is not lost.
 */
export function FeedbackControls({ articleId, feedback, describedBy }: Props) {
  const { t } = useLanguage();
  const [saved, setSaved] = useState(feedback);
  const [pending, setPending] = useState<{ rating: Rating | null } | null>(null);
  const [failed, setFailed] = useState(false);

  // A reload of the article list may bring a newer stored state; adopt it
  // unless a request of ours is still running.
  const [loaded, setLoaded] = useState(feedback);
  if (feedback !== loaded) {
    setLoaded(feedback);
    if (!pending) {
      setSaved(feedback);
    }
  }

  const shown = pending ? pending.rating : saved;

  function save(next: Rating | null) {
    if (pending || next === shown) {
      return;
    }
    setPending({ rating: next });
    setFailed(false);
    const request =
      next === null ? clearFeedback(articleId).then(() => null) : setFeedback(articleId, next);
    request.then(
      (stored) => {
        setSaved(stored);
        setPending(null);
      },
      () => {
        setPending(null);
        setFailed(true);
      },
    );
  }

  const busy = pending !== null;

  return (
    <div className="feedback" role="group" aria-label={t.feedback.label}>
      <div className="feedback__buttons">
        <button
          type="button"
          className="button feedback__button"
          aria-describedby={describedBy}
          aria-pressed={shown === "relevant"}
          aria-disabled={busy || undefined}
          onClick={() => save("relevant")}
        >
          {t.feedback.relevant}
        </button>
        <button
          type="button"
          className="button feedback__button"
          aria-describedby={describedBy}
          aria-pressed={shown === "irrelevant"}
          aria-disabled={busy || undefined}
          onClick={() => save("irrelevant")}
        >
          {t.feedback.irrelevant}
        </button>
        <button
          type="button"
          className="button feedback__button"
          aria-describedby={describedBy}
          aria-disabled={busy || shown === null || undefined}
          onClick={() => save(null)}
        >
          {t.feedback.clear}
        </button>
      </div>
      <p className="feedback__state" role="status">
        {busy ? t.feedback.saving : t.feedback.current[shown ?? "none"]}
      </p>
      {failed && (
        <p className="feedback__error" role="alert">
          {t.feedback.error}
        </p>
      )}
    </div>
  );
}
