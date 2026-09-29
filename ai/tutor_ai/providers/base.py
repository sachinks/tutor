"""The one interface every model provider implements (design §4, D27).

The rest of the service depends only on this module, never on a concrete provider, so switching from Ollama or the
mock to a hosted provider changes configuration, not code.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant"]
EmbeddingKind = Literal["document", "query"]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


class ProviderError(Exception):
    """A model call failed. `code` maps to the error the service returns ("provider_unavailable", ...)."""

    code = "provider_error"

    def __init__(self, message: str, *, provider: str) -> None:
        super().__init__(message)
        self.provider = provider


class ProviderUnavailable(ProviderError):
    """The provider can't be reached (Ollama not running, network down)."""

    code = "provider_unavailable"


class ProviderTimeout(ProviderError):
    code = "provider_timeout"


@runtime_checkable
class ModelProvider(Protocol):
    name: str
    chat_model: str
    embedding_model: str
    dimensions: int

    def chat(self, messages: list[Message], *, max_tokens: int, temperature: float) -> AsyncIterator[str]:
        """Stream the reply as text fragments, in order."""
        ...

    async def embed(self, texts: list[str], *, kind: EmbeddingKind) -> list[list[float]]:
        """One unit-length vector of `dimensions` floats per text, in the same order."""
        ...

    async def health(self) -> bool:
        """True if the provider is reachable and has the configured models."""
        ...

    async def aclose(self) -> None: ...
