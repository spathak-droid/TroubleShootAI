"""Multi-provider AI client with OpenRouter primary, OpenAI fallback.

Supports OpenRouter (any model), OpenAI, and Anthropic direct.
Provider priority: OpenRouter → OpenAI → Anthropic.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncIterator
from typing import Optional

from loguru import logger

from bundle_analyzer.security.models import SanitizationReport
from bundle_analyzer.security.scrubber import BundleScrubber


def _resolve_provider() -> tuple[str, str, str]:
    """Determine which provider to use based on available env vars.

    Returns:
        Tuple of (provider_name, api_key, model).
    """
    # Priority 1: OpenRouter
    or_key = os.environ.get("OPEN_ROUTER_API_KEY")
    if or_key:
        model = os.environ.get("OPEN_ROUTER_MODEL", "anthropic/claude-haiku-4.5")
        return "openrouter", or_key, model

    # Priority 2: OpenAI
    oai_key = os.environ.get("OPENAI_API_KEY")
    if oai_key:
        model = os.environ.get("OPEN_AI_MODEL", "gpt-4.1-nano")
        return "openai", oai_key, model

    # Priority 3: Anthropic direct
    ant_key = os.environ.get("ANTHROPIC_API_KEY")
    if ant_key:
        model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
        return "anthropic", ant_key, model

    raise RuntimeError(
        "No AI provider configured. Set one of: "
        "OPEN_ROUTER_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY in .env"
    )


class BundleAnalyzerClient:
    """Multi-provider AI client with retry logic and token tracking.

    Provider priority: OpenRouter → OpenAI → Anthropic.
    OpenRouter and OpenAI both use the OpenAI SDK.
    Anthropic uses its own SDK.
    """

    def __init__(self, api_key: Optional[str] = None, max_retries: int = 3) -> None:
        """Initialise the AI client with the best available provider.

        Args:
            api_key: Override API key. If not set, auto-detects from env.
            max_retries: Maximum retry attempts on rate-limit errors.
        """
        self.max_retries = max_retries
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self._scrubber = BundleScrubber()
        self.last_sanitization_report: SanitizationReport | None = None

        if api_key:
            # Explicit key — try to guess provider from env
            self._provider = "openrouter" if os.environ.get("OPEN_ROUTER_API_KEY") else "openai"
            self._api_key = api_key
            self._model = os.environ.get("OPEN_ROUTER_MODEL", "anthropic/claude-haiku-4.5")
        else:
            self._provider, self._api_key, self._model = _resolve_provider()

        logger.info(
            "AI client initialized | provider={provider} model={model}",
            provider=self._provider,
            model=self._model,
        )

        self._init_clients()

    def _init_clients(self) -> None:
        """Create the appropriate SDK clients based on provider."""
        if self._provider in ("openrouter", "openai"):
            from openai import AsyncOpenAI, OpenAI

            base_url = (
                "https://openrouter.ai/api/v1"
                if self._provider == "openrouter"
                else None
            )
            self._sync_client = OpenAI(api_key=self._api_key, base_url=base_url, timeout=120.0)
            self._async_client = AsyncOpenAI(api_key=self._api_key, base_url=base_url, timeout=120.0)
            self._call_async = self._openai_async
            self._call_sync = self._openai_sync
        else:
            import anthropic

            self._sync_client = anthropic.Anthropic(api_key=self._api_key)
            self._async_client = anthropic.AsyncAnthropic(api_key=self._api_key)
            self._call_async = self._anthropic_async
            self._call_sync = self._anthropic_sync

    async def _openai_async(
        self, system: str, user: str, max_tokens: int, temperature: float
    ) -> str:
        """Make an async call via OpenAI-compatible API."""
        response = await self._async_client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        usage = response.usage
        if usage:
            self.total_input_tokens += usage.prompt_tokens or 0
            self.total_output_tokens += usage.completion_tokens or 0
        return response.choices[0].message.content or ""

    def _openai_sync(
        self, system: str, user: str, max_tokens: int, temperature: float
    ) -> str:
        """Make a sync call via OpenAI-compatible API."""
        response = self._sync_client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        usage = response.usage
        if usage:
            self.total_input_tokens += usage.prompt_tokens or 0
            self.total_output_tokens += usage.completion_tokens or 0
        return response.choices[0].message.content or ""

    async def _anthropic_async(
        self, system: str, user: str, max_tokens: int, temperature: float
    ) -> str:
        """Make an async call via Anthropic API."""
        response = await self._async_client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        self.total_input_tokens += response.usage.input_tokens
        self.total_output_tokens += response.usage.output_tokens
        return response.content[0].text if response.content else ""

    def _anthropic_sync(
        self, system: str, user: str, max_tokens: int, temperature: float
    ) -> str:
        """Make a sync call via Anthropic API."""
        response = self._sync_client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        self.total_input_tokens += response.usage.input_tokens
        self.total_output_tokens += response.usage.output_tokens
        return response.content[0].text if response.content else ""

    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        """Async completion with automatic retry on rate limits.

        Args:
            system: System prompt string.
            user: User prompt string.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.

        Returns:
            The model's text response.
        """
        # Scrub user prompt before sending (system prompts are our templates)
        sanitized_user, san_report = self._scrubber.scrub_for_llm(user)
        self.last_sanitization_report = san_report
        if san_report.total_redactions > 0:
            logger.info(
                "Sanitized {} sensitive patterns before LLM call",
                san_report.total_redactions,
            )
        if san_report.prompt_injection_detected:
            logger.warning(
                "Prompt injection attempt detected and neutralized ({} instance(s))",
                san_report.prompt_injection_count,
            )

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                start = time.monotonic()
                text = await self._call_async(system, sanitized_user, max_tokens, temperature)
                elapsed = time.monotonic() - start

                logger.debug(
                    "AI call completed in {elapsed:.2f}s | "
                    "in={in_tok} out={out_tok} | provider={provider} model={model}",
                    elapsed=elapsed,
                    in_tok=self.total_input_tokens,
                    out_tok=self.total_output_tokens,
                    provider=self._provider,
                    model=self._model,
                )
                return text

            except Exception as exc:
                err_name = type(exc).__name__.lower()
                is_retryable = (
                    "ratelimit" in err_name
                    or "rate_limit" in err_name
                    or "429" in str(exc)
                    or "timeout" in err_name
                )
                if is_retryable:
                    last_error = exc
                    backoff = 2**attempt
                    logger.warning(
                        "Retryable error {err} (attempt {attempt}/{max}), retrying in {backoff}s",
                        err=err_name,
                        attempt=attempt + 1,
                        max=self.max_retries,
                        backoff=backoff,
                    )
                    await asyncio.sleep(backoff)
                else:
                    raise

        raise last_error  # type: ignore[misc]

    async def stream(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> AsyncIterator[str]:
        """Async streaming completion — yields text chunks as they arrive.

        Args:
            system: System prompt string.
            user: User prompt string.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.

        Yields:
            Text chunks as they are generated by the model.
        """
        sanitized_user, san_report = self._scrubber.scrub_for_llm(user)
        self.last_sanitization_report = san_report
        if san_report.total_redactions > 0:
            logger.info(
                "Sanitized {} sensitive patterns before streaming LLM call",
                san_report.total_redactions,
            )

        if self._provider in ("openrouter", "openai"):
            stream = await self._async_client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": sanitized_user},
                ],
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        else:
            # Anthropic streaming
            async with self._async_client.messages.stream(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": sanitized_user}],
            ) as stream:
                async for text in stream.text_stream:
                    yield text

    def complete_sync(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        """Synchronous completion for simple use cases.

        Args:
            system: System prompt string.
            user: User prompt string.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.

        Returns:
            The model's text response.
        """
        # Scrub user prompt before sending (system prompts are our templates)
        sanitized_user, san_report = self._scrubber.scrub_for_llm(user)
        self.last_sanitization_report = san_report
        if san_report.total_redactions > 0:
            logger.info(
                "Sanitized {} sensitive patterns before sync LLM call",
                san_report.total_redactions,
            )

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                start = time.monotonic()
                text = self._call_sync(system, sanitized_user, max_tokens, temperature)
                elapsed = time.monotonic() - start

                logger.debug(
                    "AI sync call completed in {elapsed:.2f}s | "
                    "provider={provider} model={model}",
                    elapsed=elapsed,
                    provider=self._provider,
                    model=self._model,
                )
                return text

            except Exception as exc:
                err_name = type(exc).__name__.lower()
                if "ratelimit" in err_name or "rate_limit" in err_name or "429" in str(exc):
                    last_error = exc
                    backoff = 2**attempt
                    logger.warning(
                        "Rate limited sync (attempt {attempt}/{max}), sleeping {backoff}s",
                        attempt=attempt + 1,
                        max=self.max_retries,
                        backoff=backoff,
                    )
                    time.sleep(backoff)
                else:
                    raise

        raise last_error  # type: ignore[misc]
