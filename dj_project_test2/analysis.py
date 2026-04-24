import librosa
import numpy as np
import json
from collections import Counter

def analyze_track_stable(file_path):
    print(f"Analyzing {file_path}...")
    y, sr = librosa.load(file_path)
    y_harm = librosa.effects.hpss(y)[0]
    
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    chroma = librosa.feature.chroma_cqt(y=y_harm, sr=sr)
    beat_chroma = librosa.util.sync(chroma, beat_frames)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    labels = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    major_template = np.array([1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0])
    minor_template = np.array([1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0])
    
    raw_chords = []
    # まず1拍ごとのコードを出す
    for i in range(beat_chroma.shape[1]):
        chroma_vec = beat_chroma[:, i]
        best_score = -1
        best_label = "???"
        for root in range(12):
            score_maj = np.dot(chroma_vec, np.roll(major_template, root))
            score_min = np.dot(chroma_vec, np.roll(minor_template, root))
            if score_maj > best_score:
                best_score = score_maj
                best_label = labels[root]
            if score_min > best_score:
                best_score = score_min
                best_label = labels[root] + "m"
        raw_chords.append(best_label)

    # 【新ロジック】2拍単位で「多数決」を行い、表示を安定させる
    stable_chords = []
    window_size = 2  # ここを 4 にすると4拍単位（1小節）で固定されます
    
    for i in range(0, len(raw_chords), window_size):
        # 2拍分（または4拍分）のコードを抜き出す
        chunk = raw_chords[i : i + window_size]
        # その中で一番多いコードを採用
        most_common_chord = Counter(chunk).most_common(1)[0][0]
        
        for j in range(len(chunk)):
            if (i + j) < len(beat_times):
                stable_chords.append({
                    "time": float(beat_times[i + j]),
                    "name": most_common_chord
                })
        
    return {"bpm": round(float(tempo)), "chords": stable_chords}

# 実行部分は以前と同じ
# 2曲分実行
try:
    # ここを analyze_track_stable に書き換える
    data = {
        "trackA": analyze_track_stable("track1.mp3"),
        "trackB": analyze_track_stable("track2.mp3")
    }
    with open('analysis.json', 'w') as f:
        json.dump(data, f)
    print("--- 安定化解析が完了しました！ ---")
except Exception as e:
    print(f"An error occurred: {e}")