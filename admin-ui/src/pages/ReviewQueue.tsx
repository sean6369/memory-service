import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api/client";

interface Candidate {
  id: string;
  content: string;
  type: string;
  proposed_scope: string;
  state: string;
  submitter: string;
  reviewer: string | null;
  decision: string | null;
  source: string;
  confidence: number | null;
  created_at: string | null;
  decided_at: string | null;
}

interface ListResponse {
  candidates: Candidate[];
  total: number;
}

const USERS: Record<string, string> = {
  "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": "Alice",
  "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb": "Bob",
  "cccccccc-cccc-cccc-cccc-cccccccccccc": "Charlie",
};

export default function ReviewQueue() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [filter, setFilter] = useState<string>("pending");
  const [reviewerId, setReviewerId] = useState("cccccccc-cccc-cccc-cccc-cccccccccccc");
  const [rejectReason, setRejectReason] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  const fetchCandidates = async () => {
    setLoading(true);
    try {
      const params = filter ? `?state=${filter}` : "";
      const data = await apiGet<ListResponse>(`/amendments${params}`);
      setCandidates(data.candidates);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchCandidates();
  }, [filter]);

  const handleApprove = async (id: string) => {
    try {
      await apiPost(`/amendments/${id}/approve`, { reviewer_id: reviewerId });
      fetchCandidates();
    } catch (e) {
      alert(`Approve failed: ${e}`);
    }
  };

  const handleReject = async (id: string) => {
    const reason = rejectReason[id] || "Rejected by reviewer";
    try {
      await apiPost(`/amendments/${id}/reject`, {
        reviewer_id: reviewerId,
        decision: reason,
      });
      fetchCandidates();
    } catch (e) {
      alert(`Reject failed: ${e}`);
    }
  };

  return (
    <div>
      <h2>Review Queue</h2>
      <p style={{ color: "#888", marginBottom: 16 }}>
        Company fact candidates awaiting human review (Flow 4)
      </p>

      <div style={{ display: "flex", gap: 16, marginBottom: 16, alignItems: "center" }}>
        <label>
          Filter:{" "}
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="">All</option>
          </select>
        </label>
        <label>
          Reviewer:{" "}
          <select value={reviewerId} onChange={(e) => setReviewerId(e.target.value)}>
            {Object.entries(USERS).map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <button onClick={fetchCandidates} disabled={loading}>
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {candidates.length === 0 && <p style={{ color: "#aaa" }}>No candidates found.</p>}

      {candidates.map((c) => (
        <div
          key={c.id}
          style={{
            border: "1px solid #333",
            borderRadius: 8,
            padding: 16,
            marginBottom: 12,
            background: "#1a1a2e",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
            <strong style={{ fontSize: 16 }}>{c.content}</strong>
            <span
              style={{
                padding: "2px 8px",
                borderRadius: 4,
                fontSize: 12,
                fontWeight: 600,
                background:
                  c.state === "pending"
                    ? "#d4a017"
                    : c.state === "approved"
                    ? "#2d6a4f"
                    : "#c0392b",
                color: "#fff",
              }}
            >
              {c.state.toUpperCase()}
            </span>
          </div>

          <div style={{ display: "flex", gap: 16, fontSize: 13, color: "#aaa", flexWrap: "wrap" }}>
            <span>Type: <b>{c.type}</b></span>
            <span>Scope: <b>{c.proposed_scope}</b></span>
            <span>Source: <b>{c.source}</b></span>
            {c.confidence !== null && <span>Confidence: <b>{c.confidence}/5</b></span>}
            <span>Submitter: <b>{USERS[c.submitter] || c.submitter.slice(0, 8)}</b></span>
            {c.reviewer && <span>Reviewer: <b>{USERS[c.reviewer] || c.reviewer.slice(0, 8)}</b></span>}
            {c.created_at && (
              <span>Created: <b>{new Date(c.created_at).toLocaleString()}</b></span>
            )}
          </div>

          {c.decision && (
            <div style={{ marginTop: 8, fontSize: 13, color: "#e07c7c" }}>
              Decision: {c.decision}
            </div>
          )}

          {c.state === "pending" && (
            <div style={{ marginTop: 12, display: "flex", gap: 8, alignItems: "center" }}>
              <button
                onClick={() => handleApprove(c.id)}
                style={{
                  background: "#2d6a4f",
                  color: "#fff",
                  border: "none",
                  borderRadius: 4,
                  padding: "6px 16px",
                  cursor: "pointer",
                }}
              >
                Approve
              </button>
              <input
                placeholder="Rejection reason..."
                value={rejectReason[c.id] || ""}
                onChange={(e) =>
                  setRejectReason((prev) => ({ ...prev, [c.id]: e.target.value }))
                }
                style={{
                  flex: 1,
                  padding: "6px 8px",
                  borderRadius: 4,
                  border: "1px solid #555",
                  background: "#0d1117",
                  color: "#fff",
                }}
              />
              <button
                onClick={() => handleReject(c.id)}
                style={{
                  background: "#c0392b",
                  color: "#fff",
                  border: "none",
                  borderRadius: 4,
                  padding: "6px 16px",
                  cursor: "pointer",
                }}
              >
                Reject
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
