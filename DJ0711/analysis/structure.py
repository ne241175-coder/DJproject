from __future__ import annotations

import librosa
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

import config
from analysis.chords import chord_sequence_match_ratio
from analysis.models import Section
from analysis.timbre import normalize

MIN_LEN_BEATS = config.BEATS_PER_BAR * 4       # 16 beats / 4小節
MAX_LEN_BEATS = config.BEATS_PER_BAR * 20      # 20小節
MIN_GAP_BEATS = config.BEATS_PER_BAR * 4       # 境界同士の最小間隔(4小節)
GRID_BARS = 4
IRREGULAR_TOLERANCE_BEATS = config.BEATS_PER_BAR  # 1小節分の許容誤差
MIN_REQUIRED_BEATS = config.BEATS_PER_BAR * 8  # これ未満は等分割にフォールバック

NOVELTY_WEIGHTS = {"ssm": 0.40, "rms": 0.20, "centroid": 0.15, "chord": 0.10, "fill": 0.15}


def compute_ssm(chroma: np.ndarray, rms: np.ndarray, centroid: np.ndarray) -> np.ndarray:
    """chroma+rms+centroidを結合した特徴からSelf-Similarity Matrix(親和度行列)を構築する。"""
    feat = np.vstack([chroma, normalize(rms), normalize(centroid)])
    try:
        rec = librosa.segment.recurrence_matrix(feat, width=3, metric="cosine", mode="affinity", sym=True)
        rec = librosa.segment.path_enhance(rec, n=7, window="hann")
        return np.asarray(rec)
    except Exception:
        try:
            return cosine_similarity(feat.T)
        except Exception:
            norm = feat / (np.linalg.norm(feat, axis=0, keepdims=True) + 1e-9)
            return norm.T @ norm


def _novelty_curve(ssm: np.ndarray, kernel_size: int) -> np.ndarray:
    """Foote型チェッカーボードカーネルによる境界ノベルティカーブ。"""
    n = ssm.shape[0]
    k = max(1, min(kernel_size, max(n // 4, 1)))
    size = 2 * k
    checker = np.kron([[1, -1], [-1, 1]], np.ones((k, k)))
    taper = np.outer(np.hanning(size) + 1e-6, np.hanning(size) + 1e-6)
    kernel = checker * taper

    padded = np.pad(ssm, k, mode="edge")
    novelty = np.zeros(n)
    for i in range(n):
        window = padded[i:i + size, i:i + size]
        novelty[i] = np.sum(window * kernel)
    return normalize(novelty)


def _derivative_novelty(series: np.ndarray, smooth: int = 2) -> np.ndarray:
    diff = np.abs(np.diff(series, prepend=series[0]))
    if smooth > 1 and len(diff) >= smooth:
        kernel = np.ones(smooth) / smooth
        diff = np.convolve(diff, kernel, mode="same")
    return normalize(diff)


def _chord_change_novelty(chord_labels: list[str], smooth: int) -> np.ndarray:
    n = len(chord_labels)
    changes = np.zeros(n)
    for i in range(1, n):
        if chord_labels[i] != chord_labels[i - 1]:
            changes[i] = 1.0
    if smooth > 1 and n >= smooth:
        kernel = np.ones(smooth) / smooth
        changes = np.convolve(changes, kernel, mode="same")
    return normalize(changes)


def _local_maxima(curve: np.ndarray) -> list[int]:
    return [i for i in range(1, len(curve) - 1) if curve[i] >= curve[i - 1] and curve[i] >= curve[i + 1]]


def _select_boundaries(combined: np.ndarray, min_gap_beats: int) -> list[int]:
    candidates = _local_maxima(combined)
    if not candidates:
        return []
    floor = np.mean(combined) + 0.35 * np.std(combined)
    candidates = [i for i in candidates if combined[i] >= floor]
    candidates.sort(key=lambda i: combined[i], reverse=True)

    selected: list[int] = []
    for i in candidates:
        if all(abs(i - s) >= min_gap_beats for s in selected):
            selected.append(i)
    return sorted(selected)


def _snap_to_grid(boundaries: list[int], beats_per_bar: int, n_beats: int) -> list[int]:
    grid4 = beats_per_bar * GRID_BARS
    snapped = []
    for b in boundaries:
        nearest4 = round(b / grid4) * grid4
        if abs(b - nearest4) <= IRREGULAR_TOLERANCE_BEATS:
            snapped.append(int(np.clip(nearest4, 0, n_beats)))
        else:
            nearest1 = round(b / beats_per_bar) * beats_per_bar
            snapped.append(int(np.clip(nearest1, 0, n_beats)))
    return sorted({b for b in snapped if 0 < b < n_beats})


def _merge_short_segments(boundaries: list[int], min_len: int, n_beats: int) -> list[int]:
    edges = [0] + boundaries + [n_beats]
    changed = True
    while changed:
        changed = False
        for i in range(1, len(edges) - 1):
            if edges[i] - edges[i - 1] < min_len:
                del edges[i]
                changed = True
                break
    return edges[1:-1]


def _split_long_segments(
    boundaries: list[int], combined: np.ndarray, max_len: int, n_beats: int, max_iters: int = 8
) -> list[int]:
    edges = [0] + boundaries + [n_beats]
    used = set(edges)
    for _ in range(max_iters):
        too_long = None
        for i in range(1, len(edges)):
            if edges[i] - edges[i - 1] > max_len:
                too_long = (edges[i - 1], edges[i])
                break
        if too_long is None:
            break
        lo, hi = too_long
        segment = combined[lo:hi]
        if len(segment) == 0:
            break
        order = np.argsort(segment)[::-1]
        picked = None
        for rel in order:
            candidate = lo + int(rel)
            if candidate not in used and lo < candidate < hi:
                picked = candidate
                break
        if picked is None:
            break
        edges = sorted(set(edges) | {picked})
        used.add(picked)
    return edges[1:-1]


def _validate_non_overlapping(sections: list[Section]) -> bool:
    for i in range(1, len(sections)):
        if sections[i].start_sec < sections[i - 1].end_sec:
            return False
    return True


def _apply_family(labels: list, confidences: list, members: list[int], base_name: str) -> None:
    for order, i in enumerate(sorted(members)):
        labels[i] = base_name if order == 0 else f"{base_name}{order + 1}"
        confidences[i] = 0.8


def _assign_labels(raw_sections: list[dict], rms: np.ndarray, beats_per_bar: int) -> list[Section]:
    n = len(raw_sections)
    rms_tol = 0.3 * float(np.std(rms))

    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        for j in range(i + 2, n):  # 隣接セクション同士は「繰り返し」とみなさない
            vec_i, vec_j = raw_sections[i]["chroma_vec"], raw_sections[j]["chroma_vec"]
            denom = np.linalg.norm(vec_i) * np.linalg.norm(vec_j)
            chroma_sim = float(np.dot(vec_i, vec_j) / denom) if denom > 1e-9 else 0.0
            chord_match = chord_sequence_match_ratio(
                raw_sections[i]["chord_progression"], raw_sections[j]["chord_progression"]
            )
            rms_close = abs(raw_sections[i]["mean_rms"] - raw_sections[j]["mean_rms"]) < rms_tol
            if chroma_sim > 0.93 and chord_match > 0.55 and rms_close:
                union(i, j)

    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)
    recurring = [members for members in clusters.values() if len(members) >= 2]
    recurring.sort(key=lambda members: np.mean([raw_sections[i]["mean_rms"] for i in members]), reverse=True)

    labels: list[str | None] = [None] * n
    confidences: list[float] = [0.5] * n

    if recurring:
        _apply_family(labels, confidences, recurring[0], "Ma")
        remaining = sorted(
            recurring[1:], key=lambda members: np.mean([raw_sections[i]["mean_rms"] for i in members])
        )
        family_letters = ["A", "B"]
        for idx, members in enumerate(remaining):
            name = family_letters[idx] if idx < len(family_letters) else "C"
            _apply_family(labels, confidences, members, name)
    else:
        rms_n = normalize(np.array([s["mean_rms"] for s in raw_sections]))
        centroid_n = normalize(np.array([s["mean_centroid"] for s in raw_sections]))
        vocal_n = normalize(np.array([s["vocal_presence"] for s in raw_sections]))
        composite = 0.5 * rms_n + 0.3 * centroid_n + 0.2 * vocal_n
        best_i = int(np.argmax(composite))
        labels[best_i] = "Ma"
        confidences[best_i] = float(composite[best_i])

    if labels[0] is None:
        labels[0] = "In"
    if labels[-1] is None:
        labels[-1] = "Out"

    c_counter = 0
    for i in range(n):
        if labels[i] is None:
            c_counter += 1
            labels[i] = "C" if c_counter == 1 else f"C{c_counter}"

    sections = []
    for i, raw in enumerate(raw_sections):
        sections.append(Section(
            label=labels[i],
            start_sec=float(raw["start_sec"]),
            end_sec=float(raw["end_sec"]),
            start_bar=int(raw["start_bar"]),
            end_bar=int(raw["end_bar"]),
            mean_rms=float(raw["mean_rms"]),
            mean_centroid=float(raw["mean_centroid"]),
            confidence=float(confidences[i]),
            vocal_presence=float(raw["vocal_presence"]),
            chord_progression=list(raw["chord_progression"]),
        ))
    return sections


def _fallback_equal_split(
    n_beats: int, edges: np.ndarray, rms: np.ndarray, centroid: np.ndarray, beats_per_bar: int, n_parts: int = 4
) -> list[Section]:
    if n_beats < 1:
        return []
    n_parts = max(1, min(n_parts, n_beats))
    bounds = np.linspace(0, n_beats, n_parts + 1).astype(int)
    sections = []
    for i in range(n_parts):
        b0, b1 = int(bounds[i]), int(bounds[i + 1])
        if b1 <= b0:
            continue
        sections.append(Section(
            label=f"Part{i + 1}",
            start_sec=float(edges[b0]),
            end_sec=float(edges[b1]),
            start_bar=b0 // beats_per_bar,
            end_bar=b1 // beats_per_bar,
            mean_rms=float(np.mean(rms[b0:b1])),
            mean_centroid=float(np.mean(centroid[b0:b1])),
            confidence=0.2 if n_parts > 1 else 0.1,
            vocal_presence=0.0,
            chord_progression=[],
        ))
    return sections


def _detect_structure_core(
    chroma: np.ndarray,
    rms: np.ndarray,
    centroid: np.ndarray,
    vocal_presence: np.ndarray,
    fill_score: np.ndarray,
    chord_labels: list[str],
    edges: np.ndarray,
    ssm: np.ndarray,
    beats_per_bar: int,
) -> list[Section]:
    n_beats = len(rms)

    ssm_novelty = _novelty_curve(ssm, kernel_size=min(16, max(n_beats // 4, 1)))
    rms_novelty = _derivative_novelty(rms)
    centroid_novelty = _derivative_novelty(centroid)
    chord_novelty = _chord_change_novelty(chord_labels, smooth=beats_per_bar)
    fill_novelty = normalize(fill_score)

    combined = (
        NOVELTY_WEIGHTS["ssm"] * ssm_novelty
        + NOVELTY_WEIGHTS["rms"] * rms_novelty
        + NOVELTY_WEIGHTS["centroid"] * centroid_novelty
        + NOVELTY_WEIGHTS["chord"] * chord_novelty
        + NOVELTY_WEIGHTS["fill"] * fill_novelty
    )

    boundaries = _select_boundaries(combined, MIN_GAP_BEATS)
    boundaries = _snap_to_grid(boundaries, beats_per_bar, n_beats)
    boundaries = _merge_short_segments(boundaries, MIN_LEN_BEATS, n_beats)
    boundaries = _split_long_segments(boundaries, combined, MAX_LEN_BEATS, n_beats)

    beat_edges = [0] + boundaries + [n_beats]
    raw_sections = []
    for i in range(len(beat_edges) - 1):
        b0, b1 = beat_edges[i], beat_edges[i + 1]
        raw_sections.append({
            "start_sec": edges[b0],
            "end_sec": edges[b1],
            "start_bar": b0 // beats_per_bar,
            "end_bar": b1 // beats_per_bar,
            "mean_rms": float(np.mean(rms[b0:b1])),
            "mean_centroid": float(np.mean(centroid[b0:b1])),
            "vocal_presence": float(np.mean(vocal_presence[b0:b1])),
            "chord_progression": chord_labels[b0:b1],
            "chroma_vec": chroma[:, b0:b1].mean(axis=1),
        })

    return _assign_labels(raw_sections, rms, beats_per_bar)


def detect_structure(
    chroma: np.ndarray,
    rms: np.ndarray,
    centroid: np.ndarray,
    vocal_presence: np.ndarray,
    fill_score: np.ndarray,
    chord_labels: list[str],
    edges: np.ndarray,
    beats_per_bar: int = config.BEATS_PER_BAR,
) -> list[Section]:
    """曲を構造区間(In/A/B/Ma/C/Out等)に分割する。

    chroma: shape (12, n_beats), rms/centroid: shape (1, n_beats) または (n_beats,)
    edges: beatsync.beat_sync()が返す長さn_beats+1の境界時刻配列
    """
    rms_1d = np.ravel(rms)
    centroid_1d = np.ravel(centroid)
    n_beats = chroma.shape[1]

    ssm = compute_ssm(chroma, rms_1d, centroid_1d)
    ssm_ok = np.all(np.isfinite(ssm)) and np.nanstd(ssm) >= 1e-9

    if n_beats < MIN_REQUIRED_BEATS or not ssm_ok:
        return _fallback_equal_split(n_beats, edges, rms_1d, centroid_1d, beats_per_bar)

    sections = _detect_structure_core(
        chroma, rms_1d, centroid_1d, vocal_presence, fill_score, chord_labels, edges, ssm, beats_per_bar
    )
    if not sections or not _validate_non_overlapping(sections):
        return _fallback_equal_split(n_beats, edges, rms_1d, centroid_1d, beats_per_bar)
    return sections
