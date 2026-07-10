from __future__ import annotations

import librosa
import numpy as np

from analysis.beatsync import beat_sync


def _safe_extract(fn, fallback_shape: tuple[int, ...]) -> np.ndarray:
    try:
        feat = fn()
        if not np.all(np.isfinite(feat)):
            raise ValueError("non-finite values in feature")
        return feat
    except Exception:
        return np.zeros(fallback_shape)


def extract_chroma(y: np.ndarray, sr: int, beat_times: np.ndarray, track_end: float) -> tuple[np.ndarray, np.ndarray]:
    raw = _safe_extract(lambda: librosa.feature.chroma_cqt(y=y, sr=sr), (12, 1))
    return beat_sync(raw, beat_times, sr, track_end)


def extract_rms(y: np.ndarray, sr: int, beat_times: np.ndarray, track_end: float) -> tuple[np.ndarray, np.ndarray]:
    raw = _safe_extract(lambda: librosa.feature.rms(y=y), (1, 1))
    return beat_sync(raw, beat_times, sr, track_end)


def extract_centroid(y: np.ndarray, sr: int, beat_times: np.ndarray, track_end: float) -> tuple[np.ndarray, np.ndarray]:
    raw = _safe_extract(lambda: librosa.feature.spectral_centroid(y=y, sr=sr), (1, 1))
    return beat_sync(raw, beat_times, sr, track_end)


def normalize(x: np.ndarray) -> np.ndarray:
    """0-1のmin-max正規化(定数配列の場合はゼロ埋め)。"""
    lo, hi = np.min(x), np.max(x)
    if hi - lo < 1e-12:
        return np.zeros_like(x)
    return (x - lo) / (hi - lo)
