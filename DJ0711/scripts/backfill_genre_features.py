"""既存トラック(genre_features_json未設定)の特徴量を音声から再計算して埋めるワンタイムスクリプト。

genre_features_jsonカラムは今回新設したため、既存トラックには入っていない。
ジャンル自体は上書きせず、KNN分類の訓練データとして使えるよう特徴量だけを補完する。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import librosa
import numpy as np

import config
import db
from analysis import tempo as tempo_module
from analysis import timbre


def main() -> None:
    with db.transaction() as conn:
        tracks = db.list_tracks(conn)
        targets = [t for t in tracks if not t["genre_features_json"]]

        if not targets:
            print("対象なし(すべてのトラックにgenre_features_jsonが設定済み)。")
            return

        for track in targets:
            audio_path = config.BASE_DIR / track["audio_path"]
            print(f"track {track['id']} ({track['title']}): {audio_path}")

            y, sr = librosa.load(audio_path, sr=config.SAMPLE_RATE, mono=True)
            duration_sec = len(y) / sr

            tempo_bpm, onset_env = tempo_module.detect_tempo(y, sr)
            beat_times = tempo_module.detect_beats(y, sr, tempo_bpm, onset_env, duration_sec)

            chroma, _edges = timbre.extract_chroma(y, sr, beat_times, duration_sec)
            rms, _ = timbre.extract_rms(y, sr, beat_times, duration_sec)
            centroid, _ = timbre.extract_centroid(y, sr, beat_times, duration_sec)
            zcr, _ = timbre.extract_zcr(y, sr, beat_times, duration_sec)

            features_used = {
                "tempo": float(tempo_bpm),
                "chroma_var": float(np.var(chroma)),
                "rms_var": float(np.var(rms)),
                "centroid_mean": float(np.mean(centroid)),
                "zcr_mean": float(np.mean(zcr)),
            }
            print(f"  features: {features_used}")

            conn.execute(
                "UPDATE tracks SET genre_features_json = ? WHERE id = ?",
                (json.dumps(features_used), track["id"]),
            )

    print(f"\n{len(targets)}件を更新しました。")


if __name__ == "__main__":
    main()
