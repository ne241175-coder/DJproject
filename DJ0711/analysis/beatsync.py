from __future__ import annotations

import librosa
import numpy as np


def beat_sync(
    feature_matrix: np.ndarray, beat_times: np.ndarray, sr: int, track_end: float
) -> tuple[np.ndarray, np.ndarray]:
    """フレーム単位の特徴量をビート境界で平均集約する純粋関数。

    旧プロトタイプでは `self._sync_edges` という隠れた共有状態を介して
    off-by-oneバグを踏んだ経緯があるため、ここでは synced と edges を
    常にペアで返し、呼び出し側が自分で対応関係を再構築しなくて済むようにする。

    Args:
        feature_matrix: shape (..., n_frames) の特徴量行列 (例: chroma, rms, centroid)
        beat_times: 秒単位のビート時刻配列 (長さ n_beats)
        sr: サンプリングレート
        track_end: 曲の終端時刻(秒)

    Returns:
        synced: shape (..., n_beats+1) に集約された特徴量
        edges: 長さ n_beats+2 の単調増加な境界時刻配列
               (0, beat_times[0..n-1], track_end)。
               synced[..., i] は区間 [edges[i], edges[i+1]) に対応する。
    """
    beat_frames = librosa.time_to_frames(np.asarray(beat_times, dtype=float), sr=sr)
    synced = librosa.util.sync(feature_matrix, beat_frames, aggregate=np.mean, pad=True)

    edges = np.concatenate(([0.0], np.asarray(beat_times, dtype=float), [float(track_end)]))
    for i in range(1, len(edges)):
        if edges[i] <= edges[i - 1]:
            edges[i] = edges[i - 1] + 1e-6

    if synced.shape[-1] != len(edges) - 1:
        raise AssertionError(
            f"beat_sync: synced列数({synced.shape[-1]}) != edges長-1({len(edges) - 1})"
        )

    return synced, edges


def segment_midtimes(edges: np.ndarray) -> np.ndarray:
    """各区間の中央時刻(可視化・デバッグ用)。"""
    return (edges[:-1] + edges[1:]) / 2.0
