import { LANGUAGES } from "./dictionaries";
import { useLanguage } from "./language";

/** DE/EN toggle for the top bar. */
export function LanguageSwitch() {
  const { lang, setLanguage, t } = useLanguage();

  return (
    <div className="language-switch" role="group" aria-label={t.language.label}>
      {LANGUAGES.map((option) => (
        <button
          key={option}
          type="button"
          className="language-switch__option"
          lang={option}
          // Starts with the visible code (WCAG 2.5.3 label in name).
          aria-label={`${option.toUpperCase()} – ${t.language[option]}`}
          aria-pressed={option === lang}
          onClick={() => setLanguage(option)}
        >
          {option.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
