import { useState } from "react";
import DemoConsole from "./pages/DemoConsole";
import ReviewQueue from "./pages/ReviewQueue";
import Governance from "./pages/Governance";

type Page = "console" | "review" | "governance";

function App() {
  const [page, setPage] = useState<Page>("console");

  return (
    <div style={{ minHeight: "100vh", background: "#0d1117", color: "#e6edf3" }}>
      {/* Nav */}
      <nav
        style={{
          display: "flex",
          alignItems: "center",
          gap: 16,
          padding: "12px 24px",
          background: "#161b22",
          borderBottom: "1px solid #30363d",
        }}
      >
        <span style={{ fontWeight: 700, fontSize: 18, marginRight: 24 }}>
          Memory Service
        </span>
        {(
          [
            ["console", "Demo Console"],
            ["review", "Review Queue"],
            ["governance", "Governance"],
          ] as [Page, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setPage(key)}
            style={{
              padding: "6px 14px",
              borderRadius: 6,
              border: "none",
              background: page === key ? "#238636" : "transparent",
              color: page === key ? "#fff" : "#8b949e",
              cursor: "pointer",
              fontWeight: page === key ? 600 : 400,
              fontSize: 14,
            }}
          >
            {label}
          </button>
        ))}
      </nav>

      {/* Content */}
      <main style={{ maxWidth: 1200, margin: "0 auto", padding: 24 }}>
        {page === "console" && <DemoConsole />}
        {page === "review" && <ReviewQueue />}
        {page === "governance" && <Governance />}
      </main>
    </div>
  );
}

export default App;
