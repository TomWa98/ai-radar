import { Overview } from "./articles/Overview";
import { Interests } from "./interests/Interests";
import { LanguageProvider, useLanguage } from "./i18n/language";
import { RefreshProvider } from "./refresh/RefreshContext";
import { AppShell } from "./shell/AppShell";
import { useHashRoute } from "./shell/navigation";
import { Sources } from "./sources/Sources";

export function App() {
  return (
    <LanguageProvider>
      <RefreshProvider>
        <Shell />
      </RefreshProvider>
    </LanguageProvider>
  );
}

function Shell() {
  const route = useHashRoute();
  const { t } = useLanguage();

  // The News Wall follows in its own issue (#29).
  return (
    <AppShell current={route}>
      {route === "overview" ? (
        <Overview />
      ) : route === "interests" ? (
        <Interests />
      ) : route === "sources" ? (
        <Sources />
      ) : (
        <section className="empty-state" aria-labelledby="empty-title">
          <h1 id="empty-title">{t.noViewTitle}</h1>
          <p>{t.noViewText}</p>
        </section>
      )}
    </AppShell>
  );
}
