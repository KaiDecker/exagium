import type { ReactNode } from "react";

function Mark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <i /><i /><i /><i />
    </span>
  );
}

export function PixelTerminal() {
  return (
    <div className="pixel-terminal" aria-hidden="true">
      <div className="pixel-monitor">
        <div className="pixel-screen">
          <i /><i /><i />
          <b>♥</b>
        </div>
        <span className="pixel-neck" />
        <span className="pixel-base" />
      </div>
      <span className="pixel-cable cable-a" />
      <span className="pixel-cable cable-b" />
      <span className="pixel-cell cell-a" />
      <span className="pixel-cell cell-b" />
    </div>
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
            <small>AGENT 实验室</small>
          </span>
        </a>
        <nav aria-label="主导航">
          <a className={path.startsWith("/experiments") ? "active" : ""} href="/experiments">
            实验
          </a>
          <a className={path.startsWith("/compare") ? "active" : ""} href="/compare">
            对比
          </a>
        </nav>
        <div className="local-indicator">
          <span /> 本地工作区
        </div>
      </header>
      <main>{children}</main>
      <footer>
        <span>BYOA · 使用你自己的 Agent</span>
        <span>运行 · 追踪 · 验证 · 对比</span>
      </footer>
    </div>
  );
}
