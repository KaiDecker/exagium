import { Beaker, GitCompareArrows, HardDrive } from "lucide-react";
import type { ReactNode } from "react";

// 品牌标记由两个像素样本和一个测量核心组成，分别对应 A/B 运行与分析。
function Mark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <i className="sample sample-a" />
      <i className="measure-core" />
      <i className="sample sample-b" />
    </span>
  );
}

// 像素感只放在小型实验示意里，避免整页变成复古终端。
export function ExperimentMotif() {
  return (
    <div className="experiment-motif" aria-hidden="true">
      <span className="motif-label">A</span>
      <i className="motif-line line-a" />
      <span className="motif-core"><b /><b /><b /></span>
      <i className="motif-line line-b" />
      <span className="motif-label motif-b">B</span>
    </div>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const path = window.location.pathname;
  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/experiments" aria-label="Exagium 首页">
          <Mark />
          <span>
            <strong>Exagium</strong>
            <small>Agent 实验室</small>
          </span>
        </a>
        <nav aria-label="主导航">
          <a className={path.startsWith("/experiments") || path.startsWith("/runs/") ? "active" : ""} href="/experiments">
            <Beaker size={17} strokeWidth={1.8} />
            <span>实验</span>
          </a>
          <a className={path.startsWith("/compare") ? "active" : ""} href="/compare">
            <GitCompareArrows size={17} strokeWidth={1.8} />
            <span>对比</span>
          </a>
        </nav>
        <div className="local-indicator" title="Exagium 不会把运行数据上传到远端">
          <HardDrive size={15} strokeWidth={1.8} />
          <span>数据只在本机</span>
          <i aria-hidden="true" />
        </div>
      </header>
      <main>{children}</main>
      <footer>
        <span>Exagium · 用证据了解你的 Agent</span>
        <span>本地运行 · 独立验证 · 清楚对比</span>
      </footer>
    </div>
  );
}
