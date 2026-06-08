import { useState } from "react";
import { apiGet } from "../api/client";

interface Bullet {
  id: string;
  user_id: string;
  content: string;
  type: string;
  tier: string;
  confidence: number;
  status: string;
  authored_by: string;
  source: string;
  created_at: string;
}

interface AuditEntry {
  id: string;
  actor: string;
  action: string;
  target_type: string;
  target_id: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  ts: string;
}

interface ProfileResponse {
  user_id: string;
  display_name: string;
  job_function: string;
  department: string;
  bullets: Bullet[];
}

interface AuditResponse {
  entries: AuditEntry[];
  total: number;
}

const USERS: Record<string, string> = {
  "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": "Alice",
  "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb": "Bob",
  "cccccccc-cccc-cccc-cccc-cccccccccccc": "Charlie",
};

export default function Governance() {
  const [selectedUser, setSelectedUser] = useState("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [tab, setTab] = useState<"profile" | "audit">("profile");

  const fetchProfile = async () => {
    try {
      const data = await apiGet<ProfileResponse>(`/governance/users/${selectedUser}/profile`);
      setProfile(data);
    } catch (e) {
      alert(`Failed to load profile: ${e}`);
    }
  };

  const fetchAudit = async () => {
    try {
      const data = await apiGet<AuditResponse>("/governance/audit");
      setAudit(data.entries);
    } catch (e) {
      alert(`Failed to load audit: ${e}`);
    }
  };

  return (
    <div>
      <h2>Governance</h2>
      <p style={{ color: "#888", marginBottom: 16 }}>
        Read-only reporting: user profiles, provenance, audit trail (Flow 6)
      </p>

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button
          onClick={() => setTab("profile")}
          style={{
            padding: "8px 16px",
            background: tab === "profile" ? "#2d6a4f" : "#333",
            color: "#fff",
            border: "none",
            borderRadius: 4,
            cursor: "pointer",
          }}
        >
          User Profile
        </button>
        <button
          onClick={() => setTab("audit")}
          style={{
            padding: "8px 16px",
            background: tab === "audit" ? "#2d6a4f" : "#333",
            color: "#fff",
            border: "none",
            borderRadius: 4,
            cursor: "pointer",
          }}
        >
          Audit Trail
        </button>
      </div>

      {tab === "profile" && (
        <div>
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            <select
              value={selectedUser}
              onChange={(e) => setSelectedUser(e.target.value)}
              style={{ padding: "6px 8px", borderRadius: 4, background: "#0d1117", color: "#fff", border: "1px solid #555" }}
            >
              {Object.entries(USERS).map(([id, name]) => (
                <option key={id} value={id}>{name}</option>
              ))}
            </select>
            <button onClick={fetchProfile}>Load Profile</button>
          </div>

          {profile && (
            <div>
              <div style={{ background: "#1a1a2e", border: "1px solid #333", borderRadius: 8, padding: 16, marginBottom: 16 }}>
                <h3 style={{ margin: "0 0 8px 0" }}>{profile.display_name}</h3>
                <div style={{ color: "#aaa", fontSize: 13 }}>
                  <span>Role: {profile.job_function}</span> &middot;{" "}
                  <span>Department: {profile.department}</span> &middot;{" "}
                  <span>Active bullets: {profile.bullets.length}</span>
                </div>
              </div>

              {profile.bullets.map((b) => (
                <div
                  key={b.id}
                  style={{
                    border: "1px solid #333",
                    borderRadius: 6,
                    padding: 12,
                    marginBottom: 8,
                    background: "#16213e",
                  }}
                >
                  <div style={{ marginBottom: 4 }}>{b.content}</div>
                  <div style={{ display: "flex", gap: 12, fontSize: 12, color: "#888" }}>
                    <span>Type: {b.type}</span>
                    <span>Tier: {b.tier}</span>
                    <span>Confidence: {b.confidence}/5</span>
                    <span>Status: {b.status}</span>
                    <span>Source: {b.source}</span>
                    <span>Authored: {b.authored_by}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "audit" && (
        <div>
          <button onClick={fetchAudit} style={{ marginBottom: 16 }}>
            Load Audit Trail
          </button>

          {audit.map((entry) => (
            <div
              key={entry.id}
              style={{
                border: "1px solid #333",
                borderRadius: 6,
                padding: 12,
                marginBottom: 8,
                background: "#1a1a2e",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                <strong>{entry.action}</strong>
                <span style={{ color: "#888", fontSize: 12 }}>
                  {new Date(entry.ts).toLocaleString()}
                </span>
              </div>
              <div style={{ fontSize: 13, color: "#aaa", marginBottom: 4 }}>
                Actor: {USERS[entry.actor] || entry.actor.slice(0, 8)} &middot; Target:{" "}
                {entry.target_type} {String(entry.target_id).slice(0, 8)}...
              </div>
              <div style={{ display: "flex", gap: 16, fontSize: 12 }}>
                <div>
                  <span style={{ color: "#c0392b" }}>Before:</span>{" "}
                  <code>{JSON.stringify(entry.before)}</code>
                </div>
                <div>
                  <span style={{ color: "#2d6a4f" }}>After:</span>{" "}
                  <code>{JSON.stringify(entry.after)}</code>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
