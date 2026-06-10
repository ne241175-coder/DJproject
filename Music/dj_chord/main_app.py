import tensorflow as tf
import numpy as np
import librosa
import json
from collections import Counter

# --- 1. 設定 (環境に合わせて書き換えてください) ---
MODEL_PATH = "./"
JSON_PATH = "index.json"
AUDIO_FILE = "test_music.mp3" 
SR = 22050        

# --- 2. 構成音データベース ---
CHORD_DATA = {
    "C": ["C", "E", "G"], "Cm": ["C", "Eb", "G"], "C7": ["C", "E", "G", "Bb"],
    "CM7": ["C", "E", "G", "B"], "C#": ["C#", "E#", "G#"], "C#m": ["C#", "E", "G#"],
    "Db": ["Db", "F", "Ab"], "DbM7": ["Db", "F", "Ab", "C"], "D": ["D", "F#", "A"],
    "Dm": ["D", "F", "A"], "Eb": ["Eb", "G", "Bb"], "Ebm": ["Eb", "Gb", "Bb"],
    "Eb7": ["Eb", "G", "Bb", "Db"], "EbM7": ["Eb", "G", "Bb", "D"], "E": ["E", "G#", "B"],
    "Em": ["E", "G", "B"], "F": ["F", "A", "C"], "Fm": ["F", "Ab", "C"],
    "F#": ["F#", "A#", "C#"], "Gb": ["Gb", "Bb", "Db"], "G": ["G", "B", "D"],
    "Gm": ["G", "Bb", "D"], "G7": ["G", "B", "D", "F"], "Ab": ["Ab", "C", "Eb"],
    "Abm": ["Ab", "Cb", "Eb"], "AbM7": ["Ab", "C", "Eb", "G"], "A": ["A", "C#", "E"], 
    "Am": ["A", "C", "E"], "Bb": ["Bb", "D", "F"], "Bbm": ["Bb", "Db", "F"], 
    "Bb7": ["Bb", "D", "F", "Ab"], "B": ["B", "D#", "F#"], "Bm": ["B", "D", "F#"], 
    "Bdim": ["B", "D", "F"], "Cm7": ["C", "Eb", "G", "Bb"], "Bb7(13)": ["Bb", "D", "F", "Ab", "G"],
    "Gaug": ["G", "B", "D#"], "Bdim7": ["B", "D", "F", "Ab"]
}

# --- 3. ロジック関数群 ---

def get_chord_notes(chord_name):
    """コード名から構成音を引く"""
    if chord_name == "N.C." or not chord_name: return ""
    if chord_name in CHORD_DATA: return " [" + ", ".join(CHORD_DATA[chord_name]) + "]"
    # カッコなどの表記揺れを補正
    clean_name = chord_name.replace("(", "").replace(")", "").replace(" ", "")
    if clean_name in CHORD_DATA: return " [" + ", ".join(CHORD_DATA[clean_name]) + "]"
    return " [Notes unknown]"

def preprocess_adaptive(y):
    """適応的ゲイン制御 + CQT + HPSS(打楽器音分離)"""
    y = librosa.util.normalize(y)
    # 4秒ごとの局所正規化で音量の小さい箇所を底上げ
    win = SR * 4
    for i in range(0, len(y), win):
        chunk = y[i:i+win]
        if np.max(np.abs(chunk)) > 0.01:
            y[i:i+win] = chunk / np.max(np.abs(chunk))
    
    # CQT解析
    cqt = librosa.cqt(y, sr=SR, hop_length=512, fmin=librosa.note_to_hz('C1'), 
                        n_bins=252, bins_per_octave=36)
    mag = (librosa.amplitude_to_db(np.abs(cqt).T, ref=np.max) + 80) / 80
    
    # ハーモニック成分（和音成分）を強調
    D_harmonic, _ = librosa.decompose.hpss(cqt)
    harm = (librosa.amplitude_to_db(np.abs(D_harmonic).T, ref=np.max) + 80) / 80
    
    return np.stack([mag, harm], axis=-1).astype(np.float32)

def estimate_key_refined(results):
    """ルート音とMajor/Minorの組み合わせで最も多いものをキーとする"""
    valid = [c for c in results if c != "N.C."]
    if not valid: return "C", "Major"
    
    pairs = []
    for c in valid:
        r = c[:2] if len(c) > 1 and c[1] in 'b#' else c[0]
        quality = "Minor" if "m" in c and "M7" not in c else "Major"
        pairs.append((r, quality))
    
    best_pair = Counter(pairs).most_common(1)[0][0]
    return best_pair

def apply_smart_filter(raw_results):
    """推定されたキーに基づき、音楽理論的に不自然なコードを修正する"""
    estimated_root, mode = estimate_key_refined(raw_results)
    print(f"\n>>> Final Key Context Detected: {estimated_root} {mode}")
    
    roots_list = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']
    
    # モードに応じたスケール（音階）の定義
    if mode == "Major":
        scale_steps = [0, 2, 4, 5, 7, 9, 11] # Major Scale
    else:
        scale_steps = [0, 2, 3, 5, 7, 8, 10] # Natural Minor Scale
        
    try:
        key_idx = roots_list.index(estimated_root)
    except:
        key_idx = 0
        
    # 許可リスト（ダイアトニック・ルート）の作成
    allowed_roots = [roots_list[(key_idx + s) % 12] for s in scale_steps]
    
    # マイナーキー特有のドミナント進行（VやVII）を許容範囲に追加
    if mode == "Minor":
        allowed_roots.append(roots_list[(key_idx + 7) % 12]) 
        allowed_roots.append(roots_list[(key_idx + 11) % 12])

    refined = []
    for i, c in enumerate(raw_results):
        if c == "N.C.":
            refined.append(c)
            continue
        
        root = c[:2] if len(c) > 1 and c[1] in 'b#' else c[0]
        
        if root not in allowed_roots:
            # キー外の音は前後の文脈で埋める
            if 0 < i < len(raw_results) - 1:
                prev_c, next_c = raw_results[i-1], raw_results[i+1]
                if prev_c == next_c:
                    refined.append(prev_c)
                    continue
            refined.append(refined[-1] if refined else c)
        else:
            refined.append(c)

    # 最終的な平滑化フィルタ
    final = []
    win = 4
    for i in range(len(refined)):
        start, end = max(0, i-win), min(len(refined), i+win+1)
        final.append(Counter(refined[start:end]).most_common(1)[0][0])
    return final

# --- 4. メイン処理 ---

def main():
    print("--- Starting System ---")
    print("Loading AI model...")
    model = tf.saved_model.load(MODEL_PATH)
    infer = model.signatures["serving_default"]
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        labels = json.load(f)

    print(f"Loading and analyzing: {AUDIO_FILE}...")
    y, _ = librosa.load(AUDIO_FILE, sr=SR)
    features = preprocess_adaptive(y)
    seq_len = features.shape[0]

    block = 1024

    pad_len = (block - (seq_len % block)) % block

    if pad_len > 0:
        pad = np.zeros((pad_len, features.shape[1], features.shape[2]), dtype=np.float32)
        features = np.concatenate([features, pad], axis=0)

    print("Padded shape:", features.shape)

    raw_res = []

    print("AI Inference...")

    out = infer(
        input_1=tf.convert_to_tensor(features[np.newaxis, ...])
    )

    ids = out['ccf'].numpy()[0]

    for cid in ids:
        raw_res.append(labels.get(str(cid), "N.C."))

    # 理論フィルタリングの適用
    final_res = apply_smart_filter(raw_res)

    print("\n" + "="*65)
    print(f"{'Time':<10} | {'Chord Name':<18} | {'Notes'}")
    print("-" * 65)
    
    last = ""
    dur = 512 / SR
    for i, name in enumerate(final_res):
        if name != last:
            time_sec = i * dur
            ts = f"[{int(time_sec//60):02d}:{int(time_sec%60):02d}.{int((time_sec%1)*10)}]"
            print(f"{ts:<10} | {name:<18} | {get_chord_notes(name)}")
            last = name
    print("="*65)

if __name__ == "__main__":
    main()