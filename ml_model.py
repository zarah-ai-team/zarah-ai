"""ml_model.py
Simple cost prediction stub. Tries to load a persisted sklearn model from models/cost_model.pkl.
If missing, uses a simple rule-based estimator and trains a tiny model on synthetic data.
"""
import os
import pickle
import numpy as np

MODEL_PATH = os.path.join("models", "cost_model.pkl")


class CostModel:
    def __init__(self):
        self.model = None
        self._load_or_train()

    def _load_or_train(self):
        try:
            with open(MODEL_PATH, "rb") as f:
                self.model = pickle.load(f)
        except Exception:
            # Create a very small synthetic dataset and train a linear regressor
            try:
                from sklearn.linear_model import LinearRegression
            except Exception:
                self.model = None
                return

            # features: duration, pax, budget, event_code, hotel_code
            X = []
            y = []
            for d in [1, 3, 5, 7]:
                for p in [1, 2, 4]:
                    for b in [50, 100, 200]:
                        for e in [0, 1, 2]:
                            for h in [0, 1, 2]:
                                X.append([d, p, b, e, h])
                                # synthetic target: base cost = days * pax * budget * factor
                                factor = 1 + 0.1 * e + 0.2 * h
                                y.append(d * p * b * factor)
            X = np.array(X)
            y = np.array(y)

            model = LinearRegression()
            model.fit(X, y)
            self.model = model
            # Persist model if models dir exists
            try:
                os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
                with open(MODEL_PATH, "wb") as f:
                    pickle.dump(self.model, f)
            except Exception:
                pass

    def predict_cost(self, features: dict) -> float:
        """Return predicted total cost (not per person)."""
        vec = features.get("vector")
        if vec is None:
            return 0.0
        # vector: duration, pax, budget, ev, hv
        X = vec.reshape(1, -1)
        if self.model:
            try:
                pred = float(self.model.predict(X)[0])
                return max(0.0, pred)
            except Exception:
                pass

        # fallback simple rule
        duration, pax, budget, ev, hv = vec
        factor = 1 + 0.1 * ev + 0.2 * hv
        return float(duration * pax * budget * factor)
