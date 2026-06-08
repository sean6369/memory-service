"""
Chat System Prompt — versioned prompt template for the /chat endpoint.

Builds LLM messages that incorporate retrieved memories as context,
enabling the assistant to respond naturally using what it "remembers"
about the user.
"""

VERSION = "1.0"

SYSTEM_PROMPT = """\
You are a helpful AI assistant with access to a memory system. You have been \
provided with relevant memories about the user you are talking to. Use these \
memories naturally in your responses — reference them when relevant, but do NOT \
announce that you are "reading from memory" or similar meta-commentary.

If a memory is relevant, weave it into your response as if you simply know it. \
If no memories are relevant to the current message, respond normally without \
mentioning the memory system.

Be concise, helpful, and conversational.\
"""


def build_messages(
    user_message: str,
    retrieved_items: list[dict],
    conversation_history: list[dict],
) -> list[dict[str, str]]:
    """
    Build the message list for llm_gateway.chat().

    Args:
        user_message: The current user message.
        retrieved_items: Retrieved memory items (each has 'content', 'type', 'score', etc.)
        conversation_history: Prior turns from Redis [{"participant": ..., "content": ...}, ...]

    Returns:
        List of {"role": ..., "content": ...} dicts ready for the LLM.
    """
    # Build system message with memory context
    system_content = SYSTEM_PROMPT

    if retrieved_items:
        memory_block = "\n\nRelevant memories about this user:\n"
        for item in retrieved_items:
            memory_block += f"- {item['content']}\n"
        system_content += memory_block

    messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]

    # Append conversation history (excluding the current user message, which was just appended to Redis)
    for turn in conversation_history[:-1]:  # skip the last turn (current user message)
        role = "user" if turn.get("participant") == "user" else "assistant"
        messages.append({"role": role, "content": turn["content"]})

    # Append current user message
    messages.append({"role": "user", "content": user_message})

    return messages
