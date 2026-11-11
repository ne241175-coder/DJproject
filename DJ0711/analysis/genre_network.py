from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from analysis.similarity import GENRE_WEIGHTS, TrackFeatures, _bpm_distance, _camelot_distance

# ネットワーク上で線を描くジャンル間類似度の下限。これ以下(70%以下)の組み合わせは
# 「近い曲がない」とみなしエッジを引かない。選曲時のジャンル間距離計算(genre_distance_lookup)
# には影響させない(あくまで描画エッジのフィルタ)。
NETWORK_MIN_SIMILARITY = 0.70


@dataclass
class GenreCentroid:
    genre: str
    track_count: int
    tempo_bpm: float
    camelot_angle: float
    energy_mean: float
    energy_std: float


def build_genre_centroids(features: list[TrackFeatures]) -> dict[str, GenreCentroid]:
    """曲が1曲以上あるジャンルについてのみ、特徴量の重心を作る。"""
    groups: dict[str, list[TrackFeatures]] = {}
    for f in features:
        groups.setdefault(f.genre, []).append(f)

    centroids: dict[str, GenreCentroid] = {}
    for genre, members in groups.items():
        tempo = sum(m.tempo_bpm for m in members) / len(members)
        # Camelot角度は単純平均だと0/2π境界で破綻するため、sin/cosの循環平均を取る
        sin_sum = sum(math.sin(m.camelot_angle) for m in members)
        cos_sum = sum(math.cos(m.camelot_angle) for m in members)
        angle = math.atan2(sin_sum, cos_sum) % (2 * math.pi)
        energy_mean = sum(m.energy_mean for m in members) / len(members)
        energy_std = sum(m.energy_std for m in members) / len(members)
        centroids[genre] = GenreCentroid(
            genre=genre, track_count=len(members), tempo_bpm=tempo,
            camelot_angle=angle, energy_mean=energy_mean, energy_std=energy_std,
        )
    return centroids


def _centroid_distance(a: GenreCentroid, b: GenreCentroid) -> float:
    d_bpm = _bpm_distance(a.tempo_bpm, b.tempo_bpm)
    d_key = _camelot_distance(a.camelot_angle, b.camelot_angle)
    d_energy = (abs(a.energy_mean - b.energy_mean) + abs(a.energy_std - b.energy_std)) / 2.0
    w = GENRE_WEIGHTS
    return w["bpm"] * d_bpm + w["key"] * d_key + w["energy"] * d_energy


def build_genre_network(features: list[TrackFeatures]) -> tuple[dict, Callable[[str, str], float]]:
    """ジャンルノード+エッジのネットワーク定義と、ジャンル間距離を引けるlookup関数を返す。

    曲が0件のジャンルはノードとして現れない(エラーにはしない)。
    """
    centroids = build_genre_centroids(features)
    genres = list(centroids.keys())

    nodes = [{"genre": g, "track_count": centroids[g].track_count} for g in genres]

    edges = []
    for i in range(len(genres)):
        for j in range(i + 1, len(genres)):
            a, b = centroids[genres[i]], centroids[genres[j]]
            dist = _centroid_distance(a, b)
            similarity = 1.0 / (1.0 + dist)
            if similarity <= NETWORK_MIN_SIMILARITY:
                continue  # 近い曲がない組み合わせは線を繋がない
            edges.append({
                "genre_a": genres[i],
                "genre_b": genres[j],
                "distance": round(dist, 4),
                "similarity": round(similarity, 4),
            })

    def genre_distance_lookup(genre_a: str, genre_b: str) -> float:
        if genre_a not in centroids or genre_b not in centroids:
            return 1.0
        return _centroid_distance(centroids[genre_a], centroids[genre_b])

    return {"nodes": nodes, "edges": edges}, genre_distance_lookup
