"""既存の全トラックを保存済み音声から再解析し、テンポ・ビート・セクションを更新する。

BPM検出アルゴリズムを改善したとき等に、既存データへ反映するためのスクリプト。
- 対象は storage/audio/ の保存済み(トリム済み)音声。idは変えずその場で更新する。
- ジャンル(genre/genres_json/genre_source/genre_confidence/genre_features_json)と
  key_* はユーザーの修正を保持するため上書きしない(db.update_track_rhythm がテンポ系だけ更新)。

使い方:
    python scripts/reanalyze_tracks.py            # 全トラック
    python scripts/reanalyze_tracks.py 15 16 17   # id指定
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
import db
from analysis import pipeline


def main() -> None:
    target_ids = {int(a) for a in sys.argv[1:]} if len(sys.argv) > 1 else None

    with db.transaction() as conn:
        tracks = db.list_tracks(conn)

    for t in tracks:
        if target_ids is not None and t["id"] not in target_ids:
            continue
        audio_path = config.BASE_DIR / t["audio_path"]
        if not audio_path.exists():
            print(f"id{t['id']:>3} 音声が見つかりません: {audio_path} — スキップ")
            continue

        workdir = Path(tempfile.mkdtemp(prefix="dj0711_reanalyze_"))
        try:
            result, _ = pipeline.analyze_track(
                audio_path, workdir, identifier=t["identifier"], genre_hint=None
            )
            with db.transaction() as conn:
                db.update_track_rhythm(conn, t["id"], result)
            print(f"id{t['id']:>3} {repr(t['title'])[:28]:<28} BPM {t['tempo_bpm']:6.1f} → {result.tempo_bpm:6.1f}  "
                  f"(sections={len(result.sections)})")
        finally:
            import shutil
            shutil.rmtree(workdir, ignore_errors=True)

    print("再解析が完了しました。")


if __name__ == "__main__":
    main()
