"""Prediction step — forward-looking failure detection."""

from __future__ import annotations

import traceback

from loguru import logger

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import PredictedFailure, TriageResult


async def run_prediction(
    triage: TriageResult,
    index: BundleIndex,
) -> list[PredictedFailure]:
    """Run the prediction engine for forward-looking failure detection.

    Args:
        triage: Triage results with current state.
        index: Bundle index for reading metrics.

    Returns:
        List of predicted failures.
    """
    try:
        from bundle_analyzer.ai.engines.prediction import ForwardPredictionEngine

        engine = ForwardPredictionEngine()
        return await engine.predict(triage, index)
    except (ImportError, AttributeError, TypeError) as exc:
        logger.debug("Prediction engine not available: {}", exc)
        return []
    except Exception as exc:
        logger.warning("Prediction engine failed: {} ({})", exc, type(exc).__name__)
        logger.debug("Prediction engine traceback:\n{}", traceback.format_exc())
        return []
