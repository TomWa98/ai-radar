import { useEffect, useState } from "react";
import { getHealth } from "../api/client";
import { useLanguage } from "../i18n/language";

type State = "checking" | "reachable" | "unreachable";

/** Truthful backend status from GET /health; no simulated "live" state. */
export function HealthStatus() {
  const { t } = useLanguage();
  const [state, setState] = useState<State>("checking");

  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal)
      .then(() => setState("reachable"))
      .catch(() => {
        if (!controller.signal.aborted) {
          setState("unreachable");
        }
      });
    return () => controller.abort();
  }, []);

  return (
    <p className={`health health--${state}`} role="status">
      {t.backend[state]}
    </p>
  );
}
