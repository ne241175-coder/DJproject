from __future__ import annotations

import numpy as np

from analysis.models import GenreResult

# ジャンルごとの (tempo, spectral centroid, chroma分散, rms分散, zero-crossing rate) の範囲。
# 確認済みデータ(genre_source='user')が1件も無い立ち上げ時のみ使われるフォールバック
# (通常はclassify_genre_knnによる、蓄積データとの比較がジャンル推定の主経路になる)。
# すべて暫定値であり、実データが溜まり次第チューニングする前提のプレースホルダー
# (旧プロトタイプのGENRE_PROFILESと同じ思想: 学習済みモデルへの置き換えを見込む)。
# Jazz/Classic/Rock/Latin/Jpop/Funk/Fusionは実測4曲を踏まえて再調整済み。
# Kpop/Vocaloid/Electro/EDMは実データが無く、既存の推定と同水準のbest-effort値
# (Kpop: Jpopに近いが高tempo・高centroid寄り、Vocaloidはtempo/chroma_varの幅が広い、
#  Electro/EDMは打ち込み由来でrms_varが低く、EDMは4つ打ち中心のtempo帯を想定)。
GENRE_PROFILES: dict[str, dict[str, tuple[float, float]]] = {
    "Jazz":     {"tempo": (80, 140),  "centroid": (1500, 2900), "chroma_var": (0.03, 0.10), "rms_var": (0.008, 0.06), "zcr": (0.05, 0.09)},
    "Classic":  {"tempo": (60, 140),  "centroid": (1000, 2500), "chroma_var": (0.04, 0.12), "rms_var": (0.012, 0.10), "zcr": (0.02, 0.06)},
    "Rock":     {"tempo": (110, 140), "centroid": (2200, 3800), "chroma_var": (0.03, 0.10), "rms_var": (0.008, 0.08), "zcr": (0.05, 0.10)},
    "Latin":    {"tempo": (95, 125),  "centroid": (2200, 3600), "chroma_var": (0.02, 0.08), "rms_var": (0.008, 0.07), "zcr": (0.05, 0.09)},
    "Jpop":     {"tempo": (100, 130), "centroid": (2600, 4200), "chroma_var": (0.02, 0.08), "rms_var": (0.01, 0.06),  "zcr": (0.05, 0.09)},
    "Kpop":     {"tempo": (95, 130),  "centroid": (2800, 4400), "chroma_var": (0.02, 0.08), "rms_var": (0.006, 0.045), "zcr": (0.05, 0.10)},
    "Vocaloid": {"tempo": (120, 200), "centroid": (3000, 5000), "chroma_var": (0.05, 0.14), "rms_var": (0.006, 0.05), "zcr": (0.06, 0.12)},
    "Funk":     {"tempo": (95, 115),  "centroid": (1800, 3000), "chroma_var": (0.02, 0.09), "rms_var": (0.01, 0.05),  "zcr": (0.04, 0.08)},
    "Fusion":   {"tempo": (90, 160),  "centroid": (2000, 3800), "chroma_var": (0.04, 0.11), "rms_var": (0.008, 0.09), "zcr": (0.05, 0.09)},
    "Electro":  {"tempo": (118, 135), "centroid": (2500, 4500), "chroma_var": (0.02, 0.08), "rms_var": (0.004, 0.04), "zcr": (0.04, 0.09)},
    "EDM":      {"tempo": (124, 135), "centroid": (2800, 4800), "chroma_var": (0.02, 0.07), "rms_var": (0.004, 0.035), "zcr": (0.04, 0.09)},
}

CONFIDENCE_FALLBACK_THRESHOLD = 0.3
HINT_CONFIDENCE = 1.0
KNN_K = 3
KNN_MIN_EXAMPLES_FOR_FULL_CONFIDENCE = 3
_KNN_DISTANCE_EPSILON = 1e-6

_GENRE_HINT_LOOKUP = {name.lower(): name for name in GENRE_PROFILES}
_FEATURE_KEYS = ("tempo", "chroma_var", "rms_var", "centroid_mean", "zcr_mean")


def _normalize_genre_hint(genre_hint: str | None) -> str | None:
    if not genre_hint:
        return None
    return _GENRE_HINT_LOOKUP.get(genre_hint.strip().lower())


def _range_score(value: float, rng: tuple[float, float]) -> float:
    """レンジの中点で1.0、端で0.0になるよう線形に減衰するスコア。"""
    lo, hi = rng
    mid = (lo + hi) / 2
    width = (hi - lo) / 2
    if width <= 0:
        return 0.0
    dist = abs(value - mid) / width
    return float(np.clip(1 - dist, 0.0, 1.0))


def _classify_genre_rule_based(features_used: dict[str, float]) -> GenreResult:
    tempo_bpm = features_used["tempo"]
    chroma_var = features_used["chroma_var"]
    rms_var = features_used["rms_var"]
    centroid_mean = features_used["centroid_mean"]
    zcr_mean = features_used["zcr_mean"]

    scores: dict[str, float] = {}
    for genre, profile in GENRE_PROFILES.items():
        s_tempo = _range_score(tempo_bpm, profile["tempo"])
        s_centroid = _range_score(centroid_mean, profile["centroid"])
        s_chroma = _range_score(chroma_var, profile["chroma_var"])
        s_rms = _range_score(rms_var, profile["rms_var"])
        s_zcr = _range_score(zcr_mean, profile["zcr"])
        scores[genre] = round((s_tempo + s_centroid + s_chroma + s_rms + s_zcr) / 5.0, 3)

    best_genre = max(scores, key=scores.get)
    best_confidence = scores[best_genre]

    if best_confidence < CONFIDENCE_FALLBACK_THRESHOLD:
        return GenreResult(genre="Unknown", confidence=best_confidence, scores=scores, features_used=features_used, source="rule")

    return GenreResult(genre=best_genre, confidence=best_confidence, scores=scores, features_used=features_used, source="rule")


def classify_genre_knn(
    features_used: dict[str, float],
    examples: list[tuple[str, dict[str, float]]],
    k: int = KNN_K,
) -> GenreResult | None:
    """確認済みデータ(examples)との比較でジャンルを推定する(k近傍法、重み付き投票)。

    examplesが空ならNone(呼び出し側がルールベースにフォールバックする)。
    特徴量ごとにスケールが大きく異なるため、examples+新規曲の範囲でmin-max正規化してから
    ユークリッド距離を計算する(analysis.similarity._normalizeと同じ考え方)。
    """
    if not examples:
        return None

    all_points = [features_used] + [f for _, f in examples]
    normalized: dict[str, list[float]] = {}
    for key in _FEATURE_KEYS:
        values = np.array([p[key] for p in all_points], dtype=float)
        lo, hi = float(values.min()), float(values.max())
        if hi - lo < 1e-9:
            normalized[key] = [0.0] * len(values)
        else:
            normalized[key] = list((values - lo) / (hi - lo))

    query_vec = np.array([normalized[key][0] for key in _FEATURE_KEYS])
    example_vecs = [
        np.array([normalized[key][i + 1] for key in _FEATURE_KEYS])
        for i in range(len(examples))
    ]

    distances = [float(np.linalg.norm(query_vec - vec)) for vec in example_vecs]
    ranked = sorted(zip(distances, examples), key=lambda pair: pair[0])
    neighbors = ranked[: min(k, len(ranked))]

    weight_by_genre: dict[str, float] = {}
    for dist, (genre, _features) in neighbors:
        weight = 1.0 / (dist + _KNN_DISTANCE_EPSILON)
        weight_by_genre[genre] = weight_by_genre.get(genre, 0.0) + weight

    total_weight = sum(weight_by_genre.values())
    scores = {genre: round(w / total_weight, 3) for genre, w in weight_by_genre.items()}

    winner = max(weight_by_genre, key=weight_by_genre.get)
    vote_share = weight_by_genre[winner] / total_weight
    data_confidence_cap = min(1.0, len(examples) / KNN_MIN_EXAMPLES_FOR_FULL_CONFIDENCE)
    confidence = round(vote_share * data_confidence_cap, 3)

    return GenreResult(genre=winner, confidence=confidence, scores=scores, features_used=features_used, source="knn")


def classify_genre(
    tempo_bpm: float,
    chroma: np.ndarray,
    centroid: np.ndarray,
    rms: np.ndarray,
    zcr: np.ndarray,
    genre_hint: str | None = None,
    confirmed_examples: list[tuple[str, dict[str, float]]] | None = None,
) -> GenreResult:
    chroma_var = float(np.var(chroma))
    rms_var = float(np.var(rms))
    centroid_mean = float(np.mean(centroid))
    zcr_mean = float(np.mean(zcr))

    features_used = {
        "tempo": tempo_bpm,
        "chroma_var": chroma_var,
        "rms_var": rms_var,
        "centroid_mean": centroid_mean,
        "zcr_mean": zcr_mean,
    }

    # ユーザーが指定したヒントは、自動判定より信頼できるため最優先で採用する。
    normalized_hint = _normalize_genre_hint(genre_hint)
    if normalized_hint:
        return GenreResult(genre=normalized_hint, confidence=HINT_CONFIDENCE, scores={}, features_used=features_used, source="hint")

    # ヒントが無ければ、蓄積された確認済みデータとの比較(KNN)を優先する。
    # 「間違って推定→ユーザーが訂正→次の類似曲は正しく推定される」というループを成立させるため、
    # ルールベースとブレンドせず、データが1件でもあればKNNの結果をそのまま採用する。
    knn_result = classify_genre_knn(features_used, confirmed_examples or [])
    if knn_result is not None:
        return knn_result

    # 確認済みデータが1件も無い立ち上げ時のみ、ルールベースにフォールバックする。
    return _classify_genre_rule_based(features_used)
