from __future__ import annotations

from pathlib import Path

import config
from analysis import chords, drums, genre, key, structure, tempo, timbre, vocals
from analysis.beatsync import segment_midtimes
from analysis.io import preprocess
from analysis.models import BeatFeatures, TrackAnalysis


def analyze_track(
    raw_path: Path, workdir: Path, identifier: str, genre_hint: str | None = None
) -> tuple[TrackAnalysis, Path]:
    """生の音声ファイルから解析結果一式を作る。

    Returns:
        result: TrackAnalysis
        trimmed_audio_path: 前処理(無音トリム済み)後の音声ファイルパス。
                             呼び出し側(jobs.py)がstorage/audio/へコピーする。
    """
    y, sr, trim_offset_sec, trimmed_path = preprocess(raw_path, workdir, identifier)
    duration_sec = len(y) / sr

    tempo_bpm, onset_env = tempo.detect_tempo(y, sr)
    beat_times = tempo.detect_beats(y, sr, tempo_bpm, onset_env, duration_sec)

    chroma, edges = timbre.extract_chroma(y, sr, beat_times, duration_sec)
    rms, _ = timbre.extract_rms(y, sr, beat_times, duration_sec)
    centroid, _ = timbre.extract_centroid(y, sr, beat_times, duration_sec)

    key_result = key.detect_key(chroma)
    chord_labels, _chord_confidence = chords.detect_chords(chroma)
    vocal_presence = vocals.detect_vocal_presence(y, sr, beat_times, duration_sec)
    fill_score = drums.detect_drum_fill(y, sr, beat_times, duration_sec)

    genre_result = genre.classify_genre(tempo_bpm, chroma, centroid, rms, genre_hint)

    sections = structure.detect_structure(
        chroma=chroma,
        rms=rms,
        centroid=centroid,
        vocal_presence=vocal_presence,
        fill_score=fill_score,
        chord_labels=chord_labels,
        edges=edges,
        beats_per_bar=config.BEATS_PER_BAR,
    )

    beat_features = BeatFeatures(
        times=[float(t) for t in segment_midtimes(edges)],
        rms=[float(v) for v in rms.ravel()],
        centroid=[float(v) for v in centroid.ravel()],
        vocal_presence=[float(v) for v in vocal_presence],
        drum_fill=[float(v) for v in fill_score],
    )

    result = TrackAnalysis(
        duration_sec=float(duration_sec),
        trim_offset_sec=float(trim_offset_sec),
        beats_per_bar=config.BEATS_PER_BAR,
        tempo_bpm=float(tempo_bpm),
        key=key_result,
        genre=genre_result,
        sections=sections,
        beats=beat_features,
        chord_labels=chord_labels,
    )
    return result, trimmed_path
