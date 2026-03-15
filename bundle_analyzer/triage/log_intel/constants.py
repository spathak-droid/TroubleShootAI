"""Constants and failure pattern library for log intelligence.

Contains limits, sidecar names, and 30+ K8s failure signature patterns
used to match against log lines in a single pass.
"""

from __future__ import annotations

import re

# ── Limits ────────────────────────────────────────────────────────────

# Max containers to analyze per pod (prevent runaway on sidecar-heavy pods)
MAX_CONTAINERS_PER_POD: int = 8

# Max pods to analyze in one scan
MAX_PODS: int = 50

# Max windows per container
MAX_WINDOWS: int = 10

# Lines per window
WINDOW_SIZE: int = 30

# Context lines around an interesting event
CONTEXT_BEFORE: int = 10
CONTEXT_AFTER: int = 20

# Rate bucket size in seconds
BUCKET_SECONDS: int = 60

# Spike threshold: bucket count must be this many times the median
SPIKE_MULTIPLIER: float = 3.0

# Max pattern groups to track
MAX_PATTERNS: int = 100

# Max stack trace groups to track
MAX_TRACE_GROUPS: int = 50

# Well-known sidecar container names
SIDECAR_NAMES: frozenset[str] = frozenset({
    "istio-proxy", "envoy", "envoy-sidecar", "linkerd-proxy",
    "vault-agent", "vault-agent-init", "fluent-bit", "fluentd",
    "filebeat", "datadog-agent", "otel-collector", "jaeger-agent",
    "consul-connect-inject", "aws-xray-daemon",
})


# ── Pattern library (30+ K8s failure signatures) ─────────────────────

# Each entry: (category, human_label, compiled_regex, severity)
FAILURE_PATTERNS: list[tuple[str, str, re.Pattern[str], str]] = [
    # DNS
    ("dns", "DNS lookup failed", re.compile(r'(?:dns|resolve).*(?:fail|error|timeout)|no\s+such\s+host|NXDOMAIN|coredns.*timeout', re.I), "warning"),
    ("dns", "DNS resolution timeout", re.compile(r'(?:resolve|lookup).*timed?\s*out|dns.*timed?\s*out', re.I), "warning"),

    # TLS / Certificates
    ("tls", "Certificate expired", re.compile(r'certificate\s+(?:has\s+)?expired|x509.*expired', re.I), "critical"),
    ("tls", "Unknown certificate authority", re.compile(r'x509.*unknown\s+authority|certificate\s+signed\s+by\s+unknown', re.I), "critical"),
    ("tls", "TLS handshake failure", re.compile(r'tls\s+handshake\s+(?:timeout|error|fail)', re.I), "warning"),
    ("tls", "Certificate not yet valid", re.compile(r'certificate\s+is\s+not\s+yet\s+valid|x509.*not\s+valid\s+before', re.I), "warning"),

    # Connection
    ("connection", "Connection refused", re.compile(r'connection\s+refused|ECONNREFUSED', re.I), "warning"),
    ("connection", "Connection reset", re.compile(r'connection\s+reset\s+by\s+peer|ECONNRESET', re.I), "warning"),
    ("connection", "Connection timeout", re.compile(r'(?:connection|dial|connect)\s+timed?\s*out|i/o\s+timeout', re.I), "warning"),
    ("connection", "No route to host", re.compile(r'no\s+route\s+to\s+host|EHOSTUNREACH', re.I), "warning"),

    # Pool exhaustion
    ("pool", "Connection pool exhausted", re.compile(r'(?:connection|conn)\s+pool\s+(?:exhausted|full|limit)', re.I), "critical"),
    ("pool", "Too many open files", re.compile(r'too\s+many\s+open\s+files|EMFILE|ENFILE', re.I), "critical"),
    ("pool", "Max connections reached", re.compile(r'(?:max|maximum)\s+(?:connections?|retries)\s+(?:reached|exceeded)', re.I), "warning"),

    # Rate limiting
    ("ratelimit", "Rate limited", re.compile(r'rate\s+limit|429\s+Too\s+Many|throttl|too\s+many\s+requests', re.I), "warning"),
    ("ratelimit", "Backoff / retry", re.compile(r'(?:exponential\s+)?back.?off|retry.after', re.I), "info"),

    # Leader election / coordination
    ("leader", "Leader election issue", re.compile(r'leader\s+election|not\s+the\s+leader|lost\s+(?:lease|lock|leadership)', re.I), "warning"),
    ("leader", "Lease expired", re.compile(r'lease\s+(?:expired|lost|not\s+renewed)', re.I), "warning"),

    # etcd
    ("etcd", "etcd timeout", re.compile(r'etcd.*(?:timeout|timed\s*out)|etcdserver.*request\s+timed?\s*out', re.I), "critical"),
    ("etcd", "etcd space exceeded", re.compile(r'mvcc.*database\s+space\s+exceeded|etcd.*no\s+space', re.I), "critical"),
    ("etcd", "etcd connection refused", re.compile(r'etcd.*connection\s+refused', re.I), "critical"),

    # OOM / Memory
    ("oom", "Out of memory", re.compile(r'OOMKill|out\s+of\s+memory|Cannot\s+allocate\s+memory', re.I), "critical"),
    ("oom", "Java heap exhausted", re.compile(r'java\.lang\.OutOfMemoryError|GC\s+overhead\s+limit\s+exceeded|heap\s+space', re.I), "critical"),
    ("oom", "Memory cgroup kill", re.compile(r'memory\s+cgroup\s+out\s+of\s+memory|killed\s+.*process.*oom', re.I), "critical"),

    # Shutdown signals
    ("shutdown", "Graceful shutdown", re.compile(r'graceful\s+shutdown|SIGTERM|received\s+signal|shutting\s+down', re.I), "info"),
    ("shutdown", "Forced kill", re.compile(r'SIGKILL|kill\s+-9|forced\s+termination', re.I), "warning"),
    ("shutdown", "Context deadline exceeded", re.compile(r'context\s+deadline\s+exceeded|context\s+canceled', re.I), "warning"),

    # Probes
    ("probe", "Liveness probe failed", re.compile(r'liveness\s+probe\s+failed', re.I), "critical"),
    ("probe", "Readiness probe failed", re.compile(r'readiness\s+probe\s+failed', re.I), "warning"),
    ("probe", "Startup probe failed", re.compile(r'startup\s+probe\s+failed', re.I), "warning"),

    # Storage
    ("storage", "Disk full", re.compile(r'no\s+space\s+left\s+on\s+device|ENOSPC|disk\s+full', re.I), "critical"),
    ("storage", "Volume mount failed", re.compile(r'(?:volume|mount)\s+(?:mount\s+)?failed|MountVolume.*failed', re.I), "critical"),
    ("storage", "Permission denied (filesystem)", re.compile(r'permission\s+denied.*(?:mount|volume|disk|write|read)', re.I), "warning"),

    # Auth / RBAC
    ("auth", "Unauthorized (401)", re.compile(r'\b401\b.*Unauthorized|Unauthorized|token\s+expired|invalid\s+token', re.I), "warning"),
    ("auth", "Forbidden (403)", re.compile(r'\b403\b.*Forbidden|Forbidden|RBAC|cannot\s+\w+\s+resource', re.I), "warning"),

    # Scheduling
    ("scheduling", "Insufficient resources", re.compile(r'Insufficient\s+(?:cpu|memory)|FailedScheduling', re.I), "warning"),
    ("scheduling", "Node taint/affinity", re.compile(r'node\(s\)\s+had\s+taint|node.*unschedulable|affinity.*not\s+match', re.I), "warning"),

    # Image
    ("image", "Image pull failure", re.compile(r'ImagePullBackOff|ErrImagePull|manifest\s+unknown|unauthorized.*image', re.I), "critical"),

    # CrashLoop
    ("crashloop", "CrashLoopBackOff", re.compile(r'CrashLoopBackOff|back-off.*restarting', re.I), "critical"),

    # Panic / crash
    ("panic", "Go panic", re.compile(r'panic:\s|goroutine\s+\d+\s+\[|runtime\s+error:', re.I), "critical"),
    ("panic", "Python traceback", re.compile(r'Traceback\s+\(most\s+recent\s+call\s+last\)', re.I), "critical"),
    ("panic", "Java exception", re.compile(r'Exception\s+in\s+thread|\.(?:Exception|Error):', re.I), "warning"),
    ("panic", "Segfault", re.compile(r'segmentation\s+fault|SIGSEGV|signal\s*:?\s*11', re.I), "critical"),
]
