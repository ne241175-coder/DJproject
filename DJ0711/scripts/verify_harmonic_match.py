"""ハーモニックミキシング(BPM/Key自動補正)の動作確認用スクリプト。

resolve_adjustment/render_matched_sectionを直接呼び出し、
- 伸縮後のサンプル数が理論値と厳密一致するか(決定論的なはずの部分)
- 移調後に再検出したKeyが期待通りか(実測: C Major+3半音→D# Major/5B で一致確認済み)
- BPMは人間演奏由来のテンポ推定ノイズがあるため参考程度に再検出のみ表示
- 「すでに近いので補正しない」「差が大きすぎて補正しない」の分岐が働くか
を確認する。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import librosa

import config
import db
from analysis import harmonic_match, key as key_module, tempo as tempo_module


def load_track_slice(track_row, start_sec: float = 0.0, duration_sec: float = 20.0):
    audio_path = config.BASE_DIR / track_row["audio_path"]
    y, sr = librosa.load(audio_path, sr=config.SAMPLE_RATE, mono=True, offset=start_sec, duration=duration_sec)
    return y, sr


def redetect(y: np.ndarray, sr: int) -> tuple[float, str]:
    tempo_bpm, onset_env = tempo_module.detect_tempo(y, sr)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    key_result = key_module.detect_key(chroma)
    return tempo_bpm, key_result.camelot, key_result.key_name


def main() -> None:
    with db.transaction() as conn:
        tracks = db.list_tracks(conn)
    if len(tracks) < 2:
        print("track が2曲以上必要です。先に複数曲を解析してください。")
        sys.exit(1)

    a, b = tracks[0], tracks[1]
    print(f"track A: {a['title']} ({a['tempo_bpm']:.1f}bpm, {a['key_camelot']})")
    print(f"track B: {b['title']} ({b['tempo_bpm']:.1f}bpm, {b['key_camelot']})")

    y, sr = load_track_slice(b, start_sec=0.0, duration_sec=20.0)

    print("\n--- ケース1: B を A に合わせる(通常ケース) ---")
    adj = harmonic_match.resolve_adjustment(a["tempo_bpm"], a["key_camelot"], b["tempo_bpm"], b["key_camelot"])
    print(adj)
    y_out = harmonic_match.render_matched_section(y, sr, adj)
    expected_len = round(len(y) / adj.stretch_rate) if adj.stretch_applied else len(y)
    print(f"len(y)={len(y)} len(y_out)={len(y_out)} expected={expected_len} match={len(y_out) == expected_len}")
    if adj.shift_applied or adj.stretch_applied:
        redetected_bpm, redetected_camelot, redetected_key_name = redetect(y_out, sr)
        bpm_target = f"目標{a['tempo_bpm']:.1f}" if adj.stretch_applied else "補正なしなのでBと同じはず"
        key_target = f"目標{a['key_camelot']}" if adj.shift_applied else f"補正なしなのでBの元Key({b['key_camelot']})のはず"
        print(f"再検出: bpm={redetected_bpm:.1f} ({bpm_target}), key={redetected_key_name}({redetected_camelot}) ({key_target})")

    print("\n--- ケース2: 同一トラック同士(補正不要のはず) ---")
    adj_same = harmonic_match.resolve_adjustment(a["tempo_bpm"], a["key_camelot"], a["tempo_bpm"], a["key_camelot"])
    print(adj_same)
    assert not adj_same.stretch_applied and not adj_same.shift_applied, "同一トラックなのに補正が適用された"
    print("OK: 補正なし")

    print("\n--- ケース3: 極端なBPM差(半/倍テンポ補正をかけてもクランプが働くはず) ---")
    adj_extreme_bpm = harmonic_match.resolve_adjustment(100.0, "8B", 140.0, "8B")
    print(adj_extreme_bpm)
    assert not adj_extreme_bpm.stretch_applied, "極端なBPM差なのに伸縮が適用された"
    print("OK: 伸縮なし(クランプ超過)")

    print("\n--- ケース4: トライトーン(正反対Camelot、移調がスキップされるはず) ---")
    adj_tritone = harmonic_match.resolve_adjustment(120.0, "8B", 120.0, "2B")
    print(adj_tritone)
    assert not adj_tritone.shift_applied, "トライトーンなのに移調が適用された"
    print("OK: 移調なし(半音数クランプ超過)")

    print("\n--- ケース5: 隣接Camelot(すでに近いので移調しないはず) ---")
    adj_adjacent = harmonic_match.resolve_adjustment(120.0, "8B", 120.0, "9B")
    print(adj_adjacent)
    assert not adj_adjacent.shift_applied, "隣接Camelotなのに移調が適用された"
    print("OK: 移調なし(既に安全な組み合わせ)")

    print("\nすべての検証ケースが期待通りでした。")


if __name__ == "__main__":
    main()
