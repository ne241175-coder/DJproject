from __future__ import annotations

import numpy as np

from analysis.models import GenreResult

# ジャンルごとの (tempo, spectral centroid, chroma分散, rms分散) の範囲。
# すべて暫定値であり、実データが溜まり次第チューニングする前提のプレースホルダー
# (旧プロトタイプのGENRE_PROFILESと同じ思想: 学習済みモデルへの置き換えを見込む)。
GENRE_PROFILES: dict[str, dict[str, tuple[float, float]]] = {
    "Jazz":     {"tempo": (80, 140),  "centroid": (1500, 3000), "chroma_var": (0.03, 0.10), "rms_var": (0.02, 0.08)},
    "Classic":  {"tempo": (60, 140),  "centroid": (1000, 2500), "chroma_var": (0.04, 0.12), "rms_var": (0.03, 0.12)},
    "Rock":     {"tempo": (110, 140), "centroid": (2200, 4000), "chroma_var": (0.03, 0.10), "rms_var": (0.02, 0.08)},
    "MathRock": {"tempo": (130, 180), "centroid": (2500, 4500), "chroma_var": (0.05, 0.12), "rms_var": (0.02, 0.07)},
    "Rap":      {"tempo": (70, 100),  "centroid": (1000, 2200), "chroma_var": (0.02, 0.07), "rms_var": (0.01, 0.05)},
    "Latin":    {"tempo": (90, 130),  "centroid": (2000, 4000), "chroma_var": (0.02, 0.08), "rms_var": (0.02, 0.07)},
    "Jpop":     {"tempo": (100, 130), "centroid": (2200, 4200), "chroma_var": (0.02, 0.08), "rms_var": (0.01, 0.06)},
    "Funk":     {"tempo": (95, 115),  "centroid": (1800, 3200), "chroma_var": (0.02, 0.09), "rms_var": (0.01, 0.05)},
    "Fusion":   {"tempo": (90, 160),  "centroid": (2000, 4000), "chroma_var": (0.04, 0.11), "rms_var": (0.02, 0.09)},
}

CONFIDENCE_FALLBACK_THRESHOLD = 0.3


def _range_score(value: float, rng: tuple[float, float]) -> float:
    """レンジの中点で1.0、端で0.0になるよう線形に減衰するスコア。"""
    lo, hi = rng
    mid = (lo + hi) / 2
    width = (hi - lo) / 2
    if width <= 0:
        return 0.0
    dist = abs(value - mid) / width
    return float(np.clip(1 - dist, 0.0, 1.0))


def classify_genre(
    tempo_bpm: float, chroma: np.ndarray, centroid: np.ndarray, rms: np.ndarray, genre_hint: str | None = None
) -> GenreResult:
    chroma_var = float(np.var(chroma))
    rms_var = float(np.var(rms))
    centroid_mean = float(np.mean(centroid))

    features_used = {
        "tempo": tempo_bpm,
        "chroma_var": chroma_var,
        "rms_var": rms_var,
        "centroid_mean": centroid_mean,
    }

    scores: dict[str, float] = {}
    for genre, profile in GENRE_PROFILES.items():
        s_tempo = _range_score(tempo_bpm, profile["tempo"])
        s_centroid = _range_score(centroid_mean, profile["centroid"])
        s_chroma = _range_score(chroma_var, profile["chroma_var"])
        s_rms = _range_score(rms_var, profile["rms_var"])
        scores[genre] = round((s_tempo + s_centroid + s_chroma + s_rms) / 4.0, 3)

    best_genre = max(scores, key=scores.get)
    best_confidence = scores[best_genre]

    if best_confidence < CONFIDENCE_FALLBACK_THRESHOLD:
        if genre_hint and genre_hint in GENRE_PROFILES:
            return GenreResult(genre=genre_hint, confidence=best_confidence, scores=scores, features_used=features_used)
        return GenreResult(genre="Unknown", confidence=best_confidence, scores=scores, features_used=features_used)

    return GenreResult(genre=best_genre, confidence=best_confidence, scores=scores, features_used=features_used)
