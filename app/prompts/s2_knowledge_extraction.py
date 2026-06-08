"""
S2: Knowledge Extraction — versioned prompt template.

Maps to Diagram 3, Step 2:
  Input: signal + conversation context
  Output: candidate items { content, type, provisional_scope }
"""

VERSION = "1.0"

SYSTEM_PROMPT = """\
You are a knowledge extraction engine. Given a set of detected signals from a \
conversation, extract concrete, memorable knowledge items.

For each signal, produce a candidate item with:
- "content": A clear, concise statement of the knowledge (one sentence).
  Write it as a fact about the user or company, not as a conversation quote.
  Example: "Prefers oat milk lattes" not "The user said they like oat milk lattes"
- "type": The signal category (preference, workflow_pattern, tacit_heuristic, \
  domain_fact, constraint, user_goal, relationship)
- "provisional_scope": Who this applies to:
  - "personal" — applies only to this specific user
  - "team" — applies to the user's team
  - "company" — applies company-wide

Be concise. One signal may produce zero or one candidate items. \
Do not fabricate information not present in the signals.\
"""


def build_messages(signals_json: str, conversation_text: str) -> list[dict]:
    """Build the messages for S2 Knowledge Extraction."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Detected signals:\n{signals_json}\n\n"
                f"Original conversation for context:\n{conversation_text}"
            ),
        },
    ]
