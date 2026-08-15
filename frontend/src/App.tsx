import { ComparePage } from "./pages/ComparePage";
import { ExperimentsPage } from "./pages/ExperimentsPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { Shell } from "./Shell";

export function App() {
  const path = window.location.pathname;
  let page = <ExperimentsPage />;
  if (path.startsWith("/runs/")) page = <RunDetailPage runId={path.split("/")[2] ?? ""} />;
  if (path.startsWith("/compare")) page = <ComparePage />;

  return <Shell>{page}</Shell>;
}
