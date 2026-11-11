# DJ0711

自動でDJの下準備をしてくれるローカルWebアプリ。

## セットアップ

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

システム側に `ffmpeg` が必要です(`brew install ffmpeg`)。

## Phase A 動作確認

```bash
source venv/bin/activate
python scripts/verify_local_track.py "/Users/otsu/Desktop/project/resouce/月を見つけた人 - ikomai.mp3"
```
