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
        conn.commit()
    finally:
        conn.close()


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

    cur = conn.execute(
        """
        INSERT INTO tracks (
            identifier, title, source_type, source_youtube_url, source_filename,
            audio_path, duration_sec, trim_offset_sec, beats_per_bar, tempo_bpm,
            key_name, key_camelot, key_confidence,
            genre, genre_confidence, genre_scores_json,
            beats_json, chord_labels_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            identifier, title, source_type, source_youtube_url, source_filename,
            audio_path, result.duration_sec, result.trim_offset_sec,
            result.beats_per_bar, result.tempo_bpm,
            result.key.key_name, result.key.camelot, result.key.confidence,
            result.genre.genre, result.genre.confidence,
            json.dumps(result.genre.scores),
            beats_json, json.dumps(result.chord_labels),
        ),
    )
    track_id = cur.lastrowid

    for idx, section in enumerate(result.sections):
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

    return track_id


def get_track(conn: sqlite3.Connection, track_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()


def list_tracks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM tracks ORDER BY created_at DESC").fetchall()


def get_sections(conn: sqlite3.Connection, track_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM sections WHERE track_id = ? ORDER BY idx", (track_id,)
    ).fetchall()
