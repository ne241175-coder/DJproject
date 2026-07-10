from __future__ import annotations

import librosa
import numpy as np

import config
from analysis.beatsync import beat_sync


def detect_drum_fill(y: np.ndarray, sr: int, beat_times: np.ndarray, track_end: float) -> np.ndarray:
    """パーカッシブ成分のオンセット密度が直近平均よりスパイクする箇所を「フィル」として検出する。

    フレーズ末尾のドラムフィルは構造の区切りを示す、ジャンルに依存しない有力な信号として使う。
    """
    try:
        y_perc = librosa.effects.percussive(y, margin=3.0)
        onset_env = librosa.onset.onset_strength(y=y_perc, sr=sr)
        synced, _ = beat_sync(onset_env.reshape(1, -1), beat_times, sr, track_end)
        raw_density = synced[0]

        window = max(config.BEATS_PER_BAR, 4)
        fill_score = np.zeros_like(raw_density)
        for i in range(len(raw_density)):
            lo = max(0, i - window)
            if lo == i:
                continue
            local_mean = np.mean(raw_density[lo:i])
            fill_score[i] = max(raw_density[i] - local_mean, 0.0)
        return fill_score
    except Exception:
        n_beats = len(beat_times) + 1
        return np.zeros(n_beats)
