"""
S5: Confidence Finalization — versioned prompt template.

Maps to Diagram 3, Step 5:
  Input: signal band + corroboration check
  Output: final confidence 1-5

Status gating (on final confidence):
  5 or 4 → active immediately
  3 or 2 → candidate (needs corroboration)
  1 → drop (unless corroborated)
"""

VERSION = "1.0"

SYSTEM_PROMPT = """\
You are a confidence scoring engine. For each knowledge item, assign a final \
confidence score from 1 to 5 based on:

Scoring criteria:
- 5: Explicitly and clearly stated by the user. No ambiguity.
- 4: Strongly supported by the conversation. High confidence.
- 3: Reasonably implied but could benefit from corroboration.
- 2: Weakly implied or ambiguous. Needs more evidence.
- 1: Very uncertain. May be a misinterpretation.

Factors that increase confidence:
- User explicitly states it
- Repeated across multiple turns
- Consistent with known context
- No conflicting information

Factors that decrease confidence:
- Mentioned in passing or hypothetically
- Contradicts existing knowledge (conflict detected)
- Ambiguous phrasing
- Duplicate of existing knowledge (already captured)

For each item, also note the conflict_status from any prior analysis:
"no_conflict", "complement", "conflict", or "duplicate"\
"""


def build_messages(items_json: str) -> list[dict]:
    """Build the messages for S5 Confidence Finalization."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Items to score:\n{items_json}",
        },
    ]
