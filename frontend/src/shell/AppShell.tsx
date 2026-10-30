import type { MouseEvent, ReactNode } from "react";
import { strings } from "../strings";
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
  return (
    <div className="shell">
      <a className="skip-link" href="#main" onClick={skipToMain}>
        {strings.skipToContent}
      </a>
      <header className="topbar">
        <span className="topbar__product">{strings.productName}</span>
        <HealthStatus />
      </header>
      <nav className="sidebar" aria-label={strings.mainNavigation}>
        <ul className="sidebar__list">
          {items.map((item) => (
            <li key={item.id}>
              {item.available ? (
                <a
                  className="sidebar__link"
                  href={hrefFor(item.id)}
                  aria-current={item.id === current ? "page" : undefined}
                >
                  {item.label}
                </a>
              ) : (
                <span
                  className="sidebar__link sidebar__link--disabled"
                  aria-disabled="true"
                >
                  {item.label}
                  <span className="sidebar__note">{strings.notAvailableYet}</span>
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
