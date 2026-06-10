import os
import librosa
from yt_dlp import YoutubeDL

# 1. 設定とURLの指定
video_url = "https://youtu.be/J0ben1SI4QY"  # 解析したいYouTubeのURL
output_filename = "Madhope"                  # 保存するファイル名（拡張子除く）

# 2. yt-dlpを使ってYouTubeから音声だけをダウンロード
ydl_opts = {
    'format': 'bestaudio/best',  # 最高音質の音声をダウンロード
    'outtmpl': output_filename,  # 出力ファイル名
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3', # mp3形式に変換
        'preferredquality': '192',
    }],
}

print("🎵 YouTubeから音声をダウンロード中...")
with YoutubeDL(ydl_opts) as ydl:
    ydl.download([video_url])

# ダウンロードされたファイル名（拡張子を追加）
audio_path = f"{output_filename}.mp3"

# 3. librosaを使ってBPMを検出
print("🔍 BPMを検出中...")
if os.path.exists(audio_path):
    # 音声ファイルの読み込み（sr=Noneで元のサンプリングレートを維持）
    y, sr = librosa.load(audio_path, sr=None)
    
    # beat_track関数でBPM（tempo）を計算
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    
    # 結果の表示（配列の最初の要素 [0] を取り出して丸める）
    print("\n" + "="*30)
    print(f"📊 検出されたBPM: {round(float(tempo[0]), 2)}")
    print("="*30)
else:
    print("エラー: 音声ファイルが見つかりませんでした。")
