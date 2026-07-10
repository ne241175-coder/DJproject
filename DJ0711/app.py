from __future__ import annotations

import tempfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

import config
import db
import jobs
from analysis import genre_network, similarity

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


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5050))
    db.init_db()
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
