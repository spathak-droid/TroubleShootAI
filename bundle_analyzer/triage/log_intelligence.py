"""Backward-compatibility shim -- re-exports from the log_intel package.

All functionality has been moved to bundle_analyzer.triage.log_intel.
This module preserves the original import paths so existing code
continues to work without modification.
"""

from __future__ import annotations

# Re-export everything under the original private names for backward compat
from bundle_analyzer.triage.log_intel.constants import (
    FAILURE_PATTERNS as _FAILURE_PATTERNS,
    MAX_CONTAINERS_PER_POD as _MAX_CONTAINERS_PER_POD,
    MAX_PATTERNS as _MAX_PATTERNS,
    MAX_PODS as _MAX_PODS,
    MAX_TRACE_GROUPS as _MAX_TRACE_GROUPS,
    MAX_WINDOWS as _MAX_WINDOWS,
    SIDECAR_NAMES as _SIDECAR_NAMES,
    BUCKET_SECONDS as _BUCKET_SECONDS,
    CONTEXT_AFTER as _CONTEXT_AFTER,
    CONTEXT_BEFORE as _CONTEXT_BEFORE,
    SPIKE_MULTIPLIER as _SPIKE_MULTIPLIER,
    WINDOW_SIZE as _WINDOW_SIZE,
)
from bundle_analyzer.triage.log_intel.correlation import (
    correlate_containers as _correlate_containers,
)
from bundle_analyzer.triage.log_intel.engine import (
    LogIntelligenceEngine,
)
from bundle_analyzer.triage.log_intel.level_extraction import (
    extract_level as _extract_level,
)
from bundle_analyzer.triage.log_intel.stack_traces import (
    detect_stack_traces as _detect_stack_traces,
    extract_exception_info as _extract_exception_info,
)
from bundle_analyzer.triage.log_intel.timestamp import (
    _TS_PATTERNS,
    detect_ts_format as _detect_ts_format,
    parse_timestamp as _parse_timestamp,
)
from bundle_analyzer.triage.log_intel.windows import (
    find_interesting_windows as _find_interesting_windows,
)

__all__ = [
    "LogIntelligenceEngine",
    "_FAILURE_PATTERNS",
    "_correlate_containers",
    "_detect_stack_traces",
    "_detect_ts_format",
    "_extract_exception_info",
    "_extract_level",
    "_find_interesting_windows",
    "_parse_timestamp",
    "_TS_PATTERNS",
]
