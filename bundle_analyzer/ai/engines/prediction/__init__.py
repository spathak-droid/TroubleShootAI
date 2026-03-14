"""Forward failure prediction engine package.

Analyzes current trends (memory growth, restart frequency, disk usage)
to predict upcoming failures before they happen.
"""

from .engine import ForwardPredictionEngine, Prediction

__all__ = ["ForwardPredictionEngine", "Prediction"]
