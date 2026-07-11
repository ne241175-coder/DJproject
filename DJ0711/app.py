from __future__ import annotations

import tempfile
from pathlib import Path

import librosa
import soundfile
from flask import Flask, jsonify, render_template, request, send_from_directory

import config
import db
import jobs
from analysis import genre, genre_network, harmonic_match, similarity

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True  # 開発中、テンプレート編集をリロード無しで反映する

UPLOAD_DIR = Path(tempfile.gettempdir()) / "dj0711_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.route("/", methods=["GET"])
def index():
    with db.transaction() as conn:
        tracks = db.list_tracks(conn)
    return render_template("index.html", tracks=tracks)


@app.route("/live", methods=["GET"])
def live():
    return render_template("live.html")


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    youtube_url = (request.form.get("youtube_url") or "").strip() or None
    genre_hint = (request.form.get("genre_hint") or "").strip() or None
    uploaded_path = None

    file = request.files.get("file")
    if file and file.filename:
        uploaded_path = UPLOAD_DIR / file.filename
        file.save(uploaded_path)

    if not youtube_url and not uploaded_path:
        return jsonify({"error": "youtube_url または file のいずれかを指定してください。"}), 400

    try:
        job_id = jobs.start_analyze_job(
            youtube_url=youtube_url, uploaded_path=uploaded_path, genre_hint=genre_hint
        )
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 409
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>", methods=["GET"])
def api_status(job_id: str):
    job = jobs.get_job_status(job_id)
    if job is None:
        return jsonify({"error": "そのジョブは見つかりません"}), 404
    return jsonify({
        "status": job["status"],
        "logs": job["logs"],
        "track_id": job["track_id"],
        "error": job["error"],
    })


@app.route("/api/tracks", methods=["GET"])
def api_tracks():
    with db.transaction() as conn:
        tracks = db.list_tracks(conn)
    return jsonify([dict(t) for t in tracks])


@app.route("/api/tracks/<int:track_id>", methods=["GET"])
def api_track_detail(track_id: int):
    with db.transaction() as conn:
        track = db.get_track(conn, track_id)
        if track is None:
            return jsonify({"error": "見つかりません"}), 404
        sections = db.get_sections(conn, track_id)
    return jsonify({
        "track": dict(track),
        "sections": [dict(s) for s in sections],
    })


@app.route("/api/tracks/<int:track_id>/audio", methods=["GET"])
def api_track_audio(track_id: int):
    with db.transaction() as conn:
        track = db.get_track(conn, track_id)
    if track is None:
        return jsonify({"error": "見つかりません"}), 404
    audio_path = config.BASE_DIR / track["audio_path"]
    return send_from_directory(audio_path.parent, audio_path.name)


@app.route("/api/tracks/<int:track_id>/genre", methods=["POST"])
def api_update_track_genre(track_id: int):
    payload = request.get_json(silent=True) or {}
    new_genres = payload.get("genres")
    if not isinstance(new_genres, list) or not new_genres:
        return jsonify({"error": "genres は1件以上のジャンル名の配列で指定してください。"}), 400
    if len(set(new_genres)) != len(new_genres):
        return jsonify({"error": "同じジャンルを複数指定することはできません。"}), 400
    unknown = [g for g in new_genres if g not in genre.GENRE_PROFILES]
    if unknown:
        return jsonify({"error": f"不明なジャンルです: {', '.join(unknown)}"}), 400

    with db.transaction() as conn:
        track = db.get_track(conn, track_id)
        if track is None:
            return jsonify({"error": "見つかりません"}), 404
        db.set_track_genres(conn, track_id, new_genres)

    return jsonify({
        "id": track_id, "genre": new_genres[0], "genres": new_genres, "genre_source": "user",
    })


@app.route("/api/tracks/<int:track_id>/tempo", methods=["POST"])
def api_update_track_tempo(track_id: int):
    payload = request.get_json(silent=True) or {}
    bpm = payload.get("bpm")
    try:
        bpm = float(bpm)
    except (TypeError, ValueError):
        return jsonify({"error": "bpm は数値で指定してください。"}), 400
    if not (config.TEMPO_MIN_BPM <= bpm <= config.TEMPO_MAX_BPM):
        return jsonify({"error": f"bpm は {config.TEMPO_MIN_BPM}〜{config.TEMPO_MAX_BPM} の範囲で指定してください。"}), 400

    with db.transaction() as conn:
        track = db.get_track(conn, track_id)
        if track is None:
            return jsonify({"error": "見つかりません"}), 404
        db.set_track_tempo(conn, track_id, bpm)

    return jsonify({"id": track_id, "tempo_bpm": bpm})


@app.route("/api/tracks/<int:track_id>", methods=["DELETE"])
def api_delete_track(track_id: int):
    with db.transaction() as conn:
        sections = db.get_sections(conn, track_id)
        section_ids = [s["id"] for s in sections]
        deleted = db.delete_track(conn, track_id)
        if deleted is None:
            return jsonify({"error": "見つかりません"}), 404
        audio_path = config.BASE_DIR / deleted["audio_path"]

    # 物理ファイルの後始末(DBトランザクションの外で。失敗しても致命的ではない)
    audio_path.unlink(missing_ok=True)
    matched_dir = config.STORAGE_MATCHED_DIR
    if matched_dir.exists():
        for wav in matched_dir.glob(f"*_{track_id}.wav"):  # このトラックを基準に合わせた補正クリップ
            wav.unlink(missing_ok=True)
        for sid in section_ids:  # このトラックのセクションを素材にした補正クリップ
            for wav in matched_dir.glob(f"{sid}_*.wav"):
                wav.unlink(missing_ok=True)

    return jsonify({"deleted": track_id})


def _load_features() -> list[similarity.TrackFeatures]:
    with db.transaction() as conn:
        rows = db.list_tracks(conn)
    return similarity.build_track_features(rows)


@app.route("/api/network", methods=["GET"])
def api_network():
    features = _load_features()
    network, _ = genre_network.build_genre_network(features)
    return jsonify(network)


@app.route("/api/genre/<genre>/tracks", methods=["GET"])
def api_genre_tracks(genre: str):
    relative_to = request.args.get("relative_to", type=int)
    features = _load_features()
    by_id = {f.track_id: f for f in features}

    if relative_to is None or relative_to not in by_id:
        return jsonify({"error": "relative_to (有効なtrack_id) を指定してください。"}), 400

    _, genre_lookup = genre_network.build_genre_network(features)
    current = by_id[relative_to]
    candidates = [f for f in features if f.genre == genre and f.track_id != relative_to]

    ranked = sorted(candidates, key=lambda f: similarity.track_distance(current, f, genre_lookup))
    return jsonify([
        {
            "track_id": f.track_id,
            "title": f.title,
            "genre": f.genre,
            "tempo_bpm": f.tempo_bpm,
            "similarity": round(
                similarity.similarity_score(similarity.track_distance(current, f, genre_lookup)), 4
            ),
        }
        for f in ranked
    ])


@app.route("/api/nearest-track", methods=["GET"])
def api_nearest_track():
    from_id = request.args.get("from", type=int)
    genre_filter = request.args.get("genre") or None

    features = _load_features()
    by_id = {f.track_id: f for f in features}
    if from_id is None or from_id not in by_id:
        return jsonify({"error": "from (有効なtrack_id) を指定してください。"}), 400

    _, genre_lookup = genre_network.build_genre_network(features)
    current = by_id[from_id]
    candidates = [f for f in features if f.track_id != from_id]
    if genre_filter:
        candidates = [f for f in candidates if f.genre == genre_filter]

    if not candidates:
        return jsonify({"track": None})

    best = min(candidates, key=lambda f: similarity.track_distance(current, f, genre_lookup))
    dist = similarity.track_distance(current, best, genre_lookup)
    return jsonify({
        "track_id": best.track_id,
        "title": best.title,
        "genre": best.genre,
        "tempo_bpm": best.tempo_bpm,
        "similarity": round(similarity.similarity_score(dist), 4),
    })


def _load_section_features() -> list[similarity.SectionFeatures]:
    with db.transaction() as conn:
        rows = db.list_sections_with_track_info(conn)
    return similarity.build_section_features(rows)


@app.route("/api/genre/<genre>/sections", methods=["GET"])
def api_genre_sections(genre: str):
    relative_to = request.args.get("relative_to", type=int)
    section_features = _load_section_features()
    by_id = {f.section_id: f for f in section_features}

    if relative_to is None or relative_to not in by_id:
        return jsonify({"error": "relative_to (有効なsection_id) を指定してください。"}), 400

    track_features = _load_features()
    _, genre_lookup = genre_network.build_genre_network(track_features)
    current = by_id[relative_to]
    candidates = [
        f for f in section_features
        if f.genre == genre and f.section_id != relative_to and f.track_id != current.track_id
    ]

    ranked = sorted(candidates, key=lambda f: similarity.section_distance(current, f, genre_lookup))
    return jsonify([
        {
            "section_id": f.section_id,
            "track_id": f.track_id,
            "track_title": f.track_title,
            "genre": f.genre,
            "tempo_bpm": f.tempo_bpm,
            "section_label": f.section_label,
            "start_sec": f.start_sec,
            "end_sec": f.end_sec,
            "duration_sec": f.duration_sec,
            "similarity": round(
                similarity.similarity_score(similarity.section_distance(current, f, genre_lookup)), 4
            ),
        }
        for f in ranked
    ])


@app.route("/api/nearest-section", methods=["GET"])
def api_nearest_section():
    from_id = request.args.get("from", type=int)
    genre_filter = request.args.get("genre") or None

    section_features = _load_section_features()
    by_id = {f.section_id: f for f in section_features}
    if from_id is None or from_id not in by_id:
        return jsonify({"error": "from (有効なsection_id) を指定してください。"}), 400

    track_features = _load_features()
    _, genre_lookup = genre_network.build_genre_network(track_features)
    current = by_id[from_id]
    candidates = [
        f for f in section_features if f.section_id != from_id and f.track_id != current.track_id
    ]
    if genre_filter:
        candidates = [f for f in candidates if f.genre == genre_filter]

    if not candidates:
        return jsonify({"section": None})

    best = min(candidates, key=lambda f: similarity.section_distance(current, f, genre_lookup))
    dist = similarity.section_distance(current, best, genre_lookup)
    return jsonify({
        "section_id": best.section_id,
        "track_id": best.track_id,
        "track_title": best.track_title,
        "genre": best.genre,
        "tempo_bpm": best.tempo_bpm,
        "section_label": best.section_label,
        "start_sec": best.start_sec,
        "end_sec": best.end_sec,
        "duration_sec": best.duration_sec,
        "similarity": round(similarity.similarity_score(dist), 4),
    })


def _load_match_context(conn, section_id: int, relative_to_track_id: int):
    """(section, current_track, source_track) を返す。見つからないものはNone。"""
    section = db.get_section(conn, section_id)
    current_track = db.get_track(conn, relative_to_track_id)
    source_track = db.get_track(conn, section["track_id"]) if section else None
    return section, current_track, source_track


@app.route("/api/sections/<int:section_id>/harmonic-adjustment", methods=["GET"])
def api_harmonic_adjustment(section_id: int):
    relative_to_track_id = request.args.get("relative_to_track", type=int)
    if relative_to_track_id is None:
        return jsonify({"error": "relative_to_track (有効なtrack_id) を指定してください。"}), 400

    with db.transaction() as conn:
        section, current_track, source_track = _load_match_context(conn, section_id, relative_to_track_id)
    if section is None or current_track is None or source_track is None:
        return jsonify({"error": "見つかりません"}), 404

    adjustment = harmonic_match.resolve_adjustment(
        current_track["tempo_bpm"], current_track["key_camelot"],
        source_track["tempo_bpm"], source_track["key_camelot"],
    )
    return jsonify({
        "stretch_applied": adjustment.stretch_applied,
        "stretch_rate": round(adjustment.stretch_rate, 4),
        "effective_source_bpm": round(adjustment.effective_source_bpm, 2),
        "shift_applied": adjustment.shift_applied,
        "semitone_shift": adjustment.semitone_shift,
        "reason": adjustment.reason,
    })


@app.route("/api/sections/<int:section_id>/matched-audio", methods=["GET"])
def api_matched_audio(section_id: int):
    relative_to_track_id = request.args.get("relative_to_track", type=int)
    if relative_to_track_id is None:
        return jsonify({"error": "relative_to_track (有効なtrack_id) を指定してください。"}), 400

    cache_path = config.STORAGE_MATCHED_DIR / f"{section_id}_{relative_to_track_id}.wav"
    if not cache_path.exists():
        with db.transaction() as conn:
            section, current_track, source_track = _load_match_context(conn, section_id, relative_to_track_id)
        if section is None or current_track is None or source_track is None:
            return jsonify({"error": "見つかりません"}), 404

        adjustment = harmonic_match.resolve_adjustment(
            current_track["tempo_bpm"], current_track["key_camelot"],
            source_track["tempo_bpm"], source_track["key_camelot"],
        )
        source_audio_path = config.BASE_DIR / source_track["audio_path"]
        y, sr = librosa.load(
            source_audio_path, sr=config.SAMPLE_RATE, mono=True,
            offset=section["start_sec"], duration=section["duration_sec"],
        )
        y_out = harmonic_match.render_matched_section(y, sr, adjustment)

        config.STORAGE_MATCHED_DIR.mkdir(parents=True, exist_ok=True)
        soundfile.write(str(cache_path), y_out, sr, subtype="PCM_16")

    return send_from_directory(cache_path.parent, cache_path.name, mimetype="audio/wav")


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5050))
    db.init_db()
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
