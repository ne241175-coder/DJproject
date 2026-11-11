from __future__ import annotations

import librosa
import numpy as np

import config


def _strength_at(target_bpm: float, bpms: np.ndarray, strengths: np.ndarray) -> float:
    """bpms配列上でtarget_bpmに最も近いビンの強度を返す。範囲外なら0。"""
    if target_bpm < bpms.min() - 1 or target_bpm > bpms.max() + 1:
        return 0.0
    return float(strengths[np.argmin(np.abs(bpms - target_bpm))])


def _detect_tempo_octave_corrected(onset_env: np.ndarray, sr: int) -> float:
    """テンポグラム(自己相関)による、事前分布に頼らないBPM推定。

    librosa.beat.beat_track単体は既定のstart_bpm=120という事前分布に
    引っ張られやすく、倍テンポ/半テンポを誤検出しがち(実測で確認済み:
    ある曲では真のBPM(~95)よりも、prior中心の120に近い129.2の方が
    強く選ばれてしまった)。
    そこで、まず事前分布の影響を受けない生のテンポグラム強度を求め、
    各候補についてその2倍・0.5倍のビンの強度も合算してから
    (オクターブ違いの一致を「畳み込む」)、GENRE_PROFILESのレンジと
    揃えた「典型的なDJテンポ帯」(TEMPO_TYPICAL_MIN-MAX)の中で
    最も強い候補を採用する。
    """
    hop_length = 512
    tempogram = librosa.feature.tempogram(onset_envelope=onset_env, sr=sr, hop_length=hop_length)
    mean_strength = tempogram.mean(axis=1)
    bpms = librosa.tempo_frequencies(tempogram.shape[0], sr=sr, hop_length=hop_length)

    valid = np.isfinite(bpms) & (bpms >= config.TEMPO_MIN_BPM) & (bpms <= config.TEMPO_MAX_BPM)
    cand_bpms, cand_strength = bpms[valid], mean_strength[valid]

    reportable = (cand_bpms >= config.TEMPO_TYPICAL_MIN) & (cand_bpms <= config.TEMPO_TYPICAL_MAX)
    if not np.any(reportable):
        raise ValueError("典型的なテンポ帯に候補が見つかりません")

    report_bpms = cand_bpms[reportable]
    folded = np.array([
        _strength_at(b, cand_bpms, cand_strength)
        + _strength_at(b * 2, cand_bpms, cand_strength)
        + _strength_at(b / 2, cand_bpms, cand_strength)
        for b in report_bpms
    ])
    winner = float(report_bpms[np.argmax(folded)])

    # 三連系(3:2)補正。duple畳み込みだけだと、真のBPMの2/3で刻む三連系の曲
    # (137→91, 140→94 等)は低い方が勝ってしまう。勝者の1.5倍テンポが典型帯にあり、
    # その生強度が勝者の生強度以上(=真の拍がそこに確かにある)なら、そちらを採用する。
    triple = winner * 1.5
    if (config.TEMPO_TYPICAL_MIN <= triple <= config.TEMPO_TYPICAL_MAX
            and _strength_at(triple, cand_bpms, cand_strength)
                >= config.TEMPO_TRIPLE_RATIO_THRESHOLD * _strength_at(winner, cand_bpms, cand_strength)):
        winner = triple

    return winner


def detect_tempo(y: np.ndarray, sr: int) -> tuple[float, np.ndarray]:
    """BPMとonset包絡線を検出する。範囲外・失敗時はフォールバックする。"""
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    try:
        tempo = _detect_tempo_octave_corrected(onset_env, sr)
    except Exception:
        try:
            tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
            tempo = float(np.atleast_1d(tempo)[0])
            if not (config.TEMPO_MIN_BPM <= tempo <= config.TEMPO_MAX_BPM):
                raise ValueError(f"tempo out of range: {tempo}")
        except Exception:
            tempo = config.TEMPO_FALLBACK_BPM
    return tempo, onset_env


def detect_beats(y: np.ndarray, sr: int, tempo: float, onset_env: np.ndarray, duration: float) -> np.ndarray:
    """ビート時刻配列(秒)を検出する。ビート数が少なすぎる場合は等間隔グリッドにフォールバックする。"""
    try:
        _, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, bpm=tempo)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        if len(beat_times) < 4:
            raise ValueError("too few beats detected")
    except Exception:
        step = 60.0 / tempo
        n = max(int(duration / step), 4)
        beat_times = np.arange(n) * step
    return beat_times


def detect_downbeats(beat_times: np.ndarray, onset_env: np.ndarray, sr: int, beats_per_bar: int = config.BEATS_PER_BAR) -> np.ndarray:
    """全曲を通した固定位相の簡易ダウンビート検出(4/4拍子を仮定)。

    onset_envのフレームレートに合わせてbeat_timesをフレームインデックスへ変換し、
    beats_per_bar通りの位相それぞれで平均onset強度を比較し、最も強い位相を採用する。
    madmom等の高度な小節推定器を使わない簡易版。
    """
    if len(beat_times) < beats_per_bar:
        return beat_times

    frame_idx = librosa.time_to_frames(beat_times, sr=sr)
    frame_idx = np.clip(frame_idx, 0, len(onset_env) - 1)

    best_phase, best_score = 0, -np.inf
    for phase in range(beats_per_bar):
        idx = frame_idx[phase::beats_per_bar]
        if len(idx) == 0:
            continue
        score = float(np.mean(onset_env[idx]))
        if score > best_score:
            best_score, best_phase = score, phase

    return beat_times[best_phase::beats_per_bar]
