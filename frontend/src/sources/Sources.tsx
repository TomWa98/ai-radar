import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { ApiError } from "../api/client";
import { formatDateTime } from "../articles/format";
import { fill } from "../i18n/dictionaries";
import { useLanguage } from "../i18n/language";
import { useResource } from "../interests/useResource";
import { useRefresh, type StartResult } from "../refresh/RefreshContext";
import {
  MAX_NAME_LENGTH,
  MAX_URL_LENGTH,
  addFeed,
  fetchFeeds,
  removeFeed,
  updateFeed,
  type Feed,
} from "./api";

/**
 * "Sources" (FR-01, FR-03): feed management and the manual refresh.
 *
 * Feed URLs, names, and fetch errors are user input or come from external
 * sources; they are rendered as text only (D8).
 */
export function Sources() {
  const { t } = useLanguage();
  return (
    <section className="sources" aria-labelledby="sources-title">
      <div className="sources__header">
        <h1 id="sources-title">{t.sources.title}</h1>
        <p className="sources__intro">{t.sources.intro}</p>
      </div>
      <div className="sources__sections">
        <RefreshPanel />
        <FeedsPanel />
      </div>
    </section>
  );
}

function RefreshPanel() {
  const { t, lang } = useLanguage();
  const { status, start } = useRefresh();
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<StartResult | null>(null);

  function trigger() {
    if (pending) {
      return;
    }
    setPending(true);
    setResult(null);
    void start().then((outcome) => {
      setPending(false);
      setResult(outcome);
    });
  }

  const messages: Record<StartResult, string> = {
    started: t.sources.refreshStarted,
    conflict: t.sources.refreshConflict,
    failed: t.sources.refreshError,
  };
  const running = status?.running ?? false;

  return (
    <section className="panel" aria-labelledby="refresh-title">
      <h2 id="refresh-title" className="panel__title">
        {t.sources.refreshTitle}
      </h2>
      <p className="panel__intro">{t.sources.refreshIntro}</p>
      <button
        type="button"
        className="button button--primary"
        aria-disabled={pending || undefined}
        onClick={trigger}
      >
        {pending ? t.sources.refreshStarting : t.sources.refreshNow}
      </button>
      <p className="panel__notice" role="status">
        {result && result !== "failed" ? messages[result] : ""}
      </p>
      {result === "failed" && (
        <p className="panel__message panel__message--error" role="alert">
          {messages.failed}
        </p>
      )}
      {status && (
        <div className="panel__meta">
          {running && <p className="sources__running">{t.sources.refreshRunning}</p>}
          <p>
            {fill(t.sources.lastCompleted, {
              date: formatDateTime(status.lastFinishedAt, lang) ?? t.refresh.never,
            })}
          </p>
          {status.lastStartedAt && (
            <p>
              {fill(t.sources.lastStarted, {
                date: formatDateTime(status.lastStartedAt, lang) ?? t.refresh.never,
              })}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

type Notice = { kind: "added" | "removed" | "saved"; name: string };

function FeedsPanel() {
  const { t } = useLanguage();
  const { state, reload, revalidate, update } = useResource(fetchFeeds);
  const { status } = useRefresh();
  const [notice, setNotice] = useState<Notice | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  // Reload in the background when a refresh has finished, so last fetch times
  // and errors are current; open edit forms stay as they are.
  const finishedAt = status?.lastFinishedAt ?? null;
  const seenFinishedAt = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    if (status === null) {
      return;
    }
    if (seenFinishedAt.current !== undefined && seenFinishedAt.current !== finishedAt) {
      revalidate();
    }
    seenFinishedAt.current = finishedAt;
  }, [status, finishedAt, revalidate]);

  function added(feed: Feed) {
    if (state.status === "success") {
      update((list) => [...list, feed]);
    } else {
      reload();
    }
    setNotice({ kind: "added", name: feed.name ?? feed.url });
  }

  function saved(feed: Feed) {
    update((list) => list.map((item) => (item.id === feed.id ? feed : item)));
    setNotice({ kind: "saved", name: feed.name ?? feed.url });
  }

  function removed(feed: Feed) {
    update((list) => list.filter((item) => item.id !== feed.id));
    setNotice({ kind: "removed", name: feed.name ?? feed.url });
    headingRef.current?.focus();
  }

  return (
    <section className="panel" aria-labelledby="feeds-title">
      <h2 id="feeds-title" className="panel__title" tabIndex={-1} ref={headingRef}>
        {t.sources.feedsTitle}
      </h2>
      <AddFeedForm onAdded={added} />
      <p className="panel__notice" role="status">
        {notice &&
          fill(t.sources[notice.kind], { name: fill(t.sources.quoted, { name: notice.name }) })}
      </p>
      {state.status === "loading" && (
        <p className="panel__message" role="status">
          {t.sources.loading}
        </p>
      )}
      {state.status === "error" && (
        <div className="panel__message panel__message--error" role="alert">
          <p>{t.sources.error}</p>
          <button type="button" className="button" onClick={reload}>
            {t.sources.retry}
          </button>
        </div>
      )}
      {state.status === "success" &&
        (state.data.length === 0 ? (
          <p className="panel__message">{t.sources.empty}</p>
        ) : (
          <ul className="feed-list">
            {state.data.map((feed) => (
              <FeedItem key={feed.id} feed={feed} onSaved={saved} onRemoved={removed} />
            ))}
          </ul>
        ))}
    </section>
  );
}

/** The plain-text detail of an API validation error (422), if any. */
function validationDetail(failure: unknown): string | undefined {
  return failure instanceof ApiError && failure.status === 422 ? failure.message : undefined;
}

interface FullTextHintProps {
  id: string;
  shown: boolean;
}

/** Shown while the full-text opt-in is checked (D3: the user owns the terms of use). */
function FullTextHint({ id, shown }: FullTextHintProps) {
  const { t } = useLanguage();
  return shown ? (
    <p id={id} className="feed-form__hint">
      {t.sources.fullTextHint}
    </p>
  ) : null;
}

interface CheckboxProps {
  id: string;
  label: string;
  checked: boolean;
  describedBy?: string;
  onChange: (checked: boolean) => void;
}

function Checkbox({ id, label, checked, describedBy, onChange }: CheckboxProps) {
  return (
    <div className="feed-form__check">
      <input
        id={id}
        type="checkbox"
        className="checkbox"
        checked={checked}
        aria-describedby={describedBy}
        onChange={(event) => onChange(event.target.checked)}
      />
      <label htmlFor={id}>{label}</label>
    </div>
  );
}

type AddError = "required" | "duplicate" | "failed";

function AddFeedForm({ onAdded }: { onAdded: (feed: Feed) => void }) {
  const { t } = useLanguage();
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [fullText, setFullText] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<{ kind: AddError; detail?: string } | null>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) {
      return;
    }
    const trimmed = url.trim();
    if (!trimmed) {
      setError({ kind: "required" });
      return;
    }
    setPending(true);
    setError(null);
    addFeed({ url: trimmed, name: name.trim() || null, enabled, fetchFullText: fullText }).then(
      (feed) => {
        setPending(false);
        setUrl("");
        setName("");
        setEnabled(true);
        setFullText(false);
        onAdded(feed);
      },
      (failure: unknown) => {
        setPending(false);
        if (failure instanceof ApiError && failure.status === 409) {
          setError({ kind: "duplicate" });
        } else {
          setError({ kind: "failed", detail: validationDetail(failure) });
        }
      },
    );
  }

  const messages: Record<AddError, string> = {
    required: t.sources.urlRequired,
    duplicate: t.sources.duplicate,
    failed: t.sources.addError,
  };
  const urlInvalid = error !== null && (error.kind !== "failed" || error.detail !== undefined);

  return (
    <form className="feed-form" onSubmit={submit} noValidate aria-labelledby="add-feed-title">
      <h3 id="add-feed-title" className="feed-form__title">
        {t.sources.addTitle}
      </h3>
      <div className="feed-form__field feed-form__wide">
        <label htmlFor="feed-url">{t.sources.url}</label>
        <input
          id="feed-url"
          className="control"
          type="url"
          inputMode="url"
          value={url}
          maxLength={MAX_URL_LENGTH}
          autoComplete="off"
          placeholder="https://"
          aria-invalid={urlInvalid || undefined}
          aria-describedby={error ? "feed-form-error" : undefined}
          onChange={(event) => setUrl(event.target.value)}
        />
      </div>
      <div className="feed-form__field feed-form__wide">
        <label htmlFor="feed-name">{t.sources.name}</label>
        <input
          id="feed-name"
          className="control"
          type="text"
          value={name}
          maxLength={MAX_NAME_LENGTH}
          autoComplete="off"
          onChange={(event) => setName(event.target.value)}
        />
      </div>
      <div className="feed-form__checks">
        <Checkbox id="feed-enabled" label={t.sources.enabled} checked={enabled} onChange={setEnabled} />
        <Checkbox
          id="feed-full-text"
          label={t.sources.fullText}
          checked={fullText}
          describedBy={fullText ? "feed-full-text-hint" : undefined}
          onChange={setFullText}
        />
        <FullTextHint id="feed-full-text-hint" shown={fullText} />
      </div>
      <button type="submit" className="button button--primary" aria-disabled={pending || undefined}>
        {pending ? t.sources.adding : t.sources.add}
      </button>
      {error && (
        <div className="feed-form__error" id="feed-form-error" role="alert">
          <p>{messages[error.kind]}</p>
          {error.detail && <p className="panel__detail">{error.detail}</p>}
        </div>
      )}
    </form>
  );
}

interface FeedItemProps {
  feed: Feed;
  onSaved: (feed: Feed) => void;
  onRemoved: (feed: Feed) => void;
}

type Mode = "view" | "edit" | "confirm";

function FeedItem({ feed, onSaved, onRemoved }: FeedItemProps) {
  const { t, lang } = useLanguage();
  const [mode, setMode] = useState<Mode>("view");
  const [removing, setRemoving] = useState(false);
  const [removeFailed, setRemoveFailed] = useState<string | null>(null);
  const editRef = useRef<HTMLButtonElement>(null);
  const removeRef = useRef<HTMLButtonElement>(null);
  const cancelRemoveRef = useRef<HTMLButtonElement>(null);
  const focusNext = useRef<"edit" | "remove" | "cancel-remove" | null>(null);

  useEffect(() => {
    const target = focusNext.current;
    if (target === "edit") {
      editRef.current?.focus();
    } else if (target === "remove") {
      removeRef.current?.focus();
    } else if (target === "cancel-remove") {
      cancelRemoveRef.current?.focus();
    }
    focusNext.current = null;
  }, [mode, removing]);

  const display = feed.name ?? feed.url;
  const label = fill(t.sources.quoted, { name: display });
  const fetched = formatDateTime(feed.lastFetchedAt, lang);

  function closeEdit(stored?: Feed) {
    focusNext.current = "edit";
    setMode("view");
    if (stored) {
      onSaved(stored);
    }
  }

  function askRemove() {
    setRemoveFailed(null);
    focusNext.current = "cancel-remove";
    setMode("confirm");
  }

  function cancelRemove() {
    if (removing) {
      return;
    }
    focusNext.current = "remove";
    setMode("view");
  }

  function confirmRemove() {
    if (removing) {
      return;
    }
    setRemoving(true);
    removeFeed(feed.id).then(
      () => onRemoved(feed),
      (failure: unknown) => {
        setRemoving(false);
        if (failure instanceof ApiError && failure.status === 404) {
          onRemoved(feed); // already gone
          return;
        }
        setRemoveFailed(t.sources.removeError);
        focusNext.current = "remove";
        setMode("view");
      },
    );
  }

  function onConfirmKey(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      cancelRemove();
    }
  }

  return (
    <li className="feed-item">
      <div className="feed-item__head">
        <span className="feed-item__name">{display}</span>
        {feed.name && <span className="feed-item__url">{feed.url}</span>}
      </div>
      <ul className="feed-item__tags" aria-label={label}>
        <li className={feed.enabled ? "tag" : "tag tag--muted"}>
          {feed.enabled ? t.sources.statusEnabled : t.sources.statusDisabled}
        </li>
        <li className="tag tag--muted">
          {feed.fetchFullText ? t.sources.statusFullText : t.sources.statusExcerpt}
        </li>
      </ul>
      <p className="feed-item__meta">
        {fetched ? fill(t.sources.lastFetched, { date: fetched }) : t.sources.neverFetched}
      </p>
      {feed.lastError && (
        <p className="feed-item__error">{fill(t.sources.lastError, { error: feed.lastError })}</p>
      )}
      {mode === "edit" ? (
        <EditFeedForm feed={feed} label={label} onDone={closeEdit} />
      ) : mode === "confirm" ? (
        <div className="confirm" role="group" aria-labelledby={`feed-${feed.id}-confirm`} onKeyDown={onConfirmKey}>
          <p id={`feed-${feed.id}-confirm`} className="confirm__text">
            {fill(t.sources.removeConfirm, { name: label })}
          </p>
          <div className="confirm__buttons">
            <button
              type="button"
              className="button button--primary"
              aria-disabled={removing || undefined}
              onClick={confirmRemove}
            >
              {removing ? t.sources.removing : t.sources.confirmRemove}
            </button>
            <button
              type="button"
              className="button"
              ref={cancelRemoveRef}
              aria-disabled={removing || undefined}
              onClick={cancelRemove}
            >
              {t.sources.cancel}
            </button>
          </div>
        </div>
      ) : (
        <div className="feed-item__controls">
          <button
            type="button"
            className="button"
            ref={editRef}
            onClick={() => {
              setRemoveFailed(null);
              setMode("edit");
            }}
          >
            {t.sources.edit} <span className="visually-hidden">{label}</span>
          </button>
          <button type="button" className="button" ref={removeRef} onClick={askRemove}>
            {t.sources.remove} <span className="visually-hidden">{label}</span>
          </button>
        </div>
      )}
      {removeFailed && (
        <p className="feed-item__error" role="alert">
          {removeFailed}
        </p>
      )}
    </li>
  );
}

interface EditFeedFormProps {
  feed: Feed;
  label: string;
  onDone: (stored?: Feed) => void;
}

function EditFeedForm({ feed, label, onDone }: EditFeedFormProps) {
  const { t } = useLanguage();
  const id = useId();
  const nameRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState(feed.name ?? "");
  const [enabled, setEnabled] = useState(feed.enabled);
  const [fullText, setFullText] = useState(feed.fetchFullText);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<{ message: string; detail?: string } | null>(null);

  useEffect(() => {
    nameRef.current?.focus();
  }, []);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) {
      return;
    }
    setPending(true);
    setError(null);
    updateFeed(feed.id, { name: name.trim() || null, enabled, fetchFullText: fullText }).then(
      (stored) => onDone(stored),
      (failure: unknown) => {
        setPending(false);
        if (failure instanceof ApiError && failure.status === 404) {
          setError({ message: t.sources.notFound });
        } else {
          setError({ message: t.sources.saveError, detail: validationDetail(failure) });
        }
      },
    );
  }

  function onKey(event: KeyboardEvent<HTMLFormElement>) {
    if (event.key === "Escape" && !pending) {
      event.preventDefault();
      onDone();
    }
  }

  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;

  return (
    <form
      className="feed-form feed-form--edit"
      onSubmit={submit}
      onKeyDown={onKey}
      noValidate
      aria-label={fill(t.sources.editTitle, { name: label })}
    >
      <div className="feed-form__field feed-form__wide">
        <label htmlFor={`${id}-name`}>{t.sources.name}</label>
        <input
          id={`${id}-name`}
          ref={nameRef}
          className="control"
          type="text"
          value={name}
          maxLength={MAX_NAME_LENGTH}
          autoComplete="off"
          aria-describedby={error ? errorId : undefined}
          onChange={(event) => setName(event.target.value)}
        />
      </div>
      <div className="feed-form__checks">
        <Checkbox id={`${id}-enabled`} label={t.sources.enabled} checked={enabled} onChange={setEnabled} />
        <Checkbox
          id={`${id}-full-text`}
          label={t.sources.fullText}
          checked={fullText}
          describedBy={fullText ? hintId : undefined}
          onChange={setFullText}
        />
        <FullTextHint id={hintId} shown={fullText} />
      </div>
      <div className="feed-form__buttons">
        <button type="submit" className="button button--primary" aria-disabled={pending || undefined}>
          {pending ? t.sources.saving : t.sources.save}
        </button>
        <button
          type="button"
          className="button"
          aria-disabled={pending || undefined}
          onClick={() => {
            if (!pending) {
              onDone();
            }
          }}
        >
          {t.sources.cancel}
        </button>
      </div>
      {error && (
        <div className="feed-form__error" id={errorId} role="alert">
          <p>{error.message}</p>
          {error.detail && <p className="panel__detail">{error.detail}</p>}
        </div>
      )}
    </form>
  );
}
