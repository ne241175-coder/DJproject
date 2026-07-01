import os
from flask import Flask, render_template, request, jsonify
import librosa
from yt_dlp import YoutubeDL

app = Flask(__name__)

import numpy as np

def calculate_genre_probabilities(y, sr, bpm):
    scores = {
        "Latin/Samba": 10,
        "Funk": 10,
        "Jazz": 10,
        "Rock": 10,
        "HipHop": 10
    }
    
    # 1. 音の「密度（1秒間にどれだけ音が鳴るか）」を解析
    # onset_peaks はドラムのキックやスネアが鳴った個数のリスト
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    peaks = librosa.util.peak_pick(onset_env, pre_max=3, post_max=3, pre_avg=3, post_avg=5, delta=0.5, wait=10)
    
    duration = librosa.get_duration(y=y, sr=sr)
    note_density = len(peaks) / duration # 1秒あたりの音符の数
    
    # 2. BPMによるベーススコアの加算
    if 120 <= bpm <= 145:
        scores["Latin/Samba"] += 40  # サンバ・ラテンの王道テンポ
        scores["Rock"] += 30
        scores["Funk"] += 20
    elif 85 <= bpm <= 115:
        scores["HipHop"] += 45       # ブーンバップやファンクの黄金テンポ
        scores["Funk"] += 40
        scores["Jazz"] += 15
    elif bpm > 145:
        scores["Jazz"] += 40         # 高速ジャズ
        scores["Rock"] += 30
    elif bpm < 85:
        scores["HipHop"] += 30       # チルなヒップホップ
        scores["Jazz"] += 30         # スロウジャズ

    # 3. 「音の密度（手数）」による決定的な分岐
    # サンバやファンクは1拍の中の手数（16分音符やシンコペーション）が多く、ロックやヒップホップは比較的シンプル
    if note_density > 3.2:
        # 音が細かくめちゃくちゃ詰まっている ＝ サンバ特有の手数の多さ、または高速ジャズ
        scores["Latin/Samba"] += 50
        scores["Jazz"] += 25
        scores["Funk"] += 15
        scores["Rock"] -= 20         # 手数が多すぎるのでストレートなロックの可能性を下げる
        scores["HipHop"] -= 30
    elif 2.2 <= note_density <= 3.2:
        # 中間の密度 ＝ ファンク特有のカッティングや、標準的なロック
        scores["Funk"] += 30
        scores["Rock"] += 25
        scores["Latin/Samba"] -= 10
    else:
        # 音の密度が低い ＝ ドラムがドッ・タッ・とシンプルに響くヒップホップやバラード
        scores["HipHop"] += 40
        scores["Rock"] += 10
        scores["Latin/Samba"] -= 30
        scores["Funk"] -= 20

    # パーセンテージ（%）に変換
    total = sum(max(0, s) for s in scores.values())
    probabilities = {genre: round((max(0, score) / total) * 100, 1) for genre, score in scores.items()}
    
    # 確率が高い順にソート
    return dict(sorted(probabilities.items(), key=lambda x: x[1], reverse=True))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json()
    video_url = data.get('url')
    output_filename = "downloaded_audio"
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_filename,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True
    }

    try:
        # 1. ダウンロード
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        
        audio_path = f"{output_filename}.mp3"
        
        # 2. BPM解析
        if os.path.exists(audio_path):
            # 音声ファイルを読み込む (y=波形データ, sr=サンプリングレート)
            y, sr = librosa.load(audio_path, sr=None)
            
            # BPMを計算
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            bpm = round(float(tempo[0]), 2)
            
            # 3. ジャンル確率計算 (引数に y, sr, bpm の3つを正しい順で渡す)
            genres = calculate_genre_probabilities(y, sr, bpm)
            
            # 後片付け（サーバーの容量圧迫を防ぐためファイル削除）
            os.remove(audio_path)
            
            # フロント（JS）にデータを返す
            return jsonify({
                "success": True,
                "bpm": bpm,
                "genres": genres
            })
        else:
            return jsonify({"success": False, "error": "ファイルが見つかりません"})
            
    except Exception as e:
        # エラーが起きたらファイルを消してから返す
        if os.path.exists(f"{output_filename}.mp3"):
            os.remove(f"{output_filename}.mp3")
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    app.run(debug=True)
