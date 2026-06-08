"""
S3: Personal vs Company — versioned prompt template.

Maps to Diagram 3, Step 3:
  Input: candidate item
  Output: tier = "user" OR "company"
"""

VERSION = "1.0"

SYSTEM_PROMPT = """\
You are a tier classification engine. For each candidate knowledge item, \
determine whether it is:

- "user": Personal to this specific user. Examples: preferences, individual \
  workflow habits, personal goals, personal relationships.
- "company": A shared fact that applies to the team or entire company. \
  Examples: company policies, team processes, shared tools, organizational facts.

Rules:
- If something is about an individual's preference or habit → "user"
- If something is a policy, process, or fact that affects multiple people → "company"
- When in doubt, classify as "user" (safer — personal memory has lower trust cost)

Provide your reasoning for each classification.\
"""


def build_messages(candidates_json: str) -> list[dict]:
    """Build the messages for S3 Personal vs Company."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Candidate items to classify:\n{candidates_json}",
        },
    ]
