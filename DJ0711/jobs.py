from __future__ import annotations

import logging
import re
import shutil
import tempfile
import threading
import time
import traceback
from pathlib import Path

import config
import db
from analysis import io, pipeline

logger = logging.getLogger("dj0711.analysis")
logger.setLevel(logging.INFO)

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
CURRENT_JOB_ID: str | None = None


class _JobLogHandler(logging.Handler):
    """analysisロガーの出力を、ジョブごとのログバッファへ流し込む(直近500行まで保持)。"""

    def __init__(self, job_id: str):
        super().__init__()
        self.job_id = job_id
        self.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            with JOBS_LOCK:
                if self.job_id in JOBS:
                    JOBS[self.job_id]["logs"].append(msg)
                    JOBS[self.job_id]["logs"] = JOBS[self.job_id]["logs"][-500:]
        except Exception:
            pass


def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\-]+", "-", text, flags=re.UNICODE).strip("-")
    return text[:40] or "track"


def make_identifier(title_hint: str) -> str:
    base = _slugify(title_hint)
    suffix = str(int(time.time() * 1000))[-6:]
    return f"{base}-{suffix}"


def start_analyze_job(*, youtube_url: str | None, uploaded_path: Path | None, genre_hint: str | None) -> str:
    """analyzeジョブを開始し、job_idを返す。同時に1件のみ実行可能。"""
    global CURRENT_JOB_ID

    if not youtube_url and not uploaded_path:
        raise ValueError("youtube_url か uploaded_path のいずれかが必要です。")

    title_hint = youtube_url or (uploaded_path.stem if uploaded_path else "track")
    job_id = make_identifier(title_hint)

    with JOBS_LOCK:
        if CURRENT_JOB_ID is not None:
            raise RuntimeError(f"現在ジョブ「{CURRENT_JOB_ID}」を実行中です。完了してからお試しください。")
        CURRENT_JOB_ID = job_id
        JOBS[job_id] = {
            "status": "running", "logs": [], "error": None, "track_id": None,
        }

    thread = threading.Thread(
        target=_run_job, args=(job_id, youtube_url, uploaded_path, genre_hint), daemon=True
    )
    thread.start()
    return job_id


def _run_job(job_id: str, youtube_url: str | None, uploaded_path: Path | None, genre_hint: str | None) -> None:
    global CURRENT_JOB_ID
    handler = _JobLogHandler(job_id)
    logger.addHandler(handler)

    workdir = Path(tempfile.mkdtemp(prefix=f"dj0711_{job_id}_"))
    try:
        io.check_dependencies()

        title = None
        if youtube_url:
            logger.info("YouTubeから音声をダウンロード中...")
            raw_path, title = io.download_youtube_audio(youtube_url, workdir, job_id)
        else:
            logger.info("アップロードされたファイルを読み込み中...")
            raw_path = io.load_uploaded_file(uploaded_path, workdir, job_id)
            title = uploaded_path.stem

        logger.info("解析を開始します...")
        result, trimmed_path = pipeline.analyze_track(raw_path, workdir, job_id, genre_hint)
        logger.info(
            f"解析完了: tempo={result.tempo_bpm:.1f}bpm key={result.key.key_name}"
            f"({result.key.camelot}) genre={result.genre.genre}"
        )

        config.STORAGE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        audio_dest = config.STORAGE_AUDIO_DIR / f"{job_id}.mp3"
        shutil.copy(trimmed_path, audio_dest)

        with db.transaction() as conn:
            track_id = db.insert_track_full(
                conn,
                identifier=job_id,
                title=title,
                source_type="youtube" if youtube_url else "upload",
                source_youtube_url=youtube_url,
                source_filename=uploaded_path.name if uploaded_path else None,
                audio_path=str(audio_dest.relative_to(config.BASE_DIR)),
                result=result,
            )

        with JOBS_LOCK:
            JOBS[job_id]["status"] = "done"
            JOBS[job_id]["track_id"] = track_id

    except io.AnalysisError as e:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["error"] = str(e)
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["error"] = f"予期しないエラー: {e}\n{traceback.format_exc()}"
    finally:
        logger.removeHandler(handler)
        shutil.rmtree(workdir, ignore_errors=True)
        with JOBS_LOCK:
            CURRENT_JOB_ID = None


def get_job_status(job_id: str) -> dict | None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return dict(job) if job else None
