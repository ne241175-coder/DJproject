"""Phase B動作確認用の使い捨てテストデータ投入スクリプト。

実音源が1曲しかない状態では類似度/ジャンルネットワークのテストにならないため、
複数ジャンル・BPM・Keyを持つ合成トラックをDBへ直接INSERTする。
本番コードではなく、検証専用。実行後は scripts/cleanup_test_tracks.py 等で削除する想定。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import db
from analysis.models import BeatFeatures, GenreResult, KeyResult, TrackAnalysis

FIXTURES = [
    # (identifier, title, genre, tempo, camelot, key_name, energy_mean_level)
    ("seed-house-1", "Seed House A", "Rock", 128.0, "8B", "C Major", 0.20),
    ("seed-house-2", "Seed House B", "Rock", 126.0, "9B", "G Major", 0.18),
    ("seed-jazz-1", "Seed Jazz A", "Jazz", 100.0, "5A", "F Minor", 0.08),
    ("seed-rap-1", "Seed Rap A", "Rap", 90.0, "2A", "D Minor", 0.12),
    ("seed-latin-1", "Seed Latin A", "Latin", 96.0, "5A", "C Minor", 0.15),
]


def make_fake_analysis(tempo: float, camelot: str, key_name: str, genre: str, energy_level: float) -> TrackAnalysis:
    n_beats = 200
    times = [i * 0.5 for i in range(n_beats)]
    rms = [energy_level + 0.02 * ((i % 8) / 8.0) for i in range(n_beats)]
    centroid = [2000.0 for _ in range(n_beats)]
    vocal = [0.4 for _ in range(n_beats)]
    fill = [0.0 for _ in range(n_beats)]

    return TrackAnalysis(
        duration_sec=100.0,
        trim_offset_sec=0.0,
        beats_per_bar=4,
        tempo_bpm=tempo,
        key=KeyResult(key_name=key_name, camelot=camelot, confidence=0.9),
        genre=GenreResult(genre=genre, confidence=0.9, scores={genre: 0.9}, features_used={}),
        sections=[],
        beats=BeatFeatures(times=times, rms=rms, centroid=centroid, vocal_presence=vocal, drum_fill=fill),
        chord_labels=["C"] * n_beats,
    )


def main() -> None:
    db.init_db()
    with db.transaction() as conn:
        for identifier, title, genre, tempo, camelot, key_name, energy_level in FIXTURES:
            result = make_fake_analysis(tempo, camelot, key_name, genre, energy_level)
            track_id = db.insert_track_full(
                conn,
                identifier=identifier,
                title=title,
                source_type="upload",
                source_youtube_url=None,
                source_filename=None,
                audio_path=f"storage/audio/{identifier}.mp3",
                result=result,
            )
            print(f"inserted {identifier} -> track_id={track_id}")


if __name__ == "__main__":
    main()
