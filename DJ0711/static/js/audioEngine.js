// Web Audio APIでの再生・2音源間クロスフェードを担当する。
// フレームワーク非依存、p5.js/DOMには一切触れない(player.jsが橋渡しする)。

export class AudioEngine {
  constructor() {
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    this.current = null; // { trackId, source, gainNode, buffer, startTime }
    this.onEnded = null; // (trackId) => void
  }

  resume() {
    if (this.ctx.state === "suspended") {
      this.ctx.resume();
    }
  }

  async _loadBuffer(url) {
    const res = await fetch(url);
    const arrayBuffer = await res.arrayBuffer();
    return this.ctx.decodeAudioData(arrayBuffer);
  }

  _makeNode(buffer, initialGain) {
    const gainNode = this.ctx.createGain();
    gainNode.gain.value = initialGain;
    gainNode.connect(this.ctx.destination);

    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(gainNode);
    return { source, gainNode };
  }

  async playTrack(trackId, url) {
    this.resume();
    const buffer = await this._loadBuffer(url);
    const { source, gainNode } = this._makeNode(buffer, 1.0);

    const startTime = this.ctx.currentTime;
    source.start(0);
    source.onended = () => {
      if (this.current && this.current.source === source && this.onEnded) {
        this.onEnded(trackId);
      }
    };

    this.current = { trackId, source, gainNode, buffer, startTime };
    return buffer.duration;
  }

  async crossfadeTo(trackId, url, durationSec = 4) {
    this.resume();
    const buffer = await this._loadBuffer(url);
    const { source, gainNode } = this._makeNode(buffer, 0.0);

    const now = this.ctx.currentTime;
    source.start(0);
    gainNode.gain.setValueAtTime(0.0, now);
    gainNode.gain.linearRampToValueAtTime(1.0, now + durationSec);

    const old = this.current;
    if (old) {
      old.gainNode.gain.cancelScheduledValues(now);
      old.gainNode.gain.setValueAtTime(old.gainNode.gain.value, now);
      old.gainNode.gain.linearRampToValueAtTime(0.0, now + durationSec);
      const oldSource = old.source;
      setTimeout(() => {
        try { oldSource.stop(); } catch (e) { /* already stopped */ }
      }, durationSec * 1000 + 150);
    }

    source.onended = () => {
      if (this.current && this.current.source === source && this.onEnded) {
        this.onEnded(trackId);
      }
    };

    this.current = { trackId, source, gainNode, buffer, startTime: now };
    return buffer.duration;
  }

  getElapsedSec() {
    if (!this.current) return 0;
    return this.ctx.currentTime - this.current.startTime;
  }

  getDurationSec() {
    return this.current ? this.current.buffer.duration : 0;
  }

  getRemainingSec() {
    if (!this.current) return 0;
    return this.getDurationSec() - this.getElapsedSec();
  }

  stop() {
    if (this.current) {
      try { this.current.source.stop(); } catch (e) { /* already stopped */ }
      this.current = null;
    }
  }

  pauseAll() {
    if (this.ctx.state === "running") return this.ctx.suspend();
    return Promise.resolve();
  }

  resumeAll() {
    if (this.ctx.state === "suspended") return this.ctx.resume();
    return Promise.resolve();
  }
}
