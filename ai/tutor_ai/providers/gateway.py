"""LLM Gateway provider for unified routing, resilient failover, and structured observability."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Literal

from ..chunking import count_tokens
from .base import EmbeddingKind, Message, ModelProvider, ProviderError, ProviderUnavailable

logger = logging.getLogger("tutor_ai.providers.gateway")

RecoveryMode = Literal["none", "prestream_failover", "midstream_continuation"]


class LLMGatewayProvider:
    """Intelligent gateway routing requests to primary and fallback model providers.

    Features:
    - Zero downstream contract changes: implements the standard ModelProvider interface.
    - Transient retries: retries pre-stream primary failures with exponential backoff.
    - Automatic pre-stream failover: falls back to secondary provider on rate limits (429),
      timeouts, or connectivity errors before tokens are emitted.
    - Mid-stream continuation recovery: if the primary provider disconnects mid-response,
      resumes seamlessly via the fallback provider using accumulated partial context.
    - Structured logging: records execution latency, chunk metrics, token estimates, retry
      counts, and recovery modes for complete production observability.
    """

    name = "gateway"

    def __init__(
        self,
        *,
        primary: ModelProvider,
        fallback: ModelProvider | None = None,
        max_retries: int = 1,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds

        # Mirror model metadata from primary provider
        self.chat_model = primary.chat_model
        self.embedding_model = primary.embedding_model
        self.dimensions = primary.dimensions

    def _build_continuation_messages(self, original_messages: list[Message], partial_text: str) -> list[Message]:
        """Construct a continuation prompt so the fallback finishes an interrupted answer without repeating."""
        return [
            *original_messages,
            Message(role="assistant", content=partial_text),
            Message(
                role="user",
                content=(
                    "Continue your incomplete reply seamlessly from the exact point where it stopped. "
                    "Do not repeat any words already written above."
                ),
            ),
        ]

    async def chat(
        self,
        messages: list[Message],
        *,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[str]:
        """Stream chat tokens with transient retries, pre-stream failover, and mid-stream recovery."""
        start_time = time.perf_counter()
        first_token_time: float | None = None
        emitted_parts: list[str] = []
        active_provider = self.primary
        retries_attempted = 0
        recovery_mode: RecoveryMode = "none"
        prompt_tokens = sum(count_tokens(m.content) for m in messages)

        logger.info(
            "LLM Gateway routing chat request",
            extra={
                "event": "gateway.chat.start",
                "primary_provider": self.primary.name,
                "primary_model": self.primary.chat_model,
                "has_fallback": self.fallback is not None,
                "fallback_provider": self.fallback.name if self.fallback else None,
                "prompt_tokens": prompt_tokens,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "max_retries": self.max_retries,
            },
        )

        primary_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                async for chunk in self.primary.chat(
                    messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                ):
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                        logger.info(
                            "LLM Gateway received first token from primary",
                            extra={
                                "event": "gateway.chat.first_token",
                                "provider": self.primary.name,
                                "attempt": attempt + 1,
                                "time_to_first_token_ms": round((first_token_time - start_time) * 1000, 1),
                            },
                        )
                    emitted_parts.append(chunk)
                    yield chunk

                # Primary completed cleanly
                primary_exc = None
                break

            except Exception as exc:
                primary_exc = exc

                # If chunks were already emitted mid-stream, do NOT retry primary (would duplicate text)
                if emitted_parts:
                    break

                # Pre-stream failure: retry primary if attempts remain
                if attempt < self.max_retries:
                    retries_attempted += 1
                    delay = self.retry_backoff_seconds * (2**attempt)
                    logger.warning(
                        "LLM Gateway primary attempt failed before emission; retrying",
                        extra={
                            "event": "gateway.chat.retry",
                            "provider": self.primary.name,
                            "attempt": attempt + 1,
                            "max_retries": self.max_retries,
                            "error_type": type(exc).__name__,
                            "backoff_seconds": delay,
                        },
                    )
                    if delay > 0:
                        await asyncio.sleep(delay)
                    continue

                # Retries exhausted before any emission
                break

        if primary_exc is not None:
            if self.fallback is None:
                duration_ms = round((time.perf_counter() - start_time) * 1000, 1)
                logger.error(
                    "LLM Gateway primary stream failed with no fallback available",
                    extra={
                        "event": "gateway.chat.error",
                        "provider": self.primary.name,
                        "error_type": type(primary_exc).__name__,
                        "emitted_chunks": len(emitted_parts),
                        "retries_attempted": retries_attempted,
                        "duration_ms": duration_ms,
                    },
                )
                if isinstance(primary_exc, ProviderError):
                    raise primary_exc
                raise ProviderUnavailable(
                    f"LLM Gateway primary provider {self.primary.name} failed: {primary_exc}",
                    provider=self.primary.name,
                ) from primary_exc

            failover_start = time.perf_counter()
            active_provider = self.fallback

            if emitted_parts:
                # Mid-stream recovery via continuation prompting
                recovery_mode = "midstream_continuation"
                partial_text = "".join(emitted_parts)
                partial_tokens = count_tokens(partial_text)
                remaining_tokens = max(20, max_tokens - partial_tokens)
                fallback_messages = self._build_continuation_messages(messages, partial_text)

                logger.warning(
                    "LLM Gateway primary failed mid-stream; continuing via fallback",
                    extra={
                        "event": "gateway.chat.midstream_continuation",
                        "primary_provider": self.primary.name,
                        "primary_error": type(primary_exc).__name__,
                        "fallback_provider": self.fallback.name,
                        "fallback_model": self.fallback.chat_model,
                        "partial_chunks": len(emitted_parts),
                        "partial_tokens": partial_tokens,
                        "remaining_max_tokens": remaining_tokens,
                        "elapsed_before_failover_ms": round((failover_start - start_time) * 1000, 1),
                    },
                )
            else:
                # Clean pre-stream failover
                recovery_mode = "prestream_failover"
                remaining_tokens = max_tokens
                fallback_messages = messages

                logger.warning(
                    "LLM Gateway primary provider failed; triggering fallback",
                    extra={
                        "event": "gateway.chat.fallback",
                        "primary_provider": self.primary.name,
                        "primary_error": type(primary_exc).__name__,
                        "fallback_provider": self.fallback.name,
                        "fallback_model": self.fallback.chat_model,
                        "retries_attempted": retries_attempted,
                        "elapsed_before_failover_ms": round((failover_start - start_time) * 1000, 1),
                    },
                )

            try:
                async for chunk in self.fallback.chat(
                    fallback_messages,
                    max_tokens=remaining_tokens,
                    temperature=temperature,
                ):
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    emitted_parts.append(chunk)
                    yield chunk
            except Exception as fallback_exc:
                duration_ms = round((time.perf_counter() - start_time) * 1000, 1)
                logger.error(
                    "LLM Gateway fallback provider also failed",
                    extra={
                        "event": "gateway.chat.fallback_error",
                        "fallback_provider": self.fallback.name,
                        "recovery_mode": recovery_mode,
                        "error_type": type(fallback_exc).__name__,
                        "duration_ms": duration_ms,
                    },
                )
                if isinstance(fallback_exc, ProviderError):
                    raise fallback_exc
                raise ProviderUnavailable(
                    f"LLM Gateway fallback {self.fallback.name} failed: {fallback_exc}",
                    provider=self.fallback.name,
                ) from fallback_exc

        total_duration_ms = round((time.perf_counter() - start_time) * 1000, 1)
        completion_tokens = count_tokens("".join(emitted_parts))
        logger.info(
            "LLM Gateway chat completed successfully",
            extra={
                "event": "gateway.chat.complete",
                "active_provider": active_provider.name,
                "model": active_provider.chat_model,
                "used_fallback": active_provider is self.fallback,
                "recovery_mode": recovery_mode,
                "retries_attempted": retries_attempted,
                "total_chunks": len(emitted_parts),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "duration_ms": total_duration_ms,
            },
        )

    async def embed(
        self,
        texts: list[str],
        *,
        kind: EmbeddingKind,
    ) -> list[list[float]]:
        """Route embedding generation to primary provider with latency metrics and fallback."""
        start_time = time.perf_counter()
        input_tokens = sum(count_tokens(t) for t in texts)
        try:
            vectors = await self.primary.embed(texts, kind=kind)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 1)
            logger.info(
                "LLM Gateway embedding completed",
                extra={
                    "event": "gateway.embed.complete",
                    "provider": self.primary.name,
                    "model": self.primary.embedding_model,
                    "text_count": len(texts),
                    "input_tokens": input_tokens,
                    "kind": kind,
                    "duration_ms": duration_ms,
                },
            )
            return vectors
        except Exception as exc:
            if self.fallback is not None:
                logger.warning(
                    "LLM Gateway primary embed failed; attempting fallback",
                    extra={
                        "event": "gateway.embed.fallback",
                        "primary_error": type(exc).__name__,
                        "fallback_provider": self.fallback.name,
                        "text_count": len(texts),
                    },
                )
                vectors = await self.fallback.embed(texts, kind=kind)
                return vectors
            raise

    async def health(self) -> bool:
        """Check health of primary provider (and fallback if configured)."""
        primary_healthy = await self.primary.health()
        if not primary_healthy and self.fallback is not None:
            fallback_healthy = await self.fallback.health()
            logger.warning(
                "LLM Gateway health: primary is unhealthy, fallback status",
                extra={
                    "event": "gateway.health.degraded",
                    "primary_healthy": False,
                    "fallback_healthy": fallback_healthy,
                },
            )
            return fallback_healthy
        return primary_healthy

    async def aclose(self) -> None:
        """Safely clean up resources for both providers."""
        try:
            await self.primary.aclose()
        finally:
            if self.fallback is not None:
                await self.fallback.aclose()
