import { Overview } from "./articles/Overview";
import { LanguageProvider, useLanguage } from "./i18n/language";
import { AppShell } from "./shell/AppShell";
import { useHashRoute } from "./shell/navigation";

export function App() {
  return (
    <LanguageProvider>
      <Shell />
    </LanguageProvider>
  );
}

function Shell() {
  const route = useHashRoute();
  const { t } = useLanguage();

  // Further views follow in their own issues (#27, #28, #29).
  return (
    <AppShell current={route}>
      {route === "overview" ? (
        <Overview />
      ) : (
        <section className="empty-state" aria-labelledby="empty-title">
          <h1 id="empty-title">{t.noViewTitle}</h1>
          <p>{t.noViewText}</p>
        </section>
      )}
    </AppShell>
  );
}
