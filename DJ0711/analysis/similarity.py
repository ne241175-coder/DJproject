from __future__ import annotations

import json
import math
from dataclasses import dataclass

import numpy as np

from analysis.key import camelot_to_position

# 曲間距離の重み。合計1.0になるよう管理する(チューニングしやすいよう一箇所に集約)。
TRACK_WEIGHTS = {"bpm": 0.3, "key": 0.3, "energy": 0.2, "genre": 0.2}
# ジャンル間(重心同士)の距離の重み。genre項は存在しない(ノード自体がジャンルのため)。
GENRE_WEIGHTS = {"bpm": 0.45, "key": 0.35, "energy": 0.20}


@dataclass
class TrackFeatures:
    track_id: int
    title: str | None
    genre: str
    tempo_bpm: float
    camelot_angle: float     # Camelot Wheel(24分割)上の角度(ラジアン, 0-2π)
    energy_mean: float       # ライブラリ内でmin-max正規化した値(0-1)
    energy_std: float        # 同上
    energy_peak_pos: float   # 曲内でのエネルギーピーク位置(0-1、曲の長さで正規化済み)


def _camelot_angle(camelot: str | None) -> float:
    """"8B"などのCamelot表記を24分割ホイール上の角度に変換する。"""
    if not camelot:
        return 0.0
    number, letter = camelot_to_position(camelot)
    position_index = (number - 1) * 2 + (0 if letter == "B" else 1)
    return position_index / 24.0 * 2 * math.pi


def _normalize(arr: np.ndarray) -> np.ndarray:
    lo, hi = float(arr.min()), float(arr.max())
    if hi - lo < 1e-9:
        return np.zeros_like(arr)
    return (arr - lo) / (hi - lo)


def build_track_features(track_rows: list) -> list[TrackFeatures]:
    """DBのtracks行群から、ライブラリ全体を基準に正規化した特徴量一覧を作る。

    energy_mean/energy_stdは曲の絶対的な音量(マスタリング差)に影響されるため、
    「現在ライブラリにある曲群の中で」min-max正規化する(絶対スケールでの比較は
    今のところ行わない、精度は今後の課題)。
    """
    raw = []
    for row in track_rows:
        beats = json.loads(row["beats_json"])
        rms = np.array(beats.get("rms", []), dtype=float)
        times = np.array(beats.get("times", []), dtype=float)
        duration = row["duration_sec"] or 1.0

        energy_mean = float(np.mean(rms)) if len(rms) else 0.0
        energy_std = float(np.std(rms)) if len(rms) else 0.0
        if len(rms):
            peak_pos = float(times[int(np.argmax(rms))] / duration)
        else:
            peak_pos = 0.5

        raw.append({
            "track_id": row["id"],
            "title": row["title"],
            "genre": row["genre"] or "Unknown",
            "tempo_bpm": row["tempo_bpm"],
            "camelot_angle": _camelot_angle(row["key_camelot"]),
            "energy_mean": energy_mean,
            "energy_std": energy_std,
            "energy_peak_pos": peak_pos,
        })

    if not raw:
        return []

    means_n = _normalize(np.array([r["energy_mean"] for r in raw]))
    stds_n = _normalize(np.array([r["energy_std"] for r in raw]))

    return [
        TrackFeatures(
            track_id=r["track_id"],
            title=r["title"],
            genre=r["genre"],
            tempo_bpm=r["tempo_bpm"],
            camelot_angle=r["camelot_angle"],
            energy_mean=float(means_n[i]),
            energy_std=float(stds_n[i]),
            energy_peak_pos=r["energy_peak_pos"],
        )
        for i, r in enumerate(raw)
    ]


def _bpm_distance(a: float, b: float) -> float:
    """半テンポ/倍テンポを互換とみなすBPM距離。0=完全一致。"""
    if a <= 0 or b <= 0:
        return 1.0
    diffs = (abs(a - b), abs(a - 2 * b), abs(a - b / 2))
    return min(diffs) / max(a, b)


def _camelot_distance(angle_a: float, angle_b: float) -> float:
    """Camelot Wheel上のcircular distance。0=完全一致(隣接/平行調ほど小さい)、1=正反対。"""
    diff = abs(angle_a - angle_b) % (2 * math.pi)
    diff = min(diff, 2 * math.pi - diff)
    return diff / math.pi


def _energy_distance(a: TrackFeatures, b: TrackFeatures) -> float:
    d_mean = abs(a.energy_mean - b.energy_mean)
    d_std = abs(a.energy_std - b.energy_std)
    d_peak = abs(a.energy_peak_pos - b.energy_peak_pos)
    return (d_mean + d_std + d_peak) / 3.0


def track_distance(a: TrackFeatures, b: TrackFeatures, genre_distance_lookup=None) -> float:
    """2曲間の距離(0=完全一致、値が小さいほど近い)。"""
    d_bpm = _bpm_distance(a.tempo_bpm, b.tempo_bpm)
    d_key = _camelot_distance(a.camelot_angle, b.camelot_angle)
    d_energy = _energy_distance(a, b)

    if a.genre == b.genre:
        d_genre = 0.0
    elif genre_distance_lookup is not None:
        d_genre = genre_distance_lookup(a.genre, b.genre)
    else:
        d_genre = 1.0

    w = TRACK_WEIGHTS
    return w["bpm"] * d_bpm + w["key"] * d_key + w["energy"] * d_energy + w["genre"] * d_genre


def similarity_score(distance: float) -> float:
    """距離をUI表示向けの0-1(1に近いほど似ている)スコアへ変換する。"""
    return 1.0 / (1.0 + distance)
