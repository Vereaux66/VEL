#!/usr/bin/env python3
"""
ANVEL Enhanced Prediction Module
Advanced ML techniques for improved trading accuracy
"""

import logging
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

try:
    import numpy as np
except ImportError:
    # Fallback for systems without numpy
    class np:
        @staticmethod
        def array(x):
            return x

        @staticmethod
        def mean(x):
            return sum(x) / len(x) if x else 0

        @staticmethod
        def std(x):
            if not x:
                return 0
            m = sum(x) / len(x)
            return (sum((i - m) ** 2 for i in x) / len(x)) ** 0.5


class EnhancedPredictor:
    """
    Enhanced prediction system with:
    - Ensemble learning with confidence scoring
    - Adaptive model weighting
    - Pattern recognition
    - Market regime detection
    - Prediction calibration
    """

    def __init__(self):
        self.model_weights = {
            "lstm": 0.25,
            "transformer": 0.25,
            "ensemble": 0.25,
            "rl": 0.25,
        }
        self.prediction_history: List[Dict] = []
        self.accuracy_by_model: Dict[str, float] = {
            "lstm": 0.5,
            "transformer": 0.5,
            "ensemble": 0.5,
            "rl": 0.5,
        }
        self.market_regime = "neutral"  # 'trending', 'ranging', 'volatile'

        logger.info("Enhanced Predictor initialized")

    def predict_with_confidence(
        self, features: List[float], models: Dict[str, Any]
    ) -> Tuple[float, float]:
        """
        Generate prediction with confidence score

        Args:
            features: Feature vector for prediction
            models: Dictionary of available models

        Returns:
            (prediction, confidence) tuple
        """
        predictions = []
        weights = []

        # Get predictions from each model
        for model_name, model in models.items():
            if model_name not in self.model_weights:
                continue

            try:
                pred = self._get_model_prediction(model, features)
                predictions.append(pred)
                weights.append(self.model_weights[model_name])
            except Exception as e:
                logger.warning(f"Model {model_name} prediction failed: {e}")
                continue

        if not predictions:
            return 0.0, 0.0

        # Weighted average prediction
        total_weight = sum(weights)
        weighted_pred = sum(p * w for p, w in zip(predictions, weights)) / total_weight

        # Calculate confidence based on agreement between models
        pred_std = np.std(predictions) if len(predictions) > 1 else 0.1
        confidence = 1.0 / (1.0 + pred_std)  # Higher agreement = higher confidence

        # Adjust confidence based on historical accuracy
        avg_accuracy = sum(self.accuracy_by_model.values()) / len(
            self.accuracy_by_model
        )
        confidence *= avg_accuracy

        # Adjust confidence based on market regime
        regime_confidence = self._get_regime_confidence()
        confidence *= regime_confidence

        logger.debug(
            f"Prediction: {weighted_pred:.4f}, Confidence: {confidence:.2f}, "
            f"Regime: {self.market_regime}"
        )

        return weighted_pred, confidence

    def _get_model_prediction(self, model: Any, features: List[float]) -> float:
        """Get prediction from a single model"""
        # Mock prediction - in production this would call actual model
        if hasattr(model, "predict"):
            return float(model.predict(features))
        return 0.0

    def detect_market_regime(self, price_history: List[float]) -> str:
        """
        Detect current market regime

        Args:
            price_history: Recent price history

        Returns:
            Market regime: 'trending', 'ranging', 'volatile', 'neutral'
        """
        if len(price_history) < 20:
            return "neutral"

        recent = price_history[-20:]

        # Calculate metrics
        returns = [
            (recent[i] - recent[i - 1]) / recent[i - 1] for i in range(1, len(recent))
        ]
        volatility = np.std(returns)
        trend_strength = abs(recent[-1] - recent[0]) / recent[0]

        # Detect regime
        if volatility > 0.03:
            regime = "volatile"
        elif trend_strength > 0.05:
            regime = "trending"
        elif volatility < 0.01:
            regime = "ranging"
        else:
            regime = "neutral"

        if regime != self.market_regime:
            logger.info(f"Market regime changed: {self.market_regime} -> {regime}")
            self.market_regime = regime

        return regime

    def _get_regime_confidence(self) -> float:
        """Get confidence multiplier based on market regime"""
        regime_multipliers = {
            "trending": 1.2,  # Models perform well in trends
            "ranging": 0.9,  # Harder to predict in ranges
            "volatile": 0.7,  # Low confidence in high volatility
            "neutral": 1.0,
        }
        return regime_multipliers.get(self.market_regime, 1.0)

    def update_model_weights(self, feedback: Dict[str, bool]) -> None:
        """
        Update model weights based on prediction feedback

        Args:
            feedback: Dictionary of model_name -> was_correct
        """
        learning_rate = 0.1

        for model_name, was_correct in feedback.items():
            if model_name not in self.model_weights:
                continue

            # Update accuracy
            current_acc = self.accuracy_by_model[model_name]
            new_acc = current_acc * 0.9 + (1.0 if was_correct else 0.0) * 0.1
            self.accuracy_by_model[model_name] = new_acc

            # Update weight based on accuracy
            if was_correct:
                self.model_weights[model_name] *= 1 + learning_rate
            else:
                self.model_weights[model_name] *= 1 - learning_rate

        # Normalize weights
        total_weight = sum(self.model_weights.values())
        for model_name in self.model_weights:
            self.model_weights[model_name] /= total_weight

        logger.info(f"Updated model weights: {self.model_weights}")

    def detect_patterns(self, price_history: List[float]) -> List[Dict]:
        """
        Detect chart patterns for enhanced prediction

        Returns:
            List of detected patterns with confidence scores
        """
        if len(price_history) < 20:
            return []

        patterns = []

        # Detect double top/bottom
        pattern = self._detect_double_top_bottom(price_history)
        if pattern:
            patterns.append(pattern)

        # Detect head and shoulders
        pattern = self._detect_head_shoulders(price_history)
        if pattern:
            patterns.append(pattern)

        # Detect support/resistance breakout
        pattern = self._detect_breakout(price_history)
        if pattern:
            patterns.append(pattern)

        return patterns

    def _detect_double_top_bottom(self, prices: List[float]) -> Optional[Dict]:
        """Detect double top or double bottom pattern"""
        if len(prices) < 30:
            return None

        recent = prices[-30:]
        max_price = max(recent)
        min_price = min(recent)

        # Find peaks
        peaks = []
        for i in range(1, len(recent) - 1):
            if recent[i] > recent[i - 1] and recent[i] > recent[i + 1]:
                peaks.append((i, recent[i]))

        # Check for double top
        if len(peaks) >= 2:
            last_two = peaks[-2:]
            if abs(last_two[0][1] - last_two[1][1]) / max_price < 0.02:
                return {"pattern": "double_top", "confidence": 0.7, "signal": "bearish"}

        # Find troughs for double bottom
        troughs = []
        for i in range(1, len(recent) - 1):
            if recent[i] < recent[i - 1] and recent[i] < recent[i + 1]:
                troughs.append((i, recent[i]))

        if len(troughs) >= 2:
            last_two = troughs[-2:]
            if abs(last_two[0][1] - last_two[1][1]) / min_price < 0.02:
                return {
                    "pattern": "double_bottom",
                    "confidence": 0.7,
                    "signal": "bullish",
                }

        return None

    def _detect_head_shoulders(self, prices: List[float]) -> Optional[Dict]:
        """Detect head and shoulders pattern"""
        # Simplified detection - would be more sophisticated in production
        if len(prices) < 40:
            return None

        recent = prices[-40:]
        peaks = []

        for i in range(5, len(recent) - 5):
            if recent[i] > max(recent[i - 5 : i]) and recent[i] > max(
                recent[i + 1 : i + 6]
            ):
                peaks.append((i, recent[i]))

        if len(peaks) >= 3:
            # Check if middle peak is highest (head)
            if peaks[-2][1] > peaks[-3][1] and peaks[-2][1] > peaks[-1][1]:
                return {
                    "pattern": "head_shoulders",
                    "confidence": 0.65,
                    "signal": "bearish",
                }

        return None

    def _detect_breakout(self, prices: List[float]) -> Optional[Dict]:
        """Detect support/resistance breakout"""
        if len(prices) < 50:
            return None

        recent = prices[-50:]
        resistance = max(recent[:-5])
        support = min(recent[:-5])
        current = prices[-1]

        # Breakout above resistance
        if current > resistance * 1.02:
            return {
                "pattern": "resistance_breakout",
                "confidence": 0.75,
                "signal": "bullish",
            }

        # Breakdown below support
        if current < support * 0.98:
            return {
                "pattern": "support_breakdown",
                "confidence": 0.75,
                "signal": "bearish",
            }

        return None

    def calibrate_prediction(
        self, raw_prediction: float, historical_accuracy: float
    ) -> float:
        """
        Calibrate prediction based on historical accuracy

        Args:
            raw_prediction: Raw model output
            historical_accuracy: Historical model accuracy

        Returns:
            Calibrated prediction
        """
        # Shrink extreme predictions based on accuracy
        if historical_accuracy < 0.6:
            # Low accuracy: be more conservative
            calibrated = raw_prediction * 0.5
        elif historical_accuracy > 0.75:
            # High accuracy: trust the model more
            calibrated = raw_prediction * 1.2
        else:
            calibrated = raw_prediction

        # Keep prediction in valid range
        return max(-1.0, min(1.0, calibrated))

    def get_prediction_metrics(self) -> Dict[str, Any]:
        """Get current prediction metrics"""
        return {
            "model_weights": self.model_weights.copy(),
            "model_accuracy": self.accuracy_by_model.copy(),
            "market_regime": self.market_regime,
            "total_predictions": len(self.prediction_history),
            "avg_accuracy": sum(self.accuracy_by_model.values())
            / len(self.accuracy_by_model),
        }


def test_enhanced_predictor():
    """Test the enhanced predictor"""
    predictor = EnhancedPredictor()

    # Test regime detection
    price_history = [100 + i * 0.5 + (i % 5) for i in range(50)]
    regime = predictor.detect_market_regime(price_history)
    print(f"Detected regime: {regime}")

    # Test pattern detection
    patterns = predictor.detect_patterns(price_history)
    print(f"Detected patterns: {patterns}")

    # Test prediction with confidence
    features = [0.1, 0.2, 0.3, 0.4, 0.5]
    models = {"lstm": None, "transformer": None}
    pred, conf = predictor.predict_with_confidence(features, models)
    print(f"Prediction: {pred:.4f}, Confidence: {conf:.2f}")

    # Test metrics
    print("\nPrediction Metrics:")
    metrics = predictor.get_prediction_metrics()
    for key, value in metrics.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    test_enhanced_predictor()
