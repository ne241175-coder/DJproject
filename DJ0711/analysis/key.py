from __future__ import annotations

import numpy as np

from analysis.models import KeyResult

# Krumhansl & Kessler (1982) キープロファイル。index 0 = C ... 11 = B
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# 標準Camelot Wheel(C Major=8B, A Minor=8Aを基準に5度圏で構築)
CAMELOT_MAJOR = {
    0: "8B", 7: "9B", 2: "10B", 9: "11B", 4: "12B", 11: "1B",
    6: "2B", 1: "3B", 8: "4B", 3: "5B", 10: "6B", 5: "7B",
}
CAMELOT_MINOR = {
    9: "8A", 4: "9A", 11: "10A", 6: "11A", 1: "12A", 8: "1A",
    3: "2A", 10: "3A", 5: "4A", 0: "5A", 7: "6A", 2: "7A",
}


def detect_key(chroma: np.ndarray) -> KeyResult:
    """曲全体平均のクロマベクトルと24キープロファイルの相関から調を推定する。

    Args:
        chroma: shape (12, n_frames) のクロマ行列(ビート同期済みでも生でも可)
    """
    vec = chroma.mean(axis=1)
    if np.std(vec) < 1e-9:
        # 無音等でクロマが定数の場合は相関計算不能なため、確信度0で仮の調を返す
        return KeyResult(key_name="C Major", camelot=CAMELOT_MAJOR[0], confidence=0.0)

    best_corr, best_tonic, best_mode = -np.inf, 0, "major"
    for tonic in range(12):
        for mode, profile in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
            rotated = np.roll(profile, tonic)
            corr = np.corrcoef(vec, rotated)[0, 1]
            if np.isfinite(corr) and corr > best_corr:
                best_corr, best_tonic, best_mode = corr, tonic, mode

    key_name = f"{PITCH_NAMES[best_tonic]} {'Major' if best_mode == 'major' else 'Minor'}"
    camelot = (CAMELOT_MAJOR if best_mode == "major" else CAMELOT_MINOR)[best_tonic]
    return KeyResult(key_name=key_name, camelot=camelot, confidence=float(best_corr))


def camelot_to_position(camelot: str) -> tuple[int, str]:
    """"8B" -> (8, "B") のようにCamelot表記を分解する(類似度計算用、Phase Bで使用)。"""
    letter = camelot[-1]
    number = int(camelot[:-1])
    return number, letter
