"""Ask session engine — grounded Q&A with evidence citations.

Enables engineers to ask follow-up questions about the analysis,
with answers grounded in bundle evidence rather than general knowledge.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from loguru import logger

from bundle_analyzer.ai.client import BundleAnalyzerClient
from bundle_analyzer.ai.prompts.interview import (
    INTERVIEW_SYSTEM_PROMPT,
    build_interview_context,
)
from bundle_analyzer.models import AnalysisResult


class InterviewSession:
    """Maintains a multi-turn Q&A session grounded in bundle evidence.

    Engineers can ask free-form questions about the bundle and receive
    answers that cite specific files, log lines, and event timestamps.
    Supports special commands like ``show pod <name>``, ``show logs <pod>``,
    and ``show events <namespace>``.
    """

    def __init__(
        self,
        analysis_result: AnalysisResult,
        client: BundleAnalyzerClient,
    ) -> None:
        """Initialize an ask session.

        Args:
            analysis_result: The complete analysis result for context.
            client: The Anthropic API client with retry logic.
        """
        self.result = analysis_result
        self.client = client
        self.history: list[dict[str, str]] = []
        self._context = build_interview_context(analysis_result)
        logger.debug(
            "Ask session initialized with {} chars of context",
            len(self._context),
        )

    async def ask(self, question: str) -> str:
        """Ask a question and get an evidence-grounded answer.

        Handles special commands (``show pod``, ``show logs``, ``show events``)
        locally and routes all other questions to Claude with full conversation
        history.

        Args:
            question: The user's question or command.

        Returns:
            The grounded answer string with citations.
        """
        # Handle special commands locally
        command_response = self._handle_command(question)
        if command_response is not None:
            self.history.append({"role": "user", "content": question})
            self.history.append({"role": "assistant", "content": command_response})
            return command_response

        # Build the full prompt with context + history
        user_message = self._build_user_message(question)
        self.history.append({"role": "user", "content": question})

        try:
            response = await self.client.complete(
                system=INTERVIEW_SYSTEM_PROMPT,
                user=user_message,
                max_tokens=2048,
                temperature=0.2,
            )
            self.history.append({"role": "assistant", "content": response})
            logger.debug(
                "Interview response: {} chars for question '{}'",
                len(response),
                question[:60],
            )
            return response
        except RuntimeError as exc:
            error_msg = f"Unable to process question: {exc}"
            logger.error("Interview API call failed: {}", exc)
            self.history.append({"role": "assistant", "content": error_msg})
            return error_msg

    async def ask_stream(self, question: str) -> AsyncIterator[str]:
        """Stream an answer token-by-token for real-time display.

        Falls back to yielding the full response at once for local commands.

        Args:
            question: The user's question or command.

        Yields:
            Text chunks as they are generated.
        """
        # Handle special commands locally (yield all at once)
        command_response = self._handle_command(question)
        if command_response is not None:
            self.history.append({"role": "user", "content": question})
            self.history.append({"role": "assistant", "content": command_response})
            yield command_response
            return

        user_message = self._build_user_message(question)
        self.history.append({"role": "user", "content": question})

        full_response: list[str] = []
        try:
            async for chunk in self.client.stream(
                system=INTERVIEW_SYSTEM_PROMPT,
                user=user_message,
                max_tokens=2048,
                temperature=0.2,
            ):
                full_response.append(chunk)
                yield chunk

            response_text = "".join(full_response)
            self.history.append({"role": "assistant", "content": response_text})
        except Exception as exc:
            error_msg = f"Unable to process question: {exc}"
            logger.error("Interview streaming failed: {}", exc)
            self.history.append({"role": "assistant", "content": error_msg})
            yield error_msg

    def _handle_command(self, question: str) -> str | None:
        """Handle special commands that can be answered from local data.

        Args:
            question: The user input to check for commands.

        Returns:
            A response string if this is a recognized command, else None.
        """
        stripped = question.strip().lower()

        if stripped.startswith("show pod "):
            return self._show_pod(question.strip()[9:].strip())
        if stripped.startswith("show logs "):
            return self._show_logs(question.strip()[10:].strip())
        if stripped.startswith("show events "):
            return self._show_events(question.strip()[12:].strip())
        return None

    def _show_pod(self, pod_name: str) -> str:
        """Show details for a specific pod from triage findings.

        Args:
            pod_name: Name (or partial name) of the pod to look up.

        Returns:
            Formatted string with pod details or a not-found message.
        """
        matches: list[str] = []
        all_pods = (
            self.result.triage.critical_pods + self.result.triage.warning_pods
        )
        for pod in all_pods:
            if pod_name.lower() in pod.pod_name.lower():
                lines = [
                    f"Pod: {pod.namespace}/{pod.pod_name}",
                    f"  Issue: {pod.issue_type}",
                    f"  Container: {pod.container_name or 'N/A'}",
                    f"  Restarts: {pod.restart_count}",
                    f"  Exit code: {pod.exit_code}",
                    f"  Message: {pod.message}",
                ]
                if pod.log_path:
                    lines.append(f"  Log: {pod.log_path}")
                if pod.previous_log_path:
                    lines.append(f"  Previous log: {pod.previous_log_path}")
                matches.append("\n".join(lines))

        if not matches:
            return f"No pod matching '{pod_name}' found in triage results."
        return "\n\n".join(matches)

    def _show_logs(self, pod_name: str) -> str:
        """Show log paths for a specific pod.

        Args:
            pod_name: Name (or partial name) of the pod.

        Returns:
            Formatted string with log paths or a not-found message.
        """
        all_pods = (
            self.result.triage.critical_pods + self.result.triage.warning_pods
        )
        for pod in all_pods:
            if pod_name.lower() in pod.pod_name.lower():
                parts = [f"Logs for {pod.namespace}/{pod.pod_name}:"]
                if pod.log_path:
                    parts.append(f"  Current: {pod.log_path}")
                else:
                    parts.append("  Current: not available")
                if pod.previous_log_path:
                    parts.append(f"  Previous: {pod.previous_log_path}")
                else:
                    parts.append("  Previous: not available")
                return "\n".join(parts)
        return f"No logs found for pod matching '{pod_name}'."

    def _show_events(self, namespace: str) -> str:
        """Show warning events for a specific namespace.

        Args:
            namespace: Namespace to filter events for.

        Returns:
            Formatted string with matching events or a not-found message.
        """
        matches: list[str] = []
        for event in self.result.triage.warning_events:
            if namespace.lower() in event.namespace.lower():
                ts = (
                    event.last_timestamp.isoformat()
                    if event.last_timestamp
                    else "unknown"
                )
                matches.append(
                    f"[{ts}] {event.reason}: {event.involved_object_kind}/"
                    f"{event.involved_object_name} — {event.message} "
                    f"(count={event.count})"
                )

        if not matches:
            return f"No warning events found in namespace '{namespace}'."
        header = f"Warning events in namespace '{namespace}':"
        return header + "\n" + "\n".join(matches)

    def _build_user_message(self, question: str) -> str:
        """Build the full user message including context and conversation history.

        Args:
            question: The new question to ask.

        Returns:
            Formatted message with context, history, and the new question.
        """
        parts: list[str] = [
            "## Analysis Context",
            self._context,
            "",
        ]

        if self.history:
            parts.append("## Conversation History")
            for entry in self.history[-10:]:  # Keep last 10 exchanges
                role_label = "Engineer" if entry["role"] == "user" else "You"
                parts.append(f"{role_label}: {entry['content']}")
            parts.append("")

        parts.append(f"## Current Question\n{question}")
        return "\n".join(parts)
