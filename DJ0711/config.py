from pathlib import Path

BASE_DIR = Path(__file__).parent

DB_PATH = BASE_DIR / "data" / "dj0711.sqlite3"
SCHEMA_PATH = BASE_DIR / "schema.sql"
STORAGE_AUDIO_DIR = BASE_DIR / "storage" / "audio"
STORAGE_MATCHED_DIR = BASE_DIR / "storage" / "matched"  # ハーモニックミキシング補正後クリップのキャッシュ

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
# GENRE_PROFILESの全ジャンルのtempoレンジ(60-200、Vocaloidが上限)と合わせている。
TEMPO_TYPICAL_MIN = 60
TEMPO_TYPICAL_MAX = 200

# 三連系(3:2)補正を発動する閾値。duple(2倍/0.5倍)の畳み込みでは、真のBPMの2/3で
# 誤検出される三連系のズレ(例: 137→91, 140→94)を復元できない。畳み込みの勝者wに対し
# 1.5倍テンポの生強度が (この比 × wの生強度) 以上なら、1.5wを採用する。
# 実測での分離は明確(補正すべき曲=1.08〜1.21、維持すべき曲=0.58〜0.77)。
TEMPO_TRIPLE_RATIO_THRESHOLD = 1.0
