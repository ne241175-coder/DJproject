// ライブセッションの状態機械: idle -> playing -> selectionOpen -> crossfading -> playing
// 遷移の単位は「曲」ではなく「セクション」(イントロ/Aメロ/Bメロ/サビ等)。
// audioEngine(再生)・network(選曲UI)・vj(背景ビジュアル)を橋渡しする。

import { AudioEngine } from "./audioEngine.js";
import { NetworkGraph } from "./network.js";
import { VJVisual } from "./vj.js";
import * as api from "./api.js";

const CROSSFADE_SEC = 4;
const DEFAULT_TRIGGER_SEC = 8; // 残りこの秒数を切ったら選択パネルを開く(デバッグ用に上書き可)

export class Player {
  constructor({ networkContainerId, vjContainerId, ui }) {
    this.audio = new AudioEngine();
    this.network = new NetworkGraph(networkContainerId, {
      onGenreClick: (genre) => this._onGenreClick(genre),
    });
    this.vj = new VJVisual(vjContainerId);
    this.ui = ui; // { statusEl, remainingEl, genreListEl }

    this.state = "idle"; // idle | playing | selectionOpen | crossfading
    this._paused = false;
    this.currentDetail = null;  // { track, sections, beats(parsed) } — 現在再生中の曲全体のデータ
    this.currentSection = null; // currentDetail.sectionsの要素そのもの(生のDB行の形を保つ)
    this.currentStretchRate = 1.0;     // ハーモニックミキシングでBPMを伸縮した比率(1.0=補正なし)
    this.currentIsMatchedClip = false; // 現在の再生がmatched-audio(補正後の単独クリップ)かどうか
    this.networkData = null;

    const params = new URLSearchParams(location.search);
    this.triggerSec = Number(params.get("debugTriggerSec")) || DEFAULT_TRIGGER_SEC;

    this._loop = this._loop.bind(this);
    requestAnimationFrame(this._loop);
  }

  async start(trackId) {
    // AudioContextの最初のresumeは、ユーザー操作(開始ボタンのクリック)に
    // 直接紐づくこのタイミングでのみ行う。crossfadeTo/playTrack側では呼ばない
    // (呼ぶと、一時停止中にセクションを選んだ際に一時停止が意図せず解除され、
    // Player._pausedフラグと実際の再生状態がズレるバグになるため)。
    await this.audio.resumeAll();
    await this._loadNetwork();
    await this._playSectionId(trackId, null, false);
  }

  async togglePause() {
    // ctx.stateの読み直しはsuspend()/resume()呼び出し直後だとタイミング次第で
    // 更新前の値を読んでしまう(連打でpause/resumeが食い違うレースの原因になった)。
    // 呼び出し側の意図(_paused)を真実の情報源にし、Promiseの完了を待ってから確定させる。
    if (this._paused) {
      await this.audio.resumeAll();
      this._paused = false;
    } else {
      await this.audio.pauseAll();
      this._paused = true;
    }
    return this._paused;
  }

  async _loadNetwork() {
    this.networkData = await api.fetchNetwork();
    this.network.setNetwork(this.networkData);
  }

  /**
   * トラックの中の1セクションを再生する(または現在のセクションからクロスフェードする)。
   * sectionId===null の場合は、そのトラックの最初のセクションから始める(セッション開始時用)。
   *
   * 類似度API(/api/genre/<genre>/sections, /api/nearest-section)が返す形は
   * section_id/section_label等の見た目の異なるオブジェクトだが、実際に再生・追跡する
   * this.currentSectionは必ず /api/tracks/<id> から取得した sections[] の要素そのものを
   * 使う(2つの異なる形を混同しないための重要なルール)。
   */
  async _playSectionId(trackId, sectionId, isCrossfade) {
    // currentDetailが後で上書きされる前に、遷移元(合わせる対象)のtrack idを捕まえておく。
    const matchTrackId = isCrossfade && this.currentDetail ? this.currentDetail.track.id : null;

    const detail = await api.fetchTrackDetail(trackId);
    const beats = JSON.parse(detail.track.beats_json);
    const section = sectionId != null
      ? detail.sections.find((s) => s.id === sectionId)
      : detail.sections[0];

    this.currentDetail = { track: detail.track, sections: detail.sections, beats };
    this.currentSection = section;

    let url = api.trackAudioUrl(trackId);
    let offsetSec = section.start_sec;
    let stretchRate = 1.0;
    let isMatchedClip = false;

    if (matchTrackId != null) {
      const adjustment = await api.fetchHarmonicAdjustment(section.id, matchTrackId);
      if (adjustment.stretch_applied || adjustment.shift_applied) {
        url = api.matchedAudioUrl(section.id, matchTrackId);
        offsetSec = 0;
        stretchRate = adjustment.stretch_applied ? adjustment.stretch_rate : 1.0;
        isMatchedClip = true;
      }
    }
    this.currentStretchRate = stretchRate;
    this.currentIsMatchedClip = isMatchedClip;

    if (isCrossfade) {
      await this.audio.crossfadeTo(trackId, url, CROSSFADE_SEC, offsetSec);
    } else {
      await this.audio.playTrack(trackId, url, offsetSec);
    }

    this.network.setCurrentGenre(detail.track.genre);
    this.state = "playing";
    this._hideGenreList();
    this._setStatus(
      `再生中: ${detail.track.title} - ${section.label} [${detail.track.genre}] ${detail.track.tempo_bpm.toFixed(1)}bpm`
      + (isMatchedClip ? " (BPM/Key補正済み)" : "")
    );
  }

  /** 選択パネルが開いた瞬間に、時間切れで実際に使われる可能性が高い候補の
   *  補正済み音声を投機的に1件だけ生成させておく(キャッシュを温める)。
   *  失敗しても実際の遷移には影響しないため、エラーは握りつぶす。 */
  async _prefetchTimeoutCandidate() {
    try {
      const nearest = await api.fetchNearestSection(this.currentSection.id, null);
      if (!nearest || nearest.section_id === undefined || !this.currentDetail) return;
      const matchTrackId = this.currentDetail.track.id;
      const adjustment = await api.fetchHarmonicAdjustment(nearest.section_id, matchTrackId);
      if (adjustment.stretch_applied || adjustment.shift_applied) {
        await fetch(api.matchedAudioUrl(nearest.section_id, matchTrackId));
      }
    } catch (e) {
      // 投機的プリフェッチの失敗は無視する(本番の遷移経路が改めて正しく処理する)
    }
  }

  _onGenreClick(genre) {
    if (this.state !== "selectionOpen" || !this.currentDetail) return;

    const currentGenre = this.currentDetail.track.genre;
    if (genre === currentGenre) {
      this._showGenreSectionList(genre);
    } else {
      this._forcedGenreTransition(genre);
    }
  }

  async _showGenreSectionList(genre) {
    const list = await api.fetchGenreSections(genre, this.currentSection.id);
    const container = this.ui.genreListEl;
    if (!container) return;
    container.innerHTML = "";
    container.style.display = "block";

    if (list.length === 0) {
      container.innerHTML = "<p>同じジャンルの他のセクションがありません。</p>";
      return;
    }

    const ul = document.createElement("ul");
    for (const item of list) {
      const li = document.createElement("li");
      li.textContent = `${item.track_title} - ${item.section_label} (${item.tempo_bpm.toFixed(1)}bpm, 類似度${item.similarity})`;
      li.style.cursor = "pointer";
      li.addEventListener("click", () => this._manualTransition(item.track_id, item.section_id));
      ul.appendChild(li);
    }
    container.appendChild(ul);
  }

  _hideGenreList() {
    if (this.ui.genreListEl) {
      this.ui.genreListEl.style.display = "none";
      this.ui.genreListEl.innerHTML = "";
    }
  }

  async _manualTransition(trackId, sectionId) {
    this.state = "crossfading";
    this._hideGenreList();
    this._setStatus("手動選択でクロスフェード中...");
    await this._playSectionId(trackId, sectionId, true);
  }

  async _forcedGenreTransition(genre) {
    this.state = "crossfading";
    this._hideGenreList();
    const nearest = await api.fetchNearestSection(this.currentSection.id, genre);
    if (!nearest || nearest.section_id === undefined) {
      this._setStatus(`ジャンル「${genre}」に他のセクションがありません。`);
      this.state = "selectionOpen";
      return;
    }
    this._setStatus(`別ジャンル(${genre})の最近傍セクションへ自動遷移中...`);
    await this._playSectionId(nearest.track_id, nearest.section_id, true);
  }

  async _timeoutTransition() {
    this.state = "crossfading";
    this._hideGenreList();
    const nearest = await api.fetchNearestSection(this.currentSection.id, null);
    if (!nearest || nearest.section_id === undefined) {
      this._setStatus("時間切れですが、遷移先のセクションがありません。");
      this.state = "playing";
      return;
    }
    this._setStatus("時間切れ: 最近傍セクションへ自動遷移中...");
    await this._playSectionId(nearest.track_id, nearest.section_id, true);
  }

  _findCurrentBeatIndex(positionSec) {
    const times = this.currentDetail.beats.times;
    if (!times || times.length === 0) return -1;
    let idx = 0;
    for (let i = 0; i < times.length; i++) {
      if (times[i] <= positionSec) idx = i; else break;
    }
    return idx;
  }

  _findCurrentSectionLabel(positionSec) {
    const sections = this.currentDetail.sections || [];
    for (const s of sections) {
      if (positionSec >= s.start_sec && positionSec < s.end_sec) return s.label;
    }
    return null;
  }

  _normalizedEnergy(rmsArr, idx) {
    if (!rmsArr.length) return 0;
    const clamped = Math.max(0, Math.min(idx, rmsArr.length - 1));
    const max = Math.max(...rmsArr) || 1;
    return rmsArr[clamped] / max;
  }

  _loop() {
    requestAnimationFrame(this._loop);
    if (!this.currentDetail || !this.currentSection
      || (this.state !== "playing" && this.state !== "selectionOpen")) return;

    const elapsedInSource = this.audio.getElapsedSec(); // 今のsourceが始まってからの経過時間(0始まり)
    // BPM補正で伸縮している場合、伸縮後クリップ上の経過時間を元の(未補正)タイムライン上の
    // 経過時間に戻してからabsolutePosを計算する(stretch_rate=1.0なら通常通り)。
    const absolutePos = this.currentSection.start_sec + elapsedInSource * this.currentStretchRate;
    // 補正済みクリップ(matched-audio)は独立した音声としての実際の長さを基準に残り時間を測る。
    // 通常再生は従来通りセクション境界(絶対位置)を基準にする。
    const remainingInSection = this.currentIsMatchedClip
      ? this.audio.getDurationSec() - elapsedInSource
      : this.currentSection.end_sec - absolutePos;

    const beatIdx = this._findCurrentBeatIndex(absolutePos);
    const rmsArr = this.currentDetail.beats.rms || [];
    const energy = this._normalizedEnergy(rmsArr, beatIdx);
    const sectionLabel = this._findCurrentSectionLabel(absolutePos);

    // VJへ渡すelapsedSecはセクション開始からの経過時間のまま(絶対位置を渡すと
    // 遷移のたびに色相が不連続にジャンプしてしまうため、意図的に据え置く)。
    this.vj.updateFrame({ elapsedSec: elapsedInSource, currentBeatIndex: beatIdx, energy, sectionLabel });

    if (this.ui.remainingEl) {
      this.ui.remainingEl.textContent = `残り(セクション内) ${Math.max(0, remainingInSection).toFixed(1)}s`;
    }

    // 短いセクションが続くと、前のクロスフェードが終わる前に次の選択状態へ
    // 入ってしまい、フェードが重なる恐れがある。直前のクロスフェード(CROSSFADE_SEC)
    // が終わるまでは次の選択状態に入らないようにする。
    if (this.state === "playing"
      && elapsedInSource >= CROSSFADE_SEC
      && remainingInSection <= this.triggerSec) {
      this.state = "selectionOpen";
      this._setStatus("そろそろ次のセクションを選んでください(同ジャンル=手動選択 / 別ジャンル=自動再生)");
      this._prefetchTimeoutCandidate();
    }

    if (this.state === "selectionOpen" && remainingInSection <= 0.2) {
      this._timeoutTransition();
    }
  }

  _setStatus(text) {
    if (this.ui.statusEl) this.ui.statusEl.textContent = text;
  }
}
