"""Certificate expiry prediction functions.

Scans TLS secrets for certificates nearing expiry or already expired,
using regex-based date extraction from PEM certificate data.
"""

from __future__ import annotations

from datetime import datetime, timezone

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import PredictedFailure

from .helpers import parse_cert_expiry


def predict_cert_expiry(index: BundleIndex) -> list[PredictedFailure]:
    """Scan TLS secrets for certificates nearing expiry.

    Looks for kubernetes.io/tls type secrets and attempts to parse
    the certificate's NotAfter date.

    Args:
        index: The indexed support bundle.

    Returns:
        List of PredictedFailure objects for expiring/expired certificates.
    """
    predictions: list[PredictedFailure] = []
    secrets_dir = index.root / "cluster-resources" / "secrets"

    if not secrets_dir.is_dir():
        return predictions

    for ns_dir in sorted(secrets_dir.iterdir()):
        if not ns_dir.is_dir():
            continue
        namespace = ns_dir.name

        for secret_file in sorted(ns_dir.glob("*.json")):
            rel = str(secret_file.relative_to(index.root))
            raw = index.read_json(rel)
            if not isinstance(raw, dict):
                continue

            # Handle items-wrapped lists
            if "items" in raw:
                items = raw["items"]
                secret_list = items if isinstance(items, list) else []
            else:
                secret_list = [raw]

            for data in secret_list:
                if not isinstance(data, dict):
                    continue

                secret_type = data.get("type", "")
                if secret_type != "kubernetes.io/tls":
                    continue

                secret_name = data.get("metadata", {}).get("name", "unknown")
                tls_crt = data.get("data", {}).get("tls.crt", "")

                if not tls_crt:
                    continue

                expiry = parse_cert_expiry(tls_crt)
                if expiry is None:
                    continue

                now = datetime.now(timezone.utc)
                remaining = expiry - now
                remaining_seconds = int(remaining.total_seconds())

                if remaining_seconds < 0:
                    predictions.append(
                        PredictedFailure(
                            resource=f"secret/{namespace}/{secret_name}",
                            failure_type="CERT_EXPIRED",
                            estimated_eta_seconds=None,
                            confidence=0.99,
                            evidence=[
                                f"TLS certificate expired {abs(remaining.days)} days ago",
                                f"NotAfter: {expiry.isoformat()}",
                            ],
                            prevention=(
                                f"Renew TLS certificate in secret {secret_name} "
                                f"in namespace {namespace} immediately"
                            ),
                        )
                    )
                elif remaining.days < 30:
                    predictions.append(
                        PredictedFailure(
                            resource=f"secret/{namespace}/{secret_name}",
                            failure_type="CERT_EXPIRING_SOON",
                            estimated_eta_seconds=remaining_seconds,
                            confidence=0.95,
                            evidence=[
                                f"TLS certificate expires in {remaining.days} days",
                                f"NotAfter: {expiry.isoformat()}",
                            ],
                            prevention=(
                                f"Renew TLS certificate in secret {secret_name} "
                                f"in namespace {namespace} before {expiry.date()}"
                            ),
                        )
                    )

    return predictions


def predict_cert_expiry_single(
    secrets_list: list[dict],
) -> list[PredictedFailure]:
    """Scan a list of secret dicts for certificate expiry.

    Args:
        secrets_list: List of Kubernetes Secret JSON dicts.

    Returns:
        List of PredictedFailure for expiring/expired certs.
    """
    predictions: list[PredictedFailure] = []
    for secret in secrets_list:
        if secret.get("type") != "kubernetes.io/tls":
            continue
        secret_name = secret.get("metadata", {}).get("name", "unknown")
        namespace = secret.get("metadata", {}).get("namespace", "unknown")
        tls_crt = secret.get("data", {}).get("tls.crt", "")
        if not tls_crt:
            continue

        expiry = parse_cert_expiry(tls_crt)
        if expiry is None:
            continue

        now = datetime.now(timezone.utc)
        remaining = expiry - now
        if remaining.days < 30:
            predictions.append(
                PredictedFailure(
                    resource=f"secret/{namespace}/{secret_name}",
                    failure_type="CERT_EXPIRED" if remaining.total_seconds() < 0 else "CERT_EXPIRING_SOON",
                    estimated_eta_seconds=max(int(remaining.total_seconds()), 0) or None,
                    confidence=0.95,
                    evidence=[f"Certificate expires: {expiry.isoformat()}"],
                    prevention=f"Renew TLS cert in secret {secret_name} namespace {namespace}",
                )
            )
    return predictions
