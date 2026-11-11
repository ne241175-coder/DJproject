from __future__ import annotations

import librosa
import numpy as np

from analysis.beatsync import beat_sync


def detect_vocal_presence(y: np.ndarray, sr: int, beat_times: np.ndarray, track_end: float) -> np.ndarray:
    """ハーモニック成分に対するpYIN有声確率から、ビートごとのボーカル存在感(0-1)を推定する。"""
    try:
        y_harmonic = librosa.effects.harmonic(y, margin=3.0)
        f0, voiced_flag, voiced_prob = librosa.pyin(
            y_harmonic,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C6"),
            sr=sr,
        )
        voiced_prob = np.nan_to_num(voiced_prob, nan=0.0)
        synced, _ = beat_sync(voiced_prob.reshape(1, -1), beat_times, sr, track_end)
        return np.clip(synced[0], 0.0, 1.0)
    except Exception:
        n_beats = len(beat_times) + 1
        return np.full(n_beats, 0.5)
