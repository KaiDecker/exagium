import type { ReactNode } from "react";

function Mark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <i />
      <i />
      <b />
    </span>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const path = window.location.pathname;
  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/experiments">
          <Mark />
          <span>
            <strong>EXAGIUM</strong>
            <small>AGENT EVALUATION LAB</small>
          </span>
        </a>
        <nav aria-label="Primary navigation">
          <a className={path.startsWith("/experiments") ? "active" : ""} href="/experiments">
            Experiments
          </a>
          <a className={path.startsWith("/compare") ? "active" : ""} href="/compare">
            Compare
          </a>
        </nav>
        <div className="local-indicator">
          <span /> Local workspace
        </div>
      </header>
      <main>{children}</main>
      <footer>
        <span>BYOA · Bring your own agent</span>
        <span>Run it. Trace it. Evaluate it. Compare it.</span>
      </footer>
    </div>
  );
}
