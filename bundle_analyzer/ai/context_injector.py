"""ISV context injection into analyst prompts.

Loads ISV-specific context (Helm values, architecture docs, READMEs)
and injects relevant sections into analyst system prompts.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger


class ContextInjector:
    """Prepends ISV/vendor context to analyst prompts when available.

    When the ``--context`` flag is used, the injector loads the specified
    file and prepends its content to every analyst system prompt so that
    Claude has ISV-specific knowledge (expected pod names, architecture
    decisions, known limitations, etc.).
    """

    def __init__(
        self,
        context_path: Path | None = None,
        context_text: str | None = None,
    ) -> None:
        """Initialize the context injector.

        Args:
            context_path: Path to an ISV context file. If *None* or if the
                file does not exist, no context is injected.
            context_text: Raw context string (takes priority over file path).
        """
        if context_text and context_text.strip():
            self.context: str | None = context_text.strip()
            logger.info("Loaded ISV context from text ({} chars)", len(self.context))
        elif context_path:
            self.context = self._load(context_path)
            if self.context:
                logger.info(
                    "Loaded ISV context from {} ({} chars)",
                    context_path,
                    len(self.context),
                )
            else:
                logger.debug("No ISV context loaded")
        else:
            self.context = None
            logger.debug("No ISV context loaded")

    def inject(self, base_prompt: str) -> str:
        """Prepend ISV context to any prompt.

        Args:
            base_prompt: The original system or user prompt.

        Returns:
            The prompt with ISV context prepended, or the unchanged
            prompt if no context is available.
        """
        if not self.context:
            return base_prompt
        return f"## ISV/Vendor Context\n{self.context}\n\n---\n\n{base_prompt}"

    @staticmethod
    def _load(context_path: Path) -> str | None:
        """Read the context file from disk.

        Args:
            context_path: Path to the context file.

        Returns:
            File contents as a string, or *None* if reading fails.
        """
        try:
            text = context_path.read_text(encoding="utf-8")
            if not text.strip():
                logger.warning("Context file {} is empty", context_path)
                return None
            return text.strip()
        except FileNotFoundError:
            logger.warning("Context file not found: {}", context_path)
            return None
        except OSError as exc:
            logger.error("Failed to read context file {}: {}", context_path, exc)
            return None
