from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np

from analysis.key import camelot_to_pitch_class, camelot_to_position
from analysis.similarity import _bpm_distance, _camelot_angle, _camelot_distance

# BPMの伸縮率をこの範囲(±25%)を超える場合は伸縮しない(音質劣化が目立つため)。
BPM_RATE_CLAMP = 0.25
# 移調幅をこの半音数を超える場合は移調しない。実データ検証により、この値は
# トライトーン(正反対のCamelot、+6半音)のケースだけを除外することが確認済み。
MAX_SEMITONE_SHIFT = 4
# この値以下のCamelot距離(完全一致/平行調/隣接)は、既存の類似度モデル上
# 「すでに相性が良い」とみなされる組み合わせのため、あえて移調しない。
CAMELOT_SAFE_THRESHOLD = 0.2

_RATE_EPSILON = 0.01  # これ未満のずれは「補正不要」として扱う


@dataclass
class HarmonicAdjustment:
    stretch_rate: float          # 1.0 = 補正なし(time_stretchのrate引数にそのまま渡せる)
    effective_source_bpm: float  # 半/倍テンポ補正後のsource側実効BPM
    stretch_applied: bool
    semitone_shift: int          # 0 = 補正なし(pitch_shiftのn_steps引数にそのまま渡せる)
    shift_applied: bool
    reason: str


def resolve_adjustment(
    current_bpm: float,
    current_camelot: str | None,
    source_bpm: float,
    source_camelot: str | None,
) -> HarmonicAdjustment:
    """現在再生中(current)に、遷移元(source)のセクションを合わせるための調整量を求める。

    音声I/Oは行わない純粋な計算のみ。
    """
    reasons: list[str] = []

    candidates = (source_bpm, source_bpm * 2, source_bpm / 2)
    effective_source_bpm = min(candidates, key=lambda b: abs(b - current_bpm))
    rate = current_bpm / effective_source_bpm if effective_source_bpm > 0 else 1.0

    stretch_applied = _RATE_EPSILON < abs(rate - 1.0) <= BPM_RATE_CLAMP
    if not stretch_applied:
        if abs(rate - 1.0) > BPM_RATE_CLAMP:
            reasons.append(f"BPM差が大きすぎるため伸縮なし(必要rate={rate:.3f})")
        rate = 1.0

    semitone_shift = 0
    shift_applied = False
    if current_camelot and source_camelot:
        dist = _camelot_distance(_camelot_angle(current_camelot), _camelot_angle(source_camelot))
        if dist > CAMELOT_SAFE_THRESHOLD:
            current_number, _ = camelot_to_position(current_camelot)
            _, source_letter = camelot_to_position(source_camelot)
            source_pitch_class = camelot_to_pitch_class(source_camelot)
            # incoming(source)側のモード(メジャー/マイナー)は保ったまま、
            # Camelotナンバーだけcurrent側に合わせたターゲットを求める
            # (「同ナンバー・別レター」は既存のCamelot距離モデルでも安全な組み合わせのため)。
            target_pitch_class = camelot_to_pitch_class(f"{current_number}{source_letter}")
            diff = (target_pitch_class - source_pitch_class) % 12
            if diff > 6:
                diff -= 12
            if abs(diff) <= MAX_SEMITONE_SHIFT:
                semitone_shift = diff
                shift_applied = semitone_shift != 0
            else:
                reasons.append(f"Key差が大きすぎるため移調なし(必要shift={diff})")

    if not reasons:
        reasons.append("補正適用" if (stretch_applied or shift_applied) else "すでに近いため補正不要")

    return HarmonicAdjustment(
        stretch_rate=rate,
        effective_source_bpm=effective_source_bpm,
        stretch_applied=stretch_applied,
        semitone_shift=semitone_shift,
        shift_applied=shift_applied,
        reason="; ".join(reasons),
    )


def render_matched_section(y: np.ndarray, sr: int, adjustment: HarmonicAdjustment) -> np.ndarray:
    """調整不要な処理は呼ばない(無駄にPhase Vocoderを通さない)。"""
    out = y
    if adjustment.shift_applied:
        out = librosa.effects.pitch_shift(out, sr=sr, n_steps=adjustment.semitone_shift)
    if adjustment.stretch_applied:
        out = librosa.effects.time_stretch(out, rate=adjustment.stretch_rate)
    return out
