import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { DICTIONARIES, isLanguage, type Dictionary, type Language } from "./dictionaries";

/** localStorage key for the chosen display language. */
export const LANGUAGE_STORAGE_KEY = "ai-radar.language";

function storedLanguage(): Language | null {
  try {
    const value = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    return isLanguage(value) ? value : null;
  } catch {
    return null; // storage unavailable (e.g. blocked): use the default
  }
}

/** Saved choice, else the browser language (German if it starts with "de"). */
export function initialLanguage(): Language {
  return storedLanguage() ?? (navigator.language.toLowerCase().startsWith("de") ? "de" : "en");
}

interface LanguageContextValue {
  lang: Language;
  setLanguage: (lang: Language) => void;
  t: Dictionary;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Language>(initialLanguage);

  const setLanguage = useCallback((next: Language) => {
    setLang(next);
    try {
      window.localStorage.setItem(LANGUAGE_STORAGE_KEY, next);
    } catch {
      // Not persisted; the choice still applies for this session.
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const value = useMemo(
    () => ({ lang, setLanguage, t: DICTIONARIES[lang] }),
    [lang, setLanguage],
  );
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const value = useContext(LanguageContext);
  if (!value) {
    throw new Error("useLanguage must be used inside <LanguageProvider>");
  }
  return value;
}
