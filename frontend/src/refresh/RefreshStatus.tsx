import { formatDateTime } from "../articles/format";
import { useLanguage } from "../i18n/language";
import { useRefresh } from "./RefreshContext";

/**
 * Refresh status in the top bar. Labelled "last completed refresh" (design
 * decision 6): `last_finished_at` does not say whether the refresh succeeded.
 */
export function RefreshStatus() {
  const { t, lang } = useLanguage();
  const { status, failed } = useRefresh();

  if (failed || !status) {
    return <p className="refresh-status">{failed ? t.refresh.unavailable : ""}</p>;
  }
  const finished = formatDateTime(status.lastFinishedAt, lang) ?? t.refresh.never;
  return (
    <p className="refresh-status">
      <span className="refresh-status__label">{t.refresh.lastCompleted}:</span>{" "}
      <span>{finished}</span>
      {status.running && <span className="refresh-status__running"> · {t.refresh.running}</span>}
    </p>
  );
}
