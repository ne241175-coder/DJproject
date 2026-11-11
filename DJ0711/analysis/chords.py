from __future__ import annotations

import numpy as np

PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def build_chord_templates() -> tuple[np.ndarray, list[str]]:
    """12根音 x {長三和音, 短三和音} = 24種類のコードテンプレートを作る。

    このコード検出は「曲のKey」を表すものではなく、構造検出(繰り返しセクションの
    検出・コード変化に基づく境界ノベルティ)のための内部信号としてのみ使う。
    """
    templates = np.zeros((24, 12))
    names: list[str] = []
    for root in range(12):
        major = np.zeros(12)
        for interval in (0, 4, 7):
            major[(root + interval) % 12] = 1.0
        templates[root] = major / np.linalg.norm(major)
        names.append(PITCH_NAMES[root])

        minor = np.zeros(12)
        for interval in (0, 3, 7):
            minor[(root + interval) % 12] = 1.0
        templates[12 + root] = minor / np.linalg.norm(minor)
        names.append(f"{PITCH_NAMES[root]}m")
    return templates, names


def detect_chords(chroma: np.ndarray) -> tuple[list[str], np.ndarray]:
    """ビート同期済みchroma (12, n_beats) から、ビートごとのコードラベルを推定する。

    Returns:
        chord_labels: 長さn_beatsのコード名リスト
        confidence: 各ビートでの最良テンプレートとのコサイン類似度
    """
    templates, names = build_chord_templates()
    n_beats = chroma.shape[1]
    try:
        norms = np.linalg.norm(chroma, axis=0, keepdims=True)
        norms[norms < 1e-9] = 1e-9
        chroma_n = chroma / norms
        sims = chroma_n.T @ templates.T  # (n_beats, 24)
        best_idx = np.argmax(sims, axis=1)
        labels = [names[i] for i in best_idx]
        confidence = sims[np.arange(n_beats), best_idx]
        return labels, confidence
    except Exception:
        return ["Unknown"] * n_beats, np.zeros(n_beats)


def chord_sequence_match_ratio(seq_a: list[str], seq_b: list[str]) -> float:
    """2つのコード進行がどれだけ一致するか(短い方の長さに正規化)。"""
    if not seq_a or not seq_b:
        return 0.0
    n = min(len(seq_a), len(seq_b))
    matches = sum(1 for i in range(n) if seq_a[i] == seq_b[i])
    return matches / n
