import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { ApiError } from "../api/client";
import { formatDateTime } from "../articles/format";
import { fill, type Language } from "../i18n/dictionaries";
import { useLanguage } from "../i18n/language";
import {
  MAX_TOPIC_LENGTH,
  WEIGHTS,
  addInterest,
  fetchInterests,
  fetchPreferences,
  isWeight,
  removeInterest,
  resetPreferences,
  setInterestWeight,
  type Interest,
  type LearnedPreference,
  type Weight,
} from "./api";
import { useResource } from "./useResource";

/**
 * "Interests & personalization" (FR-14, FR-17, FR-18, FR-19, FR-24): manual
 * interests and learned preferences, shown in separate sections.
 *
 * Topics are user input or LLM output and are rendered as text only.
 */
export function Interests() {
  const { t } = useLanguage();
  return (
    <section className="interests" aria-labelledby="interests-title">
      <div className="interests__header">
        <h1 id="interests-title">{t.interests.title}</h1>
        <p className="interests__intro">{t.interests.intro}</p>
      </div>
      <div className="interests__sections">
        <ManualInterests />
        <LearnedPreferences />
      </div>
    </section>
  );
}

type Notice = { kind: "added" | "removed"; topic: string };

function ManualInterests() {
  const { t } = useLanguage();
  const { state, reload, update } = useResource(fetchInterests);
  const [notice, setNotice] = useState<Notice | null>(null);
  // After a removal the button is gone; focus moves to the section heading.
  const headingRef = useRef<HTMLHeadingElement>(null);

  function added(interest: Interest) {
    if (state.status === "success") {
      update((list) => [...list, interest]);
    } else {
      reload(); // the list is not shown yet; load it including the new interest
    }
    setNotice({ kind: "added", topic: interest.topic });
  }

  function changed(interest: Interest) {
    update((list) => list.map((item) => (item.id === interest.id ? interest : item)));
  }

  function removed(interest: Interest) {
    update((list) => list.filter((item) => item.id !== interest.id));
    setNotice({ kind: "removed", topic: interest.topic });
    headingRef.current?.focus();
  }

  return (
    <section className="panel" aria-labelledby="manual-title">
      <h2 id="manual-title" className="panel__title" tabIndex={-1} ref={headingRef}>
        {t.interests.manualTitle}
      </h2>
      <p className="panel__intro">{t.interests.manualIntro}</p>
      <AddInterestForm onAdded={added} />
      <p className="panel__notice" role="status">
        {notice &&
          fill(t.interests[notice.kind], { topic: quoted(notice.topic, t.interests.quoted) })}
      </p>
      {state.status === "loading" && (
        <p className="panel__message" role="status">
          {t.interests.loading}
        </p>
      )}
      {state.status === "error" && (
        <div className="panel__message panel__message--error" role="alert">
          <p>{t.interests.error}</p>
          <button type="button" className="button" onClick={reload}>
            {t.interests.retry}
          </button>
        </div>
      )}
      {state.status === "success" &&
        (state.data.length === 0 ? (
          <p className="panel__message">{t.interests.empty}</p>
        ) : (
          <ul className="interest-list">
            {state.data.map((interest) => (
              <InterestItem
                key={interest.id}
                interest={interest}
                onChanged={changed}
                onRemoved={removed}
              />
            ))}
          </ul>
        ))}
    </section>
  );
}

function quoted(topic: string, template: string): string {
  return fill(template, { topic });
}

type AddError = "required" | "duplicate" | "failed";

function AddInterestForm({ onAdded }: { onAdded: (interest: Interest) => void }) {
  const { t } = useLanguage();
  const [topic, setTopic] = useState("");
  const [weight, setWeight] = useState<Weight>("medium");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<{ kind: AddError; detail?: string } | null>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) {
      return;
    }
    // The API collapses whitespace the same way.
    const normalized = topic.split(/\s+/).filter(Boolean).join(" ");
    if (!normalized) {
      setError({ kind: "required" });
      return;
    }
    setPending(true);
    setError(null);
    addInterest(normalized, weight).then(
      (interest) => {
        setPending(false);
        setTopic("");
        setWeight("medium");
        onAdded(interest);
      },
      (failure: unknown) => {
        setPending(false);
        if (failure instanceof ApiError && failure.status === 409) {
          setError({ kind: "duplicate" });
        } else {
          // 422 details come from the API's input validation and are plain text.
          const detail =
            failure instanceof ApiError && failure.status === 422 ? failure.message : undefined;
          setError({ kind: "failed", detail });
        }
      },
    );
  }

  const messages: Record<AddError, string> = {
    required: t.interests.topicRequired,
    duplicate: t.interests.duplicate,
    failed: t.interests.addError,
  };

  return (
    <form className="interest-form" onSubmit={submit} noValidate>
      <div className="interest-form__field interest-form__topic">
        <label htmlFor="interest-topic">{t.interests.topic}</label>
        <input
          id="interest-topic"
          className="control"
          type="text"
          value={topic}
          maxLength={MAX_TOPIC_LENGTH}
          autoComplete="off"
          aria-invalid={error?.kind === "required" || error?.kind === "duplicate" || undefined}
          aria-describedby={error ? "interest-form-error" : undefined}
          onChange={(event) => setTopic(event.target.value)}
        />
      </div>
      <div className="interest-form__field">
        <label htmlFor="interest-weight">{t.interests.weight}</label>
        <WeightSelect id="interest-weight" value={weight} onChange={setWeight} />
      </div>
      <button type="submit" className="button button--primary" aria-disabled={pending || undefined}>
        {pending ? t.interests.adding : t.interests.add}
      </button>
      {error && (
        <div className="interest-form__error" id="interest-form-error" role="alert">
          <p>{messages[error.kind]}</p>
          {error.detail && <p className="panel__detail">{error.detail}</p>}
        </div>
      )}
    </form>
  );
}

interface WeightSelectProps {
  id: string;
  value: Weight;
  busy?: boolean;
  onChange: (weight: Weight) => void;
}

function WeightSelect({ id, value, busy, onChange }: WeightSelectProps) {
  const { t } = useLanguage();
  return (
    <select
      id={id}
      className="control"
      value={value}
      aria-disabled={busy || undefined}
      onChange={(event) => {
        if (isWeight(event.target.value)) {
          onChange(event.target.value);
        }
      }}
    >
      {WEIGHTS.map((option) => (
        <option key={option} value={option}>
          {t.interests.weights[option]}
        </option>
      ))}
    </select>
  );
}

interface InterestItemProps {
  interest: Interest;
  onChanged: (interest: Interest) => void;
  onRemoved: (interest: Interest) => void;
}

/**
 * One manual interest. While a request runs, further changes are ignored;
 * the controls stay focusable (`aria-disabled` instead of `disabled`). If
 * saving fails, the stored weight is shown again with an error.
 */
function InterestItem({ interest, onChanged, onRemoved }: InterestItemProps) {
  const { t } = useLanguage();
  const [pending, setPending] = useState<{ weight: Weight } | "remove" | null>(null);
  const [failed, setFailed] = useState<"weight" | "remove" | null>(null);

  const busy = pending !== null;
  const shown = pending !== null && pending !== "remove" ? pending.weight : interest.weight;
  const label = quoted(interest.topic, t.interests.quoted);

  function changeWeight(next: Weight) {
    if (busy || next === interest.weight) {
      return;
    }
    setPending({ weight: next });
    setFailed(null);
    setInterestWeight(interest.id, next).then(
      (stored) => {
        setPending(null);
        onChanged(stored);
      },
      () => {
        setPending(null);
        setFailed("weight");
      },
    );
  }

  function remove() {
    if (busy) {
      return;
    }
    setPending("remove");
    setFailed(null);
    removeInterest(interest.id).then(
      () => onRemoved(interest),
      () => {
        setPending(null);
        setFailed("remove");
      },
    );
  }

  const selectId = `interest-${interest.id}-weight`;

  return (
    <li className="interest-item">
      <span className="interest-item__topic">{interest.topic}</span>
      <div className="interest-item__controls">
        <label className="visually-hidden" htmlFor={selectId}>
          {fill(t.interests.weightFor, { topic: label })}
        </label>
        <WeightSelect id={selectId} value={shown} busy={busy} onChange={changeWeight} />
        <button type="button" className="button" aria-disabled={busy || undefined} onClick={remove}>
          {t.interests.remove} <span className="visually-hidden">{label}</span>
        </button>
      </div>
      <p className="interest-item__state" role="status">
        {busy ? t.interests.saving : ""}
      </p>
      {failed && (
        <p className="interest-item__error" role="alert">
          {failed === "weight" ? t.interests.updateError : t.interests.removeError}
        </p>
      )}
    </li>
  );
}

type ResetState = "idle" | "confirming" | "pending" | "done" | "failed";

function LearnedPreferences() {
  const { t, lang } = useLanguage();
  const { state, reload } = useResource(fetchPreferences);
  const [reset, setReset] = useState<ResetState>("idle");
  const headingRef = useRef<HTMLHeadingElement>(null);
  const resetRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  // Where focus goes after the confirmation closes.
  const focusNext = useRef<"cancel" | "reset" | "heading" | null>(null);

  useEffect(() => {
    const target = focusNext.current;
    if (target === "cancel") {
      cancelRef.current?.focus();
    } else if (target === "reset") {
      resetRef.current?.focus();
    } else if (target === "heading") {
      headingRef.current?.focus();
    }
    focusNext.current = null;
  }, [reset]);

  function ask() {
    focusNext.current = "cancel";
    setReset("confirming");
  }

  function cancel() {
    if (reset !== "confirming") {
      return;
    }
    focusNext.current = "reset";
    setReset("idle");
  }

  function confirm() {
    if (reset !== "confirming") {
      return;
    }
    setReset("pending");
    resetPreferences().then(
      () => {
        focusNext.current = "heading";
        setReset("done");
        reload();
      },
      () => {
        focusNext.current = "reset";
        setReset("failed");
      },
    );
  }

  function onConfirmKey(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      cancel();
    }
  }

  const confirmOpen = reset === "confirming" || reset === "pending";

  return (
    <section className="panel" aria-labelledby="learned-title">
      <h2 id="learned-title" className="panel__title" tabIndex={-1} ref={headingRef}>
        {t.interests.learnedTitle}
      </h2>
      <p className="panel__intro">{t.interests.learnedIntro}</p>
      <p className="panel__notice" role="status">
        {reset === "done" ? t.interests.resetDone : ""}
      </p>
      {reset === "failed" && (
        <p className="panel__message panel__message--error" role="alert">
          {t.interests.resetError}
        </p>
      )}
      {state.status === "loading" && (
        <p className="panel__message" role="status">
          {t.interests.learnedLoading}
        </p>
      )}
      {state.status === "error" && (
        <div className="panel__message panel__message--error" role="alert">
          <p>{t.interests.learnedError}</p>
          <button type="button" className="button" onClick={reload}>
            {t.interests.retry}
          </button>
        </div>
      )}
      {state.status === "success" && (
        <>
          {state.data.learned.length === 0 ? (
            <p className="panel__message">{t.interests.learnedEmpty}</p>
          ) : (
            <ul className="learned-list">
              {state.data.learned.map((preference) => (
                <LearnedItem key={preference.topic} preference={preference} lang={lang} />
              ))}
            </ul>
          )}
          {state.data.lastResetAt && (
            <p className="panel__meta">
              {fill(t.interests.lastReset, {
                date: formatDateTime(state.data.lastResetAt, lang) ?? t.article.noDate,
              })}
            </p>
          )}
          {(state.data.learned.length > 0 || confirmOpen) &&
            (confirmOpen ? (
              <div
                className="confirm"
                role="group"
                aria-labelledby="reset-confirm-text"
                onKeyDown={onConfirmKey}
              >
                <p id="reset-confirm-text" className="confirm__text">
                  {t.interests.confirmText}
                </p>
                <div className="confirm__buttons">
                  <button
                    type="button"
                    className="button button--primary"
                    aria-disabled={reset === "pending" || undefined}
                    onClick={confirm}
                  >
                    {reset === "pending" ? t.interests.resetting : t.interests.confirmReset}
                  </button>
                  <button
                    type="button"
                    className="button"
                    ref={cancelRef}
                    aria-disabled={reset === "pending" || undefined}
                    onClick={cancel}
                  >
                    {t.interests.cancel}
                  </button>
                </div>
              </div>
            ) : (
              <button type="button" className="button" ref={resetRef} onClick={ask}>
                {t.interests.reset}
              </button>
            ))}
        </>
      )}
    </section>
  );
}

function LearnedItem({ preference, lang }: { preference: LearnedPreference; lang: Language }) {
  const { t } = useLanguage();
  const score = new Intl.NumberFormat(lang === "de" ? "de-DE" : "en-GB", {
    signDisplay: "exceptZero",
  }).format(preference.score);
  return (
    <li className="learned-item">
      <span className="learned-item__topic">{preference.topic}</span>
      <span className="learned-item__score">{fill(t.interests.score, { score })}</span>
      <span className="learned-item__reason">
        {fill(t.interests.reason, {
          relevant: preference.relevant,
          irrelevant: preference.irrelevant,
          ratings: preference.ratings,
        })}
      </span>
    </li>
  );
}
