from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager

import config
from analysis.models import TrackAnalysis


def get_connection() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        with open(config.SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """schema.sqlの CREATE TABLE IF NOT EXISTS では追従できない、既存DBへのカラム追加。"""
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(tracks)")}
    if "genre_source" not in existing_columns:
        conn.execute("ALTER TABLE tracks ADD COLUMN genre_source TEXT NOT NULL DEFAULT 'auto'")
    if "genre_features_json" not in existing_columns:
        conn.execute("ALTER TABLE tracks ADD COLUMN genre_features_json TEXT")
    if "genres_json" not in existing_columns:
        conn.execute("ALTER TABLE tracks ADD COLUMN genres_json TEXT")

    # 既存行はgenre(主ジャンル)から単一要素の配列として導出できる(音声の再解析は不要)。
    rows = conn.execute(
        "SELECT id, genre FROM tracks WHERE genres_json IS NULL AND genre IS NOT NULL"
    ).fetchall()
    for row in rows:
        conn.execute(
            "UPDATE tracks SET genres_json = ? WHERE id = ?",
            (json.dumps([row["genre"]]), row["id"]),
        )


@contextmanager
def transaction():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def insert_track_full(
    conn: sqlite3.Connection,
    *,
    identifier: str,
    title: str | None,
    source_type: str,
    source_youtube_url: str | None,
    source_filename: str | None,
    audio_path: str,
    result: TrackAnalysis,
) -> int:
    """解析結果をtracks/sectionsに書き込む。

    identifierがすでに存在する場合は削除してから入れ直す(再解析の上書き)。
    呼び出し側でトランザクション(db.transaction())を張ること。
    """
    conn.execute("DELETE FROM tracks WHERE identifier = ?", (identifier,))

    beats = result.beats
    beats_json = json.dumps({
        "times": beats.times,
        "rms": beats.rms,
        "centroid": beats.centroid,
        "vocal_presence": beats.vocal_presence,
        "drum_fill": beats.drum_fill,
    })

    genre_source = "user" if result.genre.source == "hint" else "auto"

    cur = conn.execute(
        """
        INSERT INTO tracks (
            identifier, title, source_type, source_youtube_url, source_filename,
            audio_path, duration_sec, trim_offset_sec, beats_per_bar, tempo_bpm,
            key_name, key_camelot, key_confidence,
            genre, genre_confidence, genre_scores_json, genre_source, genre_features_json, genres_json,
            beats_json, chord_labels_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            identifier, title, source_type, source_youtube_url, source_filename,
            audio_path, result.duration_sec, result.trim_offset_sec,
            result.beats_per_bar, result.tempo_bpm,
            result.key.key_name, result.key.camelot, result.key.confidence,
            result.genre.genre, result.genre.confidence,
            json.dumps(result.genre.scores), genre_source,
            json.dumps(result.genre.features_used),
            json.dumps([result.genre.genre]),
            beats_json, json.dumps(result.chord_labels),
        ),
    )
    track_id = cur.lastrowid

    for idx, section in enumerate(result.sections):
        _insert_section(conn, track_id, idx, section)

    return track_id


def _insert_section(conn: sqlite3.Connection, track_id: int, idx: int, section) -> None:
    conn.execute(
        """
        INSERT INTO sections (
            track_id, idx, label, start_sec, end_sec, duration_sec,
            start_bar, end_bar, mean_rms, mean_centroid, confidence,
            vocal_presence, chord_progression_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            track_id, idx, section.label, section.start_sec, section.end_sec,
            section.duration_sec, section.start_bar, section.end_bar,
            section.mean_rms, section.mean_centroid, section.confidence,
            section.vocal_presence, json.dumps(section.chord_progression),
        ),
    )


def update_track_rhythm(conn: sqlite3.Connection, track_id: int, result: TrackAnalysis) -> None:
    """再解析結果のうち、テンポ・ビート・小節・セクションだけを既存トラックに反映する。

    ジャンル(genre/genres_json/genre_source/genre_confidence/genre_features_json)や
    key_* はユーザーの修正を保持するため上書きしない。idも変えない。
    """
    beats = result.beats
    beats_json = json.dumps({
        "times": beats.times, "rms": beats.rms, "centroid": beats.centroid,
        "vocal_presence": beats.vocal_presence, "drum_fill": beats.drum_fill,
    })
    conn.execute(
        "UPDATE tracks SET tempo_bpm = ?, beats_per_bar = ?, beats_json = ?, chord_labels_json = ? WHERE id = ?",
        (result.tempo_bpm, result.beats_per_bar, beats_json, json.dumps(result.chord_labels), track_id),
    )
    conn.execute("DELETE FROM sections WHERE track_id = ?", (track_id,))
    for idx, section in enumerate(result.sections):
        _insert_section(conn, track_id, idx, section)


def get_track(conn: sqlite3.Connection, track_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()


def delete_track(conn: sqlite3.Connection, track_id: int) -> sqlite3.Row | None:
    """トラックを削除する。sectionsはFK ON DELETE CASCADEで自動削除される。

    削除した行(なければNone)を返す。呼び出し側が音声ファイル等の物理削除に使う。
    """
    row = conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
    if row is None:
        return None
    conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
    return row


def list_tracks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM tracks ORDER BY created_at DESC").fetchall()


def get_sections(conn: sqlite3.Connection, track_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM sections WHERE track_id = ? ORDER BY idx", (track_id,)
    ).fetchall()


def get_section(conn: sqlite3.Connection, section_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()


def list_confirmed_genre_examples(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """ユーザーが確認/修正したジャンルを持つトラックの (genre, 特徴量) 一覧。KNN分類の訓練データ。"""
    return conn.execute(
        "SELECT genre, genre_features_json FROM tracks"
        " WHERE genre_source = 'user' AND genre_features_json IS NOT NULL"
    ).fetchall()


def set_track_tempo(conn: sqlite3.Connection, track_id: int, bpm: float) -> None:
    """ユーザーによるBPM手動上書き。自動検出が三連系等で外れた場合の安全網。"""
    conn.execute("UPDATE tracks SET tempo_bpm = ? WHERE id = ?", (bpm, track_id))


def set_track_genres(conn: sqlite3.Connection, track_id: int, genres: list[str]) -> None:
    """ユーザーによるジャンル修正/確認。genresの先頭が主ジャンル(DJ時に採用される値)になる。

    以後このトラックの主ジャンルはKNN分類の訓練データになる。
    """
    conn.execute(
        "UPDATE tracks SET genre = ?, genres_json = ?, genre_source = 'user', genre_confidence = 1.0 WHERE id = ?",
        (genres[0], json.dumps(genres), track_id),
    )


def list_sections_with_track_info(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """ライブラリ全体のセクションを、親トラックの情報と結合して返す(セクション単位の類似度計算用)。"""
    return conn.execute(
        """
        SELECT
            s.id AS section_id, s.track_id AS track_id, s.idx AS section_idx,
            s.label AS section_label, s.start_sec AS start_sec, s.end_sec AS end_sec,
            s.duration_sec AS duration_sec, s.mean_rms AS mean_rms,
            s.mean_centroid AS mean_centroid, s.vocal_presence AS vocal_presence,
            t.title AS track_title, t.genre AS genre, t.tempo_bpm AS tempo_bpm,
            t.key_camelot AS key_camelot
        FROM sections s JOIN tracks t ON t.id = s.track_id
        ORDER BY s.track_id, s.idx
        """
    ).fetchall()
