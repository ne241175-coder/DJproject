PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tracks (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    identifier          TEXT NOT NULL UNIQUE,       -- サーバー生成スラッグ
    title               TEXT,
    source_type         TEXT NOT NULL CHECK (source_type IN ('youtube','upload')),
    source_youtube_url  TEXT,
    source_filename     TEXT,
    audio_path          TEXT NOT NULL,              -- storage/audio/ 配下の相対パス(再生用)
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    analysis_version    INTEGER NOT NULL DEFAULT 1,

    duration_sec        REAL NOT NULL,
    trim_offset_sec     REAL NOT NULL DEFAULT 0.0,
    beats_per_bar       INTEGER NOT NULL DEFAULT 4,

    tempo_bpm           REAL NOT NULL,

    key_name            TEXT,                       -- 例: "C Major"
    key_camelot         TEXT,                       -- 例: "8B"
    key_confidence      REAL,

    genre               TEXT,
    genre_confidence    REAL,
    genre_scores_json   TEXT,
    genre_source        TEXT NOT NULL DEFAULT 'auto',  -- 'auto'(自動推定) / 'user'(ヒント指定または後からの修正)
    genre_features_json TEXT,                          -- KNN比較用の特徴量(tempo/chroma_var/rms_var/centroid_mean/zcr_mean)
    genres_json         TEXT,                          -- 複数ジャンルタグ(JSON配列、先頭=主ジャンル=genreカラムと同じ値)

    beats_json          TEXT NOT NULL,               -- {times, rms, centroid, vocal_presence, drum_fill}
    chord_labels_json   TEXT
);

CREATE TABLE IF NOT EXISTS sections (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id                INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    idx                     INTEGER NOT NULL,
    label                   TEXT NOT NULL,
    start_sec               REAL NOT NULL,
    end_sec                 REAL NOT NULL,
    duration_sec            REAL NOT NULL,
    start_bar               INTEGER NOT NULL,
    end_bar                 INTEGER NOT NULL,
    mean_rms                REAL,
    mean_centroid           REAL,
    confidence              REAL,
    vocal_presence          REAL,
    chord_progression_json  TEXT,
    UNIQUE(track_id, idx)
);

CREATE INDEX IF NOT EXISTS idx_sections_track_id ON sections(track_id);
CREATE INDEX IF NOT EXISTS idx_tracks_genre ON tracks(genre);
