"""Policy engine — determines scrub level per source type and policy mode."""

from __future__ import annotations
from typing import Literal
from loguru import logger
from bundle_analyzer.security.models import SecurityPolicy


SourceType = Literal[
    "pod_spec", "container_log", "node_json", "event",
    "configmap", "secret", "stack_trace", "ci_output",
    "prompt", "unknown"
]


class PolicyEngine:
    """Evaluates what to scrub based on source type and security policy."""

    # Scrub levels: light (preserve most), standard, aggressive (redact most)
    _SOURCE_SCRUB_LEVELS: dict[str, str] = {
        "pod_spec": "standard",
        "container_log": "aggressive",   # logs leak the most
        "node_json": "standard",
        "event": "light",                # events are mostly safe metadata
        "configmap": "aggressive",       # may contain config with secrets
        "secret": "aggressive",
        "stack_trace": "aggressive",     # file paths, code, internal URLs
        "ci_output": "aggressive",
        "prompt": "standard",            # our own prompt templates
        "unknown": "aggressive",         # when in doubt, scrub hard
    }

    def __init__(self, policy: SecurityPolicy | None = None) -> None:
        """Initialize the policy engine with an optional security policy."""
        self.policy = policy or SecurityPolicy()

    def get_scrub_level(self, source_type: SourceType) -> str:
        """Return scrub level for a given source type."""
        if self.policy.mode == "strict":
            return "aggressive"
        if self.policy.mode == "allowlist":
            return "allowlist"
        return self._SOURCE_SCRUB_LEVELS.get(source_type, "aggressive")

    def should_redact_category(self, category: str) -> bool:
        """Check if a category should be redacted under current policy."""
        mapping = {
            "credential": self.policy.redact_credentials,
            "pii": self.policy.redact_pii,
            "infrastructure": self.policy.redact_internal_ips or self.policy.redact_hostnames,
            "proprietary_code": self.policy.redact_file_paths,
            "high_entropy": self.policy.redact_high_entropy,
            "prompt_injection": True,  # always detect
        }
        return mapping.get(category, True)

    def should_preserve(self, data_type: str) -> bool:
        """Check if a specific data type should be preserved."""
        mapping = {
            "k8s_resource_name": self.policy.preserve_k8s_resource_names,
            "namespace": self.policy.preserve_namespace_names,
            "label_key": self.policy.preserve_label_keys,
            "env_var_name": self.policy.preserve_env_var_names,
            "container_image": self.policy.preserve_container_image_names,
            "resource_limits": self.policy.preserve_resource_limits,
            "probe_path": self.policy.preserve_probe_paths,
            "event_reason": self.policy.preserve_event_reasons,
            "hidden_marker": self.policy.preserve_hidden_markers,
        }
        return mapping.get(data_type, False)
