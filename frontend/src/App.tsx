import { Overview } from "./articles/Overview";
import { Interests } from "./interests/Interests";
import { LanguageProvider, useLanguage } from "./i18n/language";
import { RefreshProvider } from "./refresh/RefreshContext";
import { AppShell } from "./shell/AppShell";
import { useHashRoute } from "./shell/navigation";
import { Sources } from "./sources/Sources";
import { NewsWall } from "./wall/NewsWall";

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

  // A separate full-screen mode, not the dashboard without its sidebar.
  if (route === "news-wall") {
    return <NewsWall />;
  }

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
