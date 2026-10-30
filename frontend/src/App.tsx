import { AppShell } from "./shell/AppShell";
import { useHashRoute } from "./shell/navigation";
import { strings } from "./strings";

export function App() {
  const route = useHashRoute();

  // Functional views follow in their own issues (#25, #27, #28, #29).
  return (
    <AppShell current={route}>
      <section className="empty-state" aria-labelledby="empty-title">
        <h1 id="empty-title">{strings.noViewTitle}</h1>
        <p>{strings.noViewText}</p>
      </section>
    </AppShell>
  );
}
