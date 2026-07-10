from pathlib import Path

BASE_DIR = Path(__file__).parent

DB_PATH = BASE_DIR / "data" / "dj0711.sqlite3"
SCHEMA_PATH = BASE_DIR / "schema.sql"
STORAGE_AUDIO_DIR = BASE_DIR / "storage" / "audio"

SAMPLE_RATE = 44100
AUDIO_BITRATE = "320k"
BEATS_PER_BAR = 4

SILENCE_THRESH_DB = -45.0
SILENCE_CHUNK_MS = 20
MAX_TRIM_RATIO = 0.4  # 前後トリムが曲全体の40%を超える場合はトリムをスキップ

TEMPO_MIN_BPM = 40
TEMPO_MAX_BPM = 220
TEMPO_FALLBACK_BPM = 120.0

# オクターブ誤り(倍テンポ/半テンポ)補正で「最終的に報告してよい」BPM帯。
# GENRE_PROFILESの全ジャンルのtempoレンジ(60-180)と合わせている。
TEMPO_TYPICAL_MIN = 60
TEMPO_TYPICAL_MAX = 180
