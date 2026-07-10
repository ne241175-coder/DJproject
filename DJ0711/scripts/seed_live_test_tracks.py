"""Phase Cのライブセッション動作確認用、使い捨てテストデータ投入スクリプト。

実際に再生できる音声が必要なため、既存の解析済みトラック(実音源)の音声ファイルを
複製し、ジャンル/BPM/Keyだけ変えたメタデータで複数トラックとして登録する
(中身の音声は同じだが、選曲UI/クロスフェード/状態遷移の配線を検証するには十分)。
本番コードではなく検証専用。
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
import db
from analysis.models import BeatFeatures, GenreResult, KeyResult, Section, TrackAnalysis

SOURCE_IDENTIFIER = "verify-月を見つけた人_-_ikomai"

VARIANTS = [
    # (identifier, title, genre, tempo, camelot, key_name)
    ("live-test-rock", "Live Test Rock", "Rock", 128.0, "8B", "C Major"),
    ("live-test-latin2", "Live Test Latin B", "Latin", 98.0, "5A", "C Minor"),
]


def main() -> None:
    db.init_db()
    with db.transaction() as conn:
        source = conn.execute(
            "SELECT * FROM tracks WHERE identifier = ?", (SOURCE_IDENTIFIER,)
        ).fetchone()
        if source is None:
            print(f"元トラック({SOURCE_IDENTIFIER})が見つかりません。先に解析を実行してください。")
            sys.exit(1)

        sections_rows = conn.execute(
            "SELECT * FROM sections WHERE track_id = ? ORDER BY idx", (source["id"],)
        ).fetchall()
        beats = json.loads(source["beats_json"])
        source_audio_path = config.BASE_DIR / source["audio_path"]

        sections = [
            Section(
                label=r["label"], start_sec=r["start_sec"], end_sec=r["end_sec"],
                start_bar=r["start_bar"], end_bar=r["end_bar"], mean_rms=r["mean_rms"],
                mean_centroid=r["mean_centroid"], confidence=r["confidence"],
                vocal_presence=r["vocal_presence"],
                chord_progression=json.loads(r["chord_progression_json"] or "[]"),
            )
            for r in sections_rows
        ]

        for identifier, title, genre, tempo, camelot, key_name in VARIANTS:
            audio_dest = config.STORAGE_AUDIO_DIR / f"{identifier}.mp3"
            shutil.copy(source_audio_path, audio_dest)

            result = TrackAnalysis(
                duration_sec=source["duration_sec"],
                trim_offset_sec=source["trim_offset_sec"],
                beats_per_bar=source["beats_per_bar"],
                tempo_bpm=tempo,
                key=KeyResult(key_name=key_name, camelot=camelot, confidence=0.9),
                genre=GenreResult(genre=genre, confidence=0.9, scores={genre: 0.9}, features_used={}),
                sections=sections,
                beats=BeatFeatures(**beats),
                chord_labels=json.loads(source["chord_labels_json"] or "[]"),
            )
            track_id = db.insert_track_full(
                conn,
                identifier=identifier,
                title=title,
                source_type="upload",
                source_youtube_url=None,
                source_filename=None,
                audio_path=str(audio_dest.relative_to(config.BASE_DIR)),
                result=result,
            )
            print(f"inserted {identifier} -> track_id={track_id}")


if __name__ == "__main__":
    main()
