"""Phase A 動作確認用スクリプト。

Flask/スレッドを経由せず、pipeline.analyze_track() を直接呼び出して
DBに書き込むところまでを最速で確認する。

使い方:
    python scripts/verify_local_track.py "<音声ファイルのパス>"
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import db
from analysis import pipeline


def main() -> None:
    if len(sys.argv) < 2:
        print("使い方: python scripts/verify_local_track.py <音声ファイルのパス>")
        sys.exit(1)

    audio_path = Path(sys.argv[1])
    if not audio_path.exists():
        print(f"ファイルが見つかりません: {audio_path}")
        sys.exit(1)

    identifier = "verify-" + audio_path.stem.replace(" ", "_")[:30]
    workdir = Path(tempfile.mkdtemp(prefix="dj0711_verify_"))

    print(f"解析中: {audio_path}")
    result, trimmed_path = pipeline.analyze_track(audio_path, workdir, identifier, genre_hint=None)

    print(f"tempo_bpm = {result.tempo_bpm:.2f}")
    print(f"key = {result.key.key_name} ({result.key.camelot}), confidence={result.key.confidence:.3f}")
    print(f"genre = {result.genre.genre}, confidence={result.genre.confidence:.3f}")
    print(f"genre_scores = {result.genre.scores}")
    print(f"duration_sec = {result.duration_sec:.2f}, trim_offset_sec = {result.trim_offset_sec:.2f}")
    print(f"n_sections = {len(result.sections)}")
    for s in result.sections:
        print(f"  [{s.label}] {s.start_sec:.1f}s - {s.end_sec:.1f}s (bar {s.start_bar}-{s.end_bar}) "
              f"conf={s.confidence:.2f} vocal={s.vocal_presence:.2f}")
    n_beats = len(result.beats.times)
    print(f"n_beats(segments) = {n_beats}")
    for arr_name in ("times", "rms", "centroid", "vocal_presence", "drum_fill"):
        arr = getattr(result.beats, arr_name)
        print(f"  beats.{arr_name}: len={len(arr)}")

    db.init_db()
    import config
    config.STORAGE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    import shutil
    audio_dest = config.STORAGE_AUDIO_DIR / f"{identifier}.mp3"
    shutil.copy(trimmed_path, audio_dest)

    with db.transaction() as conn:
        track_id = db.insert_track_full(
            conn,
            identifier=identifier,
            title=audio_path.stem,
            source_type="upload",
            source_youtube_url=None,
            source_filename=audio_path.name,
            audio_path=str(audio_dest.relative_to(config.BASE_DIR)),
            result=result,
        )
    print(f"DBに保存しました: track_id={track_id}")

    shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
