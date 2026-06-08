"""
S4: Conflict Judgment — versioned prompt template.

Maps to Diagram 3, Step 4:
  Input: new item + similar existing items
  Tool: Qdrant query for more context (additional context items)
  Output: "conflict" | "complement" | "duplicate"

Only called when Gate 2 (vector similarity pre-check) finds similar items.
S4 also receives additional context from its own Qdrant tool query (separate from S4-pre).
"""

VERSION = "1.0"

SYSTEM_PROMPT = """\
You are a conflict judgment engine for an AI memory system. You are given a \
NEW candidate item and a list of EXISTING similar items found via vector search.

You also receive ADDITIONAL CONTEXT from a broader vector search — these are \
related but less similar items that may provide useful background for your judgment.

For each pair (new vs existing), determine the relationship:

- "duplicate": The new item says essentially the same thing as an existing item. \
  Do NOT add it — it would be redundant.
- "complement": The new item adds new information that complements or extends \
  an existing item. Both should exist.
- "conflict": The new item contradicts an existing item. The new item may \
  supersede the old one (information may have changed).

Consider the additional context items when making your judgment — they may reveal \
patterns or relationships that affect whether the new item is truly a conflict, \
complement, or duplicate.

Provide an explanation for each judgment. If the judgment is "conflict" or \
"duplicate", include the affected_item_id of the existing item.\
"""


def build_messages(
    candidate_json: str,
    similar_items_json: str,
    additional_context_json: str = "[]",
) -> list[dict]:
    """Build the messages for S4 Conflict Judgment."""
    content = (
        f"NEW candidate item:\n{candidate_json}\n\n"
        f"EXISTING similar items (from S4-pre vector pre-check):\n{similar_items_json}"
    )

    # Include additional context from S4's own Qdrant tool query
    if additional_context_json and additional_context_json != "[]":
        content += (
            f"\n\nADDITIONAL CONTEXT (from S4 Qdrant tool query — broader search):"
            f"\n{additional_context_json}"
        )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]
