from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Section:
    """曲を構成するひとつの区間(イントロ/サビ等)。

    label は In / A / B / Ma(サビ系) / C / Out、
    フォールバック時は Part1 / Part2 ... になる。
    """
    label: str
    start_sec: float
    end_sec: float
    start_bar: int
    end_bar: int
    mean_rms: float
    mean_centroid: float
    confidence: float = 0.0
    vocal_presence: float = 0.0
    chord_progression: list[str] = field(default_factory=list)

    @property
    def duration_sec(self) -> float:
        return round(self.end_sec - self.start_sec, 3)


@dataclass
class KeyResult:
    key_name: str          # 例: "C Major"
    camelot: str           # 例: "8B"
    confidence: float


@dataclass
class GenreResult:
    genre: str
    confidence: float
    scores: dict[str, float] = field(default_factory=dict)
    features_used: dict[str, float] = field(default_factory=dict)


@dataclass
class BeatFeatures:
    """ビート同期済みの時系列特徴量(曲全体、可視化・VJ用)。"""
    times: list[float]
    rms: list[float]
    centroid: list[float]
    vocal_presence: list[float]
    drum_fill: list[float]


@dataclass
class TrackAnalysis:
    duration_sec: float
    trim_offset_sec: float
    beats_per_bar: int
    tempo_bpm: float
    key: KeyResult
    genre: GenreResult
    sections: list[Section]
    beats: BeatFeatures
    chord_labels: list[str]
