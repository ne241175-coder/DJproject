from __future__ import annotations

import glob
import shutil
from pathlib import Path

import librosa
import numpy as np
from pydub import AudioSegment
from pydub.silence import detect_leading_silence

import config


class AnalysisError(Exception):
    """解析パイプライン内の致命的エラー(フォールバック不能時に送出)"""


def check_dependencies() -> None:
    if shutil.which("ffmpeg") is None:
        raise AnalysisError("ffmpeg が見つかりません。`brew install ffmpeg` 等でインストールしてください。")


def download_youtube_audio(youtube_url: str, workdir: Path, identifier: str) -> tuple[Path, str | None]:
    """YouTube URLから音声をダウンロードし、(mp3パス, タイトル) を返す。"""
    import yt_dlp

    outtmpl = str(workdir / f"{identifier}_raw.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "0",
        }],
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)
            title = info.get("title") if info else None
    except Exception as e:
        raise AnalysisError(f"YouTubeからのダウンロードに失敗しました: {e}") from e

    expected = workdir / f"{identifier}_raw.mp3"
    if expected.exists():
        return expected, title

    candidates = glob.glob(str(workdir / f"{identifier}_raw.*"))
    if not candidates:
        raise AnalysisError("ダウンロードされた音声ファイルが見つかりません。")
    return Path(candidates[0]), title


def load_uploaded_file(uploaded_path: Path, workdir: Path, identifier: str) -> Path:
    """アップロードされたローカルファイルを作業ディレクトリにコピーする。"""
    dest = workdir / f"{identifier}_raw{uploaded_path.suffix}"
    shutil.copy(uploaded_path, dest)
    return dest


def preprocess(raw_path: Path, workdir: Path, identifier: str) -> tuple[np.ndarray, int, float, Path]:
    """無音トリム + モノラル化 + リサンプルを行い、(waveform, sr, trim_offset_sec, trimmed_path) を返す。"""
    try:
        seg = AudioSegment.from_file(raw_path)
    except Exception as e:
        raise AnalysisError(f"音声ファイルの読み込みに失敗しました: {e}") from e

    seg = seg.set_channels(1).set_frame_rate(config.SAMPLE_RATE)
    duration_ms = len(seg)

    start_trim = detect_leading_silence(
        seg, silence_threshold=config.SILENCE_THRESH_DB, chunk_size=config.SILENCE_CHUNK_MS
    )
    end_trim = detect_leading_silence(
        seg.reverse(), silence_threshold=config.SILENCE_THRESH_DB, chunk_size=config.SILENCE_CHUNK_MS
    )

    if start_trim + end_trim > duration_ms * config.MAX_TRIM_RATIO:
        start_trim, end_trim = 0, 0

    trimmed = seg[start_trim: duration_ms - end_trim] if (start_trim or end_trim) else seg

    trimmed_path = workdir / f"{identifier}_trimmed.mp3"
    trimmed.export(trimmed_path, format="mp3", bitrate=config.AUDIO_BITRATE)

    try:
        y, sr = librosa.load(trimmed_path, sr=config.SAMPLE_RATE, mono=True)
    except Exception as e:
        raise AnalysisError(f"前処理後の音声読み込みに失敗しました: {e}") from e

    trim_offset_sec = start_trim / 1000.0
    return y, sr, trim_offset_sec, trimmed_path
