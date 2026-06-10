import tensorflow as tf
import librosa
import numpy as np
import json

# 1. コード名リスト (index.json) の読み込み
with open('index.json', 'r', encoding='utf-8') as f:
    chord_map = json.load(f)

# 2. 学習済みモデル (saved_model.pbがあるフォルダ) の読み込み
# フォルダ名を 'chord_model' と仮定します（フォルダの中に pb ファイルがある状態）
model_path = './' 
model = tf.saved_model.load(model_path)
infer = model.signatures["serving_default"]

def predict_chord(audio_path):
    # 3. 音声ファイルの読み込みと前処理
    # AIモデルが期待するサンプリングレート（一般的に16000Hzや22050Hz）に合わせる必要があります
    y, sr = librosa.load(audio_path, sr=22050)
    
    # ここで音声を短い時間（フレーム）ごとに区切って解析します
    # 本来はモデルの入力形状(shape)に合わせる必要がありますが、まずは一例として全体を解析
    # librosa.feature.melspectrogram などを使って特徴量を作ることが多いです
    
    # --- 注意 ---
    # モデルによって入力データの形（スペクトログラムの種類など）が厳密に決まっています。
    # 以下のコードは「読み込みに成功した後の推論のイメージ」です。
    
    # 4. 推論の実行 (AIにデータを渡す)
    # input_tensor = tf.convert_to_tensor(your_processed_data, dtype=tf.float32)
    # predictions = infer(input_tensor)
    
    # 5. 結果の表示
    # 予測されたID（例: 2）を chord_map[str(id)] で「C」などの文字列に変換します
    print("解析が完了しました。")

# 実行
# predict_chord('test_audio.mp3')