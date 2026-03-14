"""Log intelligence package -- smart pre-processing that extracts meaningful signals from logs.

Re-exports LogIntelligenceEngine as the public facade, plus sub-module
functions for direct access.
"""

from __future__ import annotations

from .constants import FAILURE_PATTERNS as FAILURE_PATTERNS
from .correlation import correlate_containers as correlate_containers
from .engine import LogIntelligenceEngine as LogIntelligenceEngine
from .level_extraction import extract_level as extract_level
from .stack_traces import detect_stack_traces as detect_stack_traces
from .stack_traces import extract_exception_info as extract_exception_info
from .timestamp import detect_ts_format as detect_ts_format
from .timestamp import parse_timestamp as parse_timestamp
from .windows import find_interesting_windows as find_interesting_windows

__all__ = [
    "LogIntelligenceEngine",
    "FAILURE_PATTERNS",
    "correlate_containers",
    "detect_stack_traces",
    "detect_ts_format",
    "extract_exception_info",
    "extract_level",
    "find_interesting_windows",
    "parse_timestamp",
]
