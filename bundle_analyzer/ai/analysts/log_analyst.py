"""Log analyst — AI-powered container log forensics for crash-looping pods.

Instead of just classifying crash patterns with regex (which CrashLoopAnalyzer
does), this analyst sends relevant log excerpts to the AI and gets a
human-readable diagnosis explaining what went wrong, why, and how to fix it.
"""

from __future__ import annotations

import asyncio
import json

from loguru import logger

from bundle_analyzer.ai.client import BundleAnalyzerClient
from bundle_analyzer.ai.prompts.log_analysis import (
    LOG_ANALYSIS_SYSTEM_PROMPT,
    build_intelligent_log_prompt,
    build_log_analysis_prompt,
)
from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import CrashLoopContext, LogDiagnosis, LogIntelligence, PodLogIntelligence
from bundle_analyzer.security.scrubber import BundleScrubber

# Maximum number of concurrent AI calls to avoid overwhelming the API.
_MAX_CONCURRENT = 3


class LogAnalyst:
    """Analyzes crash-looping container logs using AI for deep diagnosis.

    For each CrashLoopContext produced by the CrashLoopAnalyzer, builds
    a prompt with container logs, exit codes, and events, then asks the
    AI to produce a human-readable diagnosis with root cause and fix.
    """

    MAX_RETRIES: int = 3
    _scrubber: BundleScrubber = BundleScrubber()

    async def analyze_crash_contexts(
        self,
        client: BundleAnalyzerClient,
        crash_contexts: list[CrashLoopContext],
        index: BundleIndex,
        log_intelligence: dict[str, PodLogIntelligence] | None = None,
    ) -> list[LogDiagnosis]:
        """Analyze all crash contexts using AI log forensics.

        Processes up to ``_MAX_CONCURRENT`` crash contexts concurrently
        to avoid overwhelming the API provider with parallel requests.

        Args:
            client: The AI client for completions.
            crash_contexts: List of crash contexts from CrashLoopAnalyzer.
            index: Bundle index for reading related events.

        Returns:
            List of LogDiagnosis objects, one per crash context.
        """
        if not crash_contexts:
            return []

        logger.info(
            "LogAnalyst: analyzing {} crash context(s) (max {} concurrent)",
            len(crash_contexts),
            _MAX_CONCURRENT,
        )

        semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
        tasks = [
            self._analyze_one(client, ctx, index, semaphore, log_intelligence)
            for ctx in crash_contexts
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        diagnoses: list[LogDiagnosis] = []
        for i, result in enumerate(results):
            if isinstance(result, LogDiagnosis):
                diagnoses.append(result)
            elif isinstance(result, Exception):
                ctx = crash_contexts[i]
                logger.error(
                    "LogAnalyst: failed for {}/{}/{}: {}",
                    ctx.namespace, ctx.pod_name, ctx.container_name, result,
                )
                diagnoses.append(self._fallback_diagnosis(ctx, str(result)))

        logger.info("LogAnalyst: produced {} diagnosis(es)", len(diagnoses))
        return diagnoses

    async def _analyze_one(
        self,
        client: BundleAnalyzerClient,
        ctx: CrashLoopContext,
        index: BundleIndex,
        semaphore: asyncio.Semaphore,
        log_intelligence: dict[str, PodLogIntelligence] | None = None,
    ) -> LogDiagnosis:
        """Analyze a single crash context with AI.

        When LogIntelligence is available, uses the pre-digested summary
        (error frequencies, stack traces, interesting windows) instead of
        raw log tails. This gives the AI far richer context in fewer tokens.

        Args:
            client: The AI client for completions.
            ctx: A single crash context to analyze.
            index: Bundle index for reading related events.
            semaphore: Concurrency limiter.
            log_intelligence: Pre-digested log intelligence, if available.

        Returns:
            A LogDiagnosis with the AI's analysis.
        """
        async with semaphore:
            logger.debug(
                "LogAnalyst: analyzing {}/{}/{}",
                ctx.namespace, ctx.pod_name, ctx.container_name,
            )

            # Get related warning events for this pod
            related_events = self._get_pod_events(ctx.namespace, ctx.pod_name, index)

            # Try to use LogIntelligence for a richer prompt
            pod_key = f"{ctx.namespace}/{ctx.pod_name}"
            container_intel: LogIntelligence | None = None
            if log_intelligence and pod_key in log_intelligence:
                pod_intel = log_intelligence[pod_key]
                for ci in pod_intel.containers:
                    if ci.container_name == ctx.container_name:
                        container_intel = ci
                        break

            if container_intel and container_intel.total_lines_scanned > 0:
                # Use the intelligent prompt with pre-digested data
                user_prompt = build_intelligent_log_prompt(
                    pod_name=ctx.pod_name,
                    namespace=ctx.namespace,
                    container_name=ctx.container_name,
                    crash_pattern=ctx.crash_pattern,
                    exit_code=ctx.exit_code,
                    termination_reason=ctx.termination_reason,
                    restart_count=ctx.restart_count,
                    intelligence=container_intel,
                    related_events=related_events,
                )
                logger.debug(
                    "LogAnalyst: using intelligent prompt for {}/{}/{} "
                    "({} lines scanned, {} patterns, {} traces)",
                    ctx.namespace, ctx.pod_name, ctx.container_name,
                    container_intel.total_lines_scanned,
                    len(container_intel.top_patterns),
                    len(container_intel.stack_traces),
                )
            else:
                # Fallback to raw log prompt
                scrubbed_current, _ = self._scrubber.scrub_log_lines(
                    ctx.last_log_lines,
                    source=f"{ctx.namespace}/{ctx.pod_name}/{ctx.container_name}/current",
                )
                scrubbed_previous, _ = self._scrubber.scrub_log_lines(
                    ctx.previous_log_lines,
                    source=f"{ctx.namespace}/{ctx.pod_name}/{ctx.container_name}/previous",
                )
                user_prompt = build_log_analysis_prompt(
                    pod_name=ctx.pod_name,
                    namespace=ctx.namespace,
                    container_name=ctx.container_name,
                    crash_pattern=ctx.crash_pattern,
                    exit_code=ctx.exit_code,
                    termination_reason=ctx.termination_reason,
                    restart_count=ctx.restart_count,
                    current_logs=scrubbed_current,
                    previous_logs=scrubbed_previous,
                    related_events=related_events,
                )

            # Call AI with retries
            for attempt in range(self.MAX_RETRIES):
                try:
                    raw_response = await client.complete(
                        system=LOG_ANALYSIS_SYSTEM_PROMPT,
                        user=user_prompt,
                    )
                    return self._parse_response(raw_response, ctx)

                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    logger.warning(
                        "LogAnalyst: parse error on attempt {}/{} for {}/{}/{}: {}",
                        attempt + 1,
                        self.MAX_RETRIES,
                        ctx.namespace,
                        ctx.pod_name,
                        ctx.container_name,
                        exc,
                    )
                    if attempt == self.MAX_RETRIES - 1:
                        return self._fallback_diagnosis(ctx, str(exc))

            # Should not reach here, but satisfy type checker
            return self._fallback_diagnosis(ctx, "all retries exhausted")

    def _get_pod_events(
        self, namespace: str, pod_name: str, index: BundleIndex
    ) -> str | None:
        """Get formatted warning events for a specific pod.

        Args:
            namespace: Pod namespace.
            pod_name: Pod name.
            index: Bundle index for reading events.

        Returns:
            Formatted event string, or None if no events found.
        """
        try:
            events = index.get_events(namespace=namespace)
        except Exception as exc:
            logger.debug("Failed to get events for {}/{}: {}", namespace, pod_name, exc)
            return None

        pod_events: list[str] = []
        for ev in events:
            obj = ev.get("involvedObject", {})
            if (
                obj.get("kind") == "Pod"
                and obj.get("name") == pod_name
                and ev.get("type") == "Warning"
            ):
                ts = ev.get(
                    "lastTimestamp",
                    ev.get("metadata", {}).get("creationTimestamp", "?"),
                )
                reason = ev.get("reason", "?")
                msg = ev.get("message", "")
                count = ev.get("count", 1)
                pod_events.append(f"[{ts}] {reason} (x{count}): {msg}")

        return "\n".join(pod_events) if pod_events else None

    def _parse_response(
        self, raw: str, ctx: CrashLoopContext
    ) -> LogDiagnosis:
        """Parse the AI's JSON response into a LogDiagnosis.

        Args:
            raw: Raw text response from the AI (should be JSON).
            ctx: The original crash context for metadata.

        Returns:
            A structured LogDiagnosis.

        Raises:
            json.JSONDecodeError: If the response is not valid JSON.
            KeyError: If required fields are missing.
        """
        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:]  # remove opening fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        data = json.loads(cleaned)

        confidence_map = {"high": 0.9, "medium": 0.6, "low": 0.3}
        confidence = confidence_map.get(
            data.get("confidence", "low"), 0.3
        )

        fix_data = data.get("fix", {})
        if isinstance(fix_data, str):
            fix_description = fix_data
            fix_commands: list[str] = []
        else:
            fix_description = fix_data.get("description", "")
            fix_commands = fix_data.get("commands", [])
            yaml_changes = fix_data.get("yaml_changes", "")
            if yaml_changes:
                fix_description = f"{fix_description} YAML changes: {yaml_changes}"

        return LogDiagnosis(
            namespace=ctx.namespace,
            pod_name=ctx.pod_name,
            container_name=ctx.container_name,
            diagnosis=data.get("diagnosis", "No diagnosis provided"),
            root_cause_category=data.get("root_cause_category", "unknown"),
            key_log_line=data.get("key_log_line", ""),
            why=data.get("why", ""),
            fix_description=fix_description,
            fix_commands=fix_commands,
            confidence=confidence,
            additional_context_needed=data.get("additional_context_needed", []),
        )

    @staticmethod
    def _fallback_diagnosis(ctx: CrashLoopContext, error: str) -> LogDiagnosis:
        """Return a low-confidence diagnosis when AI analysis fails.

        Args:
            ctx: The original crash context for metadata.
            error: Description of the error that occurred.

        Returns:
            A LogDiagnosis with low confidence and the crash pattern as fallback.
        """
        return LogDiagnosis(
            namespace=ctx.namespace,
            pod_name=ctx.pod_name,
            container_name=ctx.container_name,
            diagnosis=f"AI log analysis failed: {error}. "
                       f"Regex-based classification: {ctx.crash_pattern}.",
            root_cause_category=ctx.crash_pattern or "unknown",
            key_log_line="",
            why=f"Could not determine — AI analysis error: {error}",
            fix_description="",
            fix_commands=[],
            confidence=0.1,
            additional_context_needed=["Manual log review recommended"],
        )
