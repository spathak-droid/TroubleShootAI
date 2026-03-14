"""Wraps the kubectl preflight CLI for running preflight checks.

Shells out to ``kubectl preflight`` and parses JSON output into
typed PreflightReport models.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from loguru import logger

from bundle_analyzer.bundle.troubleshoot_parser import TroubleshootParser
from bundle_analyzer.models import PreflightReport


class PreflightRunner:
    """Runs troubleshoot.sh preflight checks via the kubectl plugin.

    Requires ``kubectl`` and the ``preflight`` plugin to be installed.
    See https://troubleshoot.sh/docs/preflight/
    """

    def __init__(self) -> None:
        """Initialize with a TroubleshootParser instance."""
        self._parser = TroubleshootParser()

    async def run(
        self,
        spec_path: Path,
        kubeconfig: Path | None = None,
        timeout_seconds: int = 120,
    ) -> PreflightReport:
        """Execute preflight checks and parse results.

        Args:
            spec_path: Path to the preflight spec YAML file.
            kubeconfig: Optional path to kubeconfig file. If None, uses
                        the default kubectl context.
            timeout_seconds: Maximum time to wait for preflight to complete.

        Returns:
            Parsed PreflightReport with typed results.

        Raises:
            FileNotFoundError: If kubectl or preflight plugin is not found.
            RuntimeError: If preflight execution fails.
        """
        kubectl = shutil.which("kubectl")
        if kubectl is None:
            raise FileNotFoundError("kubectl not found in PATH")

        cmd = [
            kubectl, "preflight",
            str(spec_path),
            "--interactive=false",
            "--format=json",
        ]
        if kubeconfig is not None:
            cmd.extend(["--kubeconfig", str(kubeconfig)])

        logger.info("Running preflight: {}", " ".join(cmd))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.error("Preflight timed out after {}s", timeout_seconds)
            raise RuntimeError(f"Preflight timed out after {timeout_seconds}s")
        except FileNotFoundError:
            raise FileNotFoundError(
                "kubectl preflight plugin not installed. "
                "Install with: kubectl krew install preflight"
            )

        if proc.returncode != 0:
            err_msg = stderr.decode(errors="replace").strip()
            logger.error("Preflight failed (exit {}): {}", proc.returncode, err_msg)
            raise RuntimeError(f"Preflight failed: {err_msg}")

        # Parse JSON output
        try:
            raw = json.loads(stdout.decode(errors="replace"))
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse preflight JSON output: {}", exc)
            raise RuntimeError(f"Failed to parse preflight output: {exc}")

        # Output may be a list of results or a dict with a "results" key
        if isinstance(raw, list):
            results_list = raw
        elif isinstance(raw, dict):
            results_list = raw.get("results", raw.get("items", []))
        else:
            results_list = []

        return self._parser.parse_preflight(results_list)
