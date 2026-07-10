// ライブセッションの状態機械: idle -> playing -> selectionOpen -> crossfading -> playing
// audioEngine(再生)・network(選曲UI)・vj(背景ビジュアル)を橋渡しする。

import { AudioEngine } from "./audioEngine.js";
import { NetworkGraph } from "./network.js";
import { VJVisual } from "./vj.js";
import * as api from "./api.js";

const CROSSFADE_SEC = 4;
const DEFAULT_TRIGGER_SEC = 20; // 残りこの秒数を切ったら選択パネルを開く(デバッグ用に上書き可)

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
    this.currentTrackId = null;
    this.currentDetail = null; // { track, sections, beats(parsed) }
    this.networkData = null;

    const params = new URLSearchParams(location.search);
    this.triggerSec = Number(params.get("debugTriggerSec")) || DEFAULT_TRIGGER_SEC;

    this._loop = this._loop.bind(this);
    requestAnimationFrame(this._loop);
  }

  async start(trackId) {
    await this._loadNetwork();
    await this._playTrackId(trackId, false);
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

  async _playTrackId(trackId, isCrossfade) {
    const detail = await api.fetchTrackDetail(trackId);
    const beats = JSON.parse(detail.track.beats_json);
    this.currentDetail = { track: detail.track, sections: detail.sections, beats };
    this.currentTrackId = trackId;

    const url = api.trackAudioUrl(trackId);
    if (isCrossfade) {
      await this.audio.crossfadeTo(trackId, url, CROSSFADE_SEC);
    } else {
      await this.audio.playTrack(trackId, url);
    }

    this.network.setCurrentGenre(detail.track.genre);
    this.state = "playing";
    this._hideGenreList();
    this._setStatus(
      `再生中: ${detail.track.title} [${detail.track.genre}] ${detail.track.tempo_bpm.toFixed(1)}bpm`
    );
  }

  _onGenreClick(genre) {
    if (this.state !== "selectionOpen" || !this.currentDetail) return;

    const currentGenre = this.currentDetail.track.genre;
    if (genre === currentGenre) {
      this._showGenreList(genre);
    } else {
      this._forcedGenreTransition(genre);
    }
  }

  async _showGenreList(genre) {
    const list = await api.fetchGenreTracks(genre, this.currentTrackId);
    const container = this.ui.genreListEl;
    if (!container) return;
    container.innerHTML = "";
    container.style.display = "block";

    if (list.length === 0) {
      container.innerHTML = "<p>同じジャンルの他の曲がありません。</p>";
      return;
    }

    const ul = document.createElement("ul");
    for (const item of list) {
      const li = document.createElement("li");
      li.textContent = `${item.title} (${item.tempo_bpm.toFixed(1)}bpm, 類似度${item.similarity})`;
      li.style.cursor = "pointer";
      li.addEventListener("click", () => this._manualTransition(item.track_id));
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

  async _manualTransition(trackId) {
    this.state = "crossfading";
    this._hideGenreList();
    this._setStatus("手動選択でクロスフェード中...");
    await this._playTrackId(trackId, true);
  }

  async _forcedGenreTransition(genre) {
    this.state = "crossfading";
    this._hideGenreList();
    const nearest = await api.fetchNearestTrack(this.currentTrackId, genre);
    if (!nearest || nearest.track_id === undefined) {
      this._setStatus(`ジャンル「${genre}」に他の曲がありません。`);
      this.state = "selectionOpen";
      return;
    }
    this._setStatus(`別ジャンル(${genre})の最近傍曲へ自動遷移中...`);
    await this._playTrackId(nearest.track_id, true);
  }

  async _timeoutTransition() {
    this.state = "crossfading";
    this._hideGenreList();
    const nearest = await api.fetchNearestTrack(this.currentTrackId, null);
    if (!nearest || nearest.track_id === undefined) {
      this._setStatus("時間切れですが、遷移先の曲がありません。");
      this.state = "playing";
      return;
    }
    this._setStatus("時間切れ: 最近傍曲へ自動遷移中...");
    await this._playTrackId(nearest.track_id, true);
  }

  _findCurrentBeatIndex(elapsedSec) {
    const times = this.currentDetail.beats.times;
    if (!times || times.length === 0) return -1;
    let idx = 0;
    for (let i = 0; i < times.length; i++) {
      if (times[i] <= elapsedSec) idx = i; else break;
    }
    return idx;
  }

  _findCurrentSectionLabel(elapsedSec) {
    const sections = this.currentDetail.sections || [];
    for (const s of sections) {
      if (elapsedSec >= s.start_sec && elapsedSec < s.end_sec) return s.label;
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
    if (!this.currentDetail || (this.state !== "playing" && this.state !== "selectionOpen")) return;

    const elapsed = this.audio.getElapsedSec();
    const remaining = this.audio.getRemainingSec();
    const beatIdx = this._findCurrentBeatIndex(elapsed);
    const rmsArr = this.currentDetail.beats.rms || [];
    const energy = this._normalizedEnergy(rmsArr, beatIdx);
    const sectionLabel = this._findCurrentSectionLabel(elapsed);

    this.vj.updateFrame({ elapsedSec: elapsed, currentBeatIndex: beatIdx, energy, sectionLabel });

    if (this.ui.remainingEl) {
      this.ui.remainingEl.textContent = `残り ${Math.max(0, remaining).toFixed(1)}s`;
    }

    if (this.state === "playing" && remaining <= this.triggerSec) {
      this.state = "selectionOpen";
      this._setStatus("そろそろ次の曲を選んでください(同ジャンル=手動選択 / 別ジャンル=自動再生)");
    }

    if (this.state === "selectionOpen" && remaining <= 0.2) {
      this._timeoutTransition();
    }
  }

  _setStatus(text) {
    if (this.ui.statusEl) this.ui.statusEl.textContent = text;
  }
}
