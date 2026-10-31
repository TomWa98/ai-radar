import type { MouseEvent, ReactNode } from "react";
import { LanguageSwitch } from "../i18n/LanguageSwitch";
import { useLanguage } from "../i18n/language";
import { RefreshStatus } from "../refresh/RefreshStatus";
import { HealthStatus } from "./HealthStatus";
import { NAV_ITEMS, hrefFor, type NavItem, type RouteId } from "./navigation";

interface AppShellProps {
  items?: readonly NavItem[];
  current: RouteId | null;
  children?: ReactNode;
}

// The hash holds the current view, so the skip link moves focus directly
// instead of changing the hash to "#main".
function skipToMain(event: MouseEvent<HTMLAnchorElement>) {
  event.preventDefault();
  document.getElementById("main")?.focus();
}

/** Top bar, sidebar navigation, and main area (docs/frontend-design.md, 3). */
export function AppShell({ items = NAV_ITEMS, current, children }: AppShellProps) {
  const { t } = useLanguage();
  return (
    <div className="shell">
      <a className="skip-link" href="#main" onClick={skipToMain}>
        {t.skipToContent}
      </a>
      <header className="topbar">
        <span className="topbar__product">{t.productName}</span>
        <div className="topbar__status">
          <RefreshStatus />
          <HealthStatus />
          <LanguageSwitch />
        </div>
      </header>
      <nav className="sidebar" aria-label={t.mainNavigation}>
        <ul className="sidebar__list">
          {items.map((item) => (
            <li key={item.id}>
              {item.available ? (
                <a
                  className="sidebar__link"
                  href={hrefFor(item.id)}
                  aria-current={item.id === current ? "page" : undefined}
                >
                  {t.nav[item.labelKey]}
                </a>
              ) : (
                <span
                  className="sidebar__link sidebar__link--disabled"
                  aria-disabled="true"
                >
                  {t.nav[item.labelKey]}
                  <span className="sidebar__note">{t.notAvailableYet}</span>
                </span>
              )}
            </li>
          ))}
        </ul>
      </nav>
      <main className="content" id="main" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
