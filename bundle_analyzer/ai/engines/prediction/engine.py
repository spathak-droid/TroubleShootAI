"""Forward prediction engine -- public facade.

Orchestrates all prediction sub-modules (OOM, disk, crashloop,
certificates, replicas) and returns a unified list of predicted failures.
"""

from __future__ import annotations

from typing import Optional

from loguru import logger
from pydantic import BaseModel

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import PredictedFailure, TriageResult


class Prediction(BaseModel):
    """A single forward-looking prediction with ETA and confidence."""

    prediction_type: str
    resource: str
    eta_human: str  # "~2 hours", "~3 days", "unknown"
    eta_seconds: Optional[int] = None
    confidence: float
    basis: str  # how this was calculated
    action_required: str

from .certificates import predict_cert_expiry
from .crashloop import predict_crashloop_permanent
from .disk import predict_disk_full
from .oom import predict_oom_from_pods
from .replicas import predict_replica_exhaustion


class ForwardPredictionEngine:
    """Predicts upcoming failures based on current resource trends.

    Implements deterministic predictors for OOM, disk exhaustion,
    permanent crash loops, certificate expiry, and replica exhaustion.
    """

    async def predict(
        self,
        triage: TriageResult,
        index: BundleIndex,
    ) -> list[PredictedFailure]:
        """Run all predictors and return a list of predicted failures.

        Args:
            triage: The triage result from Phase 1 scanners.
            index: The indexed support bundle.

        Returns:
            List of PredictedFailure objects for impending issues.
        """
        predictions: list[PredictedFailure] = []

        predictions.extend(predict_oom_from_pods(index))
        predictions.extend(predict_disk_full(index))
        predictions.extend(predict_crashloop_permanent(index, triage))
        predictions.extend(predict_cert_expiry(index))
        predictions.extend(predict_replica_exhaustion(index))

        logger.info("Prediction engine: {} predictions generated", len(predictions))
        return predictions
