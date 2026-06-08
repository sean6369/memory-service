import { useState, useEffect, useRef } from "react";
import { apiPost } from "../api/client";
import { v4 as uuidv4 } from "uuid";

interface ResolvedQuery {
  query_type: string;
  resolved_query: string;
  notes: string;
}

interface RetrievedItem {
  content: string;
  score: number;
  type: string;
  source_id: string;
  collection: string;
  authored_by?: string;
  source?: string;
  confidence?: number;
  status?: string;
}

interface QueryResult {
  original_query: string;
  resolved_query: ResolvedQuery;
  items: RetrievedItem[];
  permitted_collections: string[];
}

interface TurnEntry {
  participant: string;
  content: string;
  retrieval?: RetrievalDetailData;
  retrievedItems?: RetrievedItemData[];
}

interface RetrievalDetailData {
  resolved_query: string;
  query_type: string;
  reasoning_notes: string;
  permitted_collections: string[];
}

interface RetrievedItemData {
  content: string;
  type: string;
  score: number;
  collection?: string;
  source_id?: string;
  authored_by?: string;
  source?: string;
  confidence?: number;
  status?: string;
}

interface ChatResult {
  session_id: string;
  assistant_message: string;
  retrieved_items: RetrievedItemData[];
  retrieval: RetrievalDetailData | null;
}

interface EndSessionResult {
  session_id: string;
  conversation_id: string;
  turns_persisted: number;
  event_published: boolean;
}

interface PipelineStep {
  step: string;
  detail: string;
  data: Record<string, unknown>;
  done: boolean;
}

const STEP_LABELS: Record<string, string> = {
  context: "Context Assembly",
  s1: "S1: Signal Detection",
  gate1: "Gate 1",
  s2: "S2: Knowledge Extraction",
  s3: "S3: Personal vs Company",
  s4_pre: "S4-pre: Vector Pre-check",
  gate2: "Gate 2",
  s4: "S4: Conflict Judgment",
  s5: "S5: Confidence Finalization",
  routing: "Curator Routing",
  complete: "Complete",
  error: "Error",
  timeout: "Timeout",
};

const STEP_COLORS: Record<string, string> = {
  context: "#1a3a5c",
  s1: "#2d1a4e",
  gate1: "#1a3a3a",
  s2: "#2d1a4e",
  s3: "#2d1a4e",
  s4_pre: "#1a3a3a",
  gate2: "#1a3a3a",
  s4: "#2d1a4e",
  s5: "#2d1a4e",
  routing: "#1a3a5c",
  complete: "#0d2818",
  error: "#3a1a1a",
  timeout: "#3a3a1a",
};

const USERS: { id: string; name: string; role: string }[] = [
  { id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", name: "Alice", role: "Backend Engineer" },
  { id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", name: "Bob", role: "Frontend Engineer" },
  { id: "cccccccc-cccc-cccc-cccc-cccccccccccc", name: "Charlie", role: "Engineering Manager" },
];

export default function DemoConsole() {
  // User
  const [userId, setUserId] = useState(USERS[0].id);
  // Query
  const [queryText, setQueryText] = useState("");
  const [queryResult, setQueryResult] = useState<QueryResult | null>(null);
  const [queryLoading, setQueryLoading] = useState(false);

  // Conversation
  const [sessionId] = useState(() => uuidv4());
  const [turns, setTurns] = useState<TurnEntry[]>([]);
  const [turnInput, setTurnInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [sessionResult, setSessionResult] = useState<EndSessionResult | null>(null);
  const [sessionEnded, setSessionEnded] = useState(false);

  // Retrieval detail expansion
  const [expandedTurns, setExpandedTurns] = useState<Set<number>>(new Set());

  // Pipeline streaming
  const [pipelineSteps, setPipelineSteps] = useState<PipelineStep[]>([]);
  const [pipelineDone, setPipelineDone] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  // Connect to SSE when session result arrives
  useEffect(() => {
    if (!sessionResult) return;

    const conversationId = sessionResult.conversation_id;
    const es = new EventSource(`http://localhost:8000/distillation/${conversationId}/stream`);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const step: PipelineStep = JSON.parse(event.data);
        setPipelineSteps((prev) => [...prev, step]);
        if (step.done) {
          setPipelineDone(true);
          es.close();
        }
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      setPipelineDone(true);
      es.close();
    };

    return () => {
      es.close();
    };
  }, [sessionResult]);

  const handleQuery = async () => {
    if (!queryText.trim()) return;
    setQueryLoading(true);
    try {
      const result = await apiPost<QueryResult>("/query", {
        user_id: userId,
        query: queryText,
      });
      setQueryResult(result);
    } catch (e) {
      alert(`Query failed: ${e}`);
    }
    setQueryLoading(false);
  };

  const handleChat = async () => {
    if (!turnInput.trim() || chatLoading) return;
    const message = turnInput;
    setTurnInput("");
    setChatLoading(true);

    // Optimistic: show user message immediately
    setTurns((prev) => [...prev, { participant: "user", content: message }]);

    try {
      const result = await apiPost<ChatResult>("/chat", {
        user_id: userId,
        session_id: sessionId,
        message,
      });
      // Append assistant response with retrieval details
      setTurns((prev) => [...prev, {
        participant: "assistant",
        content: result.assistant_message,
        retrieval: result.retrieval ?? undefined,
        retrievedItems: result.retrieved_items,
      }]);
    } catch (e) {
      alert(`Chat failed: ${e}`);
    }
    setChatLoading(false);
  };

  const handleEndSession = async () => {
    try {
      const result = await apiPost<EndSessionResult>(`/session/${sessionId}/end`, {
        user_id: userId,
      });
      setSessionResult(result);
      setSessionEnded(true);
    } catch (e) {
      alert(`End session failed: ${e}`);
    }
  };

  return (
    <div>
      <h2>Demo Console</h2>
      <p style={{ color: "#888", marginBottom: 16 }}>
        End-to-end demo: query, converse, distill, review
      </p>

      {/* User Switcher */}
      <div
        style={{
          background: "#1a1a2e",
          border: "1px solid #333",
          borderRadius: 8,
          padding: 16,
          marginBottom: 16,
        }}
      >
        <h3 style={{ margin: "0 0 8px 0" }}>Active User</h3>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <select
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            style={{
              padding: "6px 8px",
              borderRadius: 4,
              background: "#0d1117",
              color: "#fff",
              border: "1px solid #555",
            }}
          >
            {USERS.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name} ({u.role})
              </option>
            ))}
          </select>
          <span style={{ color: "#aaa", fontSize: 13 }}>ID: {userId.slice(0, 8)}...</span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Query Panel */}
        <div
          style={{
            background: "#1a1a2e",
            border: "1px solid #333",
            borderRadius: 8,
            padding: 16,
          }}
        >
          <h3 style={{ margin: "0 0 12px 0" }}>Query Memory (Flow 1)</h3>
          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <input
              value={queryText}
              onChange={(e) => setQueryText(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleQuery()}
              placeholder="e.g. the usual, dark mode, gRPC..."
              style={{
                flex: 1,
                padding: "8px 10px",
                borderRadius: 4,
                border: "1px solid #555",
                background: "#0d1117",
                color: "#fff",
              }}
            />
            <button onClick={handleQuery} disabled={queryLoading}>
              {queryLoading ? "..." : "Query"}
            </button>
          </div>

          {queryResult && (
            <div>
              {/* Step 1b: Permissions */}
              <div
                style={{
                  padding: "6px 10px",
                  marginBottom: 4,
                  borderRadius: 4,
                  background: "#1a3a3a",
                  border: "1px solid #333",
                  fontSize: 12,
                }}
              >
                <div style={{ color: "#ccc", fontWeight: 600, marginBottom: 2 }}>
                  1b: Permission Check
                </div>
                <div style={{ color: "#aaa" }}>
                  Collections: {queryResult.permitted_collections.length > 0
                    ? queryResult.permitted_collections.join(", ")
                    : "none"}
                </div>
              </div>

              {/* Step 1a: LLM Reasoning */}
              <div
                style={{
                  padding: "6px 10px",
                  marginBottom: 4,
                  borderRadius: 4,
                  background: "#2d1a4e",
                  border: "1px solid #333",
                  fontSize: 12,
                }}
              >
                <div style={{ color: "#ccc", fontWeight: 600, marginBottom: 2 }}>
                  1a: LLM Reasoning
                </div>
                <div style={{ color: "#aaa" }}>
                  Type: <b>{queryResult.resolved_query.query_type}</b> | Resolved: <b>{queryResult.resolved_query.resolved_query}</b>
                </div>
                {queryResult.resolved_query.notes && (
                  <div style={{ color: "#777", marginTop: 2 }}>
                    Notes: {queryResult.resolved_query.notes}
                  </div>
                )}
              </div>

              {/* Step 1c: Vector Search + Provenance */}
              <div
                style={{
                  padding: "6px 10px",
                  marginBottom: 4,
                  borderRadius: 4,
                  background: "#1a3a5c",
                  border: "1px solid #333",
                  fontSize: 12,
                }}
              >
                <div style={{ color: "#ccc", fontWeight: 600, marginBottom: 4 }}>
                  1c: Vector Search + Provenance ({queryResult.items.length} results)
                </div>
                <div style={{ maxHeight: 300, overflowY: "auto" }}>
                  {queryResult.items.length === 0 && (
                    <div style={{ color: "#555" }}>No items found</div>
                  )}
                  {queryResult.items.map((item, i) => (
                    <div
                      key={i}
                      style={{
                        padding: "6px 8px",
                        marginBottom: 3,
                        borderRadius: 3,
                        background: "#0d1117",
                        fontSize: 12,
                      }}
                    >
                      <div style={{ color: "#ccc" }}>{item.content}</div>
                      <div style={{ color: "#666", fontSize: 10, marginTop: 2 }}>
                        {item.type}
                        {item.collection ? ` | ${item.collection}` : ""}
                        {" "}| score: {item.score.toFixed(3)}
                        {item.confidence != null ? ` | confidence: ${item.confidence}` : ""}
                        {item.status ? ` | ${item.status}` : ""}
                        {item.authored_by ? ` | by: ${item.authored_by}` : ""}
                        {item.source ? ` | src: ${item.source}` : ""}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Conversation Panel */}
        <div
          style={{
            background: "#1a1a2e",
            border: "1px solid #333",
            borderRadius: 8,
            padding: 16,
          }}
        >
          <h3 style={{ margin: "0 0 12px 0" }}>Conversation (Flow 2 + 3)</h3>
          <div style={{ fontSize: 12, color: "#666", marginBottom: 8 }}>
            Session: {sessionId.slice(0, 8)}...
          </div>

          <div
            style={{
              maxHeight: 250,
              overflowY: "auto",
              marginBottom: 12,
              border: "1px solid #333",
              borderRadius: 4,
              padding: 8,
              background: "#0d1117",
            }}
          >
            {turns.length === 0 && !chatLoading && (
              <div style={{ color: "#555", fontSize: 13 }}>No turns yet...</div>
            )}
            {turns.map((t, i) => (
              <div key={i} style={{ marginBottom: 6 }}>
                <div
                  style={{
                    padding: "4px 8px",
                    borderRadius: 4,
                    background: t.participant === "user" ? "#1a3a5c" : "#2d1a4e",
                    fontSize: 13,
                  }}
                >
                  <b>{t.participant}:</b> {t.content}
                  {t.participant === "assistant" && t.retrieval && (
                    <span
                      onClick={() => {
                        setExpandedTurns((prev) => {
                          const next = new Set(prev);
                          if (next.has(i)) next.delete(i);
                          else next.add(i);
                          return next;
                        });
                      }}
                      style={{
                        marginLeft: 8,
                        fontSize: 10,
                        color: "#888",
                        cursor: "pointer",
                        textDecoration: "underline",
                      }}
                    >
                      {expandedTurns.has(i) ? "hide retrieval" : "show retrieval"}
                    </span>
                  )}
                </div>
                {t.participant === "assistant" && expandedTurns.has(i) && t.retrieval && (
                  <div
                    style={{
                      margin: "2px 0 0 12px",
                      padding: 8,
                      borderRadius: 4,
                      background: "#0d1117",
                      border: "1px solid #2a2a3a",
                      fontSize: 11,
                    }}
                  >
                    <div style={{ color: "#888", marginBottom: 4 }}>
                      <b>Retrieval Details</b>
                    </div>
                    <div style={{ color: "#aaa", marginBottom: 2 }}>
                      Query type: <b>{t.retrieval.query_type}</b> | Resolved: <b>{t.retrieval.resolved_query}</b>
                    </div>
                    {t.retrieval.reasoning_notes && (
                      <div style={{ color: "#777", marginBottom: 2 }}>
                        Notes: {t.retrieval.reasoning_notes}
                      </div>
                    )}
                    <div style={{ color: "#777", marginBottom: 4 }}>
                      Collections: {t.retrieval.permitted_collections.join(", ") || "none"}
                    </div>
                    {t.retrievedItems && t.retrievedItems.length > 0 ? (
                      <>
                        <div style={{ color: "#888", marginBottom: 2 }}>
                          <b>Retrieved Items ({t.retrievedItems.length})</b>
                        </div>
                        {t.retrievedItems.map((item, j) => (
                          <div
                            key={j}
                            style={{
                              padding: "3px 6px",
                              marginBottom: 2,
                              borderRadius: 3,
                              background: "#16213e",
                            }}
                          >
                            <div style={{ color: "#ccc" }}>{item.content}</div>
                            <div style={{ color: "#666", fontSize: 10 }}>
                              {item.type}
                              {item.collection ? ` | ${item.collection}` : ""}
                              {" "}| score: {item.score.toFixed(3)}
                              {item.confidence != null ? ` | confidence: ${item.confidence}` : ""}
                              {item.status ? ` | ${item.status}` : ""}
                              {item.authored_by ? ` | by: ${item.authored_by}` : ""}
                            </div>
                          </div>
                        ))}
                      </>
                    ) : (
                      <div style={{ color: "#555" }}>No items retrieved</div>
                    )}
                  </div>
                )}
              </div>
            ))}
            {chatLoading && (
              <div
                style={{
                  marginBottom: 6,
                  padding: "4px 8px",
                  borderRadius: 4,
                  background: "#2d1a4e",
                  fontSize: 13,
                  color: "#888",
                  fontStyle: "italic",
                }}
              >
                assistant: thinking...
              </div>
            )}
          </div>

          {!sessionEnded && (
            <>
              <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                <input
                  value={turnInput}
                  onChange={(e) => setTurnInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleChat()}
                  placeholder="Type a message..."
                  disabled={chatLoading}
                  style={{
                    flex: 1,
                    padding: "8px 10px",
                    borderRadius: 4,
                    border: "1px solid #555",
                    background: "#0d1117",
                    color: "#fff",
                  }}
                />
                <button onClick={handleChat} disabled={chatLoading}>
                  {chatLoading ? "..." : "Send"}
                </button>
              </div>
              <button
                onClick={handleEndSession}
                disabled={turns.length === 0 || chatLoading}
                style={{
                  width: "100%",
                  padding: "8px",
                  background: turns.length > 0 && !chatLoading ? "#d4a017" : "#333",
                  color: "#fff",
                  border: "none",
                  borderRadius: 4,
                  cursor: turns.length > 0 && !chatLoading ? "pointer" : "not-allowed",
                  fontWeight: 600,
                }}
              >
                End Session (triggers distillation)
              </button>
            </>
          )}

          {sessionResult && (
            <div
              style={{
                marginTop: 12,
                padding: 12,
                background: "#0d2818",
                border: "1px solid #2d6a4f",
                borderRadius: 6,
                fontSize: 13,
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 4 }}>Session Ended</div>
              <div>Conversation ID: {sessionResult.conversation_id.slice(0, 8)}...</div>
              <div>Turns persisted: {sessionResult.turns_persisted}</div>
              <div>Event published: {sessionResult.event_published ? "Yes" : "No"}</div>
            </div>
          )}
        </div>
      </div>

      {/* Pipeline Progress Panel — appears after session ends */}
      {sessionResult && (
        <div
          style={{
            marginTop: 16,
            background: "#1a1a2e",
            border: "1px solid #333",
            borderRadius: 8,
            padding: 16,
          }}
        >
          <h3 style={{ margin: "0 0 12px 0" }}>
            Distillation Pipeline (Live)
            {!pipelineDone && (
              <span
                style={{
                  marginLeft: 8,
                  fontSize: 12,
                  color: "#d4a017",
                  fontWeight: 400,
                }}
              >
                running...
              </span>
            )}
            {pipelineDone && (
              <span
                style={{
                  marginLeft: 8,
                  fontSize: 12,
                  color: "#2d6a4f",
                  fontWeight: 400,
                }}
              >
                done
              </span>
            )}
          </h3>

          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {pipelineSteps.length === 0 && !pipelineDone && (
              <div style={{ color: "#555", fontSize: 13, fontStyle: "italic" }}>
                Waiting for pipeline to start...
              </div>
            )}
            {pipelineSteps.map((step, i) => (
              <div
                key={i}
                style={{
                  padding: "8px 12px",
                  borderRadius: 4,
                  background: STEP_COLORS[step.step] || "#1a1a2e",
                  border: step.done
                    ? step.step === "error"
                      ? "1px solid #6a2d2d"
                      : "1px solid #2d6a4f"
                    : "1px solid #333",
                  fontSize: 13,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontWeight: 600, color: "#ccc" }}>
                    {STEP_LABELS[step.step] || step.step}
                  </span>
                  {step.step === "complete" && (
                    <span style={{ color: "#2d6a4f", fontSize: 11 }}>DONE</span>
                  )}
                  {step.step === "error" && (
                    <span style={{ color: "#c44" }}>ERROR</span>
                  )}
                </div>
                <div style={{ color: "#aaa", fontSize: 12, marginTop: 2 }}>
                  {step.detail}
                </div>
                {/* Show S1 debug data (conversation + context previews) */}
                {step.step === "s1" && step.data && (step.data as Record<string, unknown>).debug && (
                  <div style={{ marginTop: 6, fontSize: 11, color: "#888" }}>
                    <div style={{ marginBottom: 2 }}>
                      <b>Prompt version:</b>{" "}
                      {String((step.data as Record<string, Record<string, unknown>>).debug.prompt_version)}
                    </div>
                    <div style={{ marginBottom: 4 }}>
                      <b>Conversation text</b>{" "}
                      ({String((step.data as Record<string, Record<string, unknown>>).debug.conversation_text_length)} chars):
                    </div>
                    <pre style={{
                      background: "#0d1117",
                      padding: 6,
                      borderRadius: 3,
                      fontSize: 10,
                      color: "#aaa",
                      whiteSpace: "pre-wrap",
                      maxHeight: 120,
                      overflowY: "auto",
                      margin: "0 0 4px 0",
                    }}>
                      {String((step.data as Record<string, Record<string, unknown>>).debug.conversation_text_preview)}
                    </pre>
                    <div style={{ marginBottom: 4 }}>
                      <b>Context</b>{" "}
                      ({String((step.data as Record<string, Record<string, unknown>>).debug.enriched_context_length)} chars):
                    </div>
                    <pre style={{
                      background: "#0d1117",
                      padding: 6,
                      borderRadius: 3,
                      fontSize: 10,
                      color: "#aaa",
                      whiteSpace: "pre-wrap",
                      maxHeight: 120,
                      overflowY: "auto",
                      margin: 0,
                    }}>
                      {String((step.data as Record<string, Record<string, unknown>>).debug.enriched_context_preview)}
                    </pre>
                  </div>
                )}
                {/* Show S1 signals inline */}
                {step.step === "s1" && step.data && Array.isArray((step.data as Record<string, unknown>).signals) && (step.data as Record<string, unknown[]>).signals.length > 0 && (
                  <div style={{ marginTop: 6 }}>
                    {((step.data as Record<string, unknown[]>).signals as Array<Record<string, unknown>>).map((s, j) => (
                      <div
                        key={j}
                        style={{
                          padding: "3px 8px",
                          marginTop: 2,
                          borderRadius: 3,
                          background: "#0d1117",
                          fontSize: 11,
                        }}
                      >
                        <span style={{ color: "#d4a017" }}>[{String(s.category)}]</span>
                        {" "}<span style={{ color: "#ccc" }}>{String(s.content)}</span>
                        <span style={{ color: "#666", marginLeft: 6 }}>
                          ({String(s.confidence_band)})
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {/* Show scores summary on complete */}
                {step.step === "complete" && step.data && Array.isArray(step.data.scores) && (
                  <div style={{ marginTop: 6 }}>
                    {(step.data.scores as Array<Record<string, unknown>>).map((s, j) => {
                      const conf = Number(s.final_confidence);
                      const status = conf >= 4 ? "active" : conf >= 2 ? "candidate" : "dropped";
                      return (
                        <div
                          key={j}
                          style={{
                            padding: "4px 8px",
                            marginTop: 4,
                            borderRadius: 3,
                            background: "#0d1117",
                            fontSize: 12,
                          }}
                        >
                          <span style={{ color: "#d4a017" }}>
                            [{String(s.tier)}]
                          </span>
                          {" "}{String(s.content)}
                          <span style={{ color: "#666", marginLeft: 8 }}>
                            confidence: {conf} | status: {status}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
                {/* Show S5 scores inline */}
                {step.step === "s5" && step.data && Array.isArray(step.data.scores) && (
                  <div style={{ marginTop: 6 }}>
                    {(step.data.scores as Array<Record<string, unknown>>).map((s, j) => (
                      <div
                        key={j}
                        style={{
                          padding: "4px 8px",
                          marginTop: 4,
                          borderRadius: 3,
                          background: "#0d1117",
                          fontSize: 12,
                        }}
                      >
                        <span style={{ color: "#d4a017" }}>
                          [{String(s.tier)}]
                        </span>
                        {" "}{String(s.content)}
                        <span style={{ color: "#666", marginLeft: 8 }}>
                          confidence: {String(s.final_confidence)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {/* Show S3 classifications inline */}
                {step.step === "s3" && step.data && Array.isArray(step.data.classifications) && (
                  <div style={{ marginTop: 6 }}>
                    {(step.data.classifications as Array<Record<string, unknown>>).map((c, j) => (
                      <div
                        key={j}
                        style={{
                          padding: "2px 8px",
                          marginTop: 2,
                          fontSize: 11,
                          color: "#aaa",
                        }}
                      >
                        {String(c.content).slice(0, 60)}... → <b>{String(c.tier)}</b>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
