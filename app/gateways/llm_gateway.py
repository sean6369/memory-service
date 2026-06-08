"""
LLM Gateway — single integration point for all model calls.

Maps to the "LLM Gateway" container in Diagram 1.
Three methods: chat, structured (returns validated Pydantic), embed.
All LLM calls in the codebase go through this gateway.
"""

import json
import logging
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMGateway:
    def __init__(self):
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._chat_model = settings.openai_chat_model
        self._embedding_model = settings.openai_embedding_model

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.3) -> str:
        """Plain chat completion. Returns the assistant message content."""
        response = self._client.chat.completions.create(
            model=self._chat_model,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content

    def structured(
        self,
        messages: list[dict[str, str]],
        schema: type[T],
        temperature: float = 0.1,
    ) -> T:
        """
        Structured output — returns a validated Pydantic model instance.
        Uses OpenAI's JSON mode with a schema instruction, then parses.
        """
        schema_json = schema.model_json_schema()
        system_suffix = (
            f"\n\nYou MUST respond with valid JSON matching this schema:\n"
            f"```json\n{json.dumps(schema_json, indent=2)}\n```\n"
            f"Respond ONLY with the JSON object, no other text."
        )

        # Prepend or append schema instruction to the system message
        augmented = list(messages)
        if augmented and augmented[0]["role"] == "system":
            augmented[0] = {
                "role": "system",
                "content": augmented[0]["content"] + system_suffix,
            }
        else:
            augmented.insert(0, {"role": "system", "content": system_suffix})

        response = self._client.chat.completions.create(
            model=self._chat_model,
            messages=augmented,
            temperature=temperature,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        logger.debug(f"LLMGateway.structured raw response: {raw}")
        return schema.model_validate_json(raw)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns a list of vectors."""
        response = self._client.embeddings.create(
            model=self._embedding_model,
            input=texts,
        )
        return [item.embedding for item in response.data]


# Singleton for the application
llm_gateway = LLMGateway()
