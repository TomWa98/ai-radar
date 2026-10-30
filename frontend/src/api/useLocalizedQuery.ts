import { useEffect, useState } from "react";
import type { Language } from "../i18n/dictionaries";
import { useLanguage } from "../i18n/language";

export type QueryState<T> =
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "error"; error: unknown };

/**
 * Load language-dependent data and reload it when the display language
 * changes. A language switch only repeats this read request with the new
 * `lang`; analyses already exist in both languages, so no new LLM call is
 * made. Callers must keep `load` stable (e.g. module-level or useCallback).
 */
export function useLocalizedQuery<T>(
  load: (lang: Language, signal: AbortSignal) => Promise<T>,
): QueryState<T> {
  const { lang } = useLanguage();
  const [state, setState] = useState<QueryState<T>>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    load(lang, controller.signal).then(
      (data) => setState({ status: "success", data }),
      (error: unknown) => {
        if (!controller.signal.aborted) {
          setState({ status: "error", error });
        }
      },
    );
    return () => controller.abort();
  }, [lang, load]);

  return state;
}
