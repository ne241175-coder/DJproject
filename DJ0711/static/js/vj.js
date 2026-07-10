// p5.jsによる背景VJ(ジェネラティブビジュアル、背景レイヤー)。
// 見た目自体はプレースホルダー(本格的なデザインは別途詰める前提)。
// ここで重要なのはplayer.jsとのデータ連携の型(updateFrameの引数)を
// 決めておくこと: { elapsedSec, currentBeatIndex, energy, sectionLabel }

export class VJVisual {
  constructor(containerId) {
    this.state = { elapsedSec: 0, energy: 0, sectionLabel: null, beatPulse: 0 };
    this._lastBeatIndex = -1;
    this._p = null;

    const container = document.getElementById(containerId);
    this.p5instance = new window.p5((p) => this._sketch(p), container);
  }

  updateFrame({ elapsedSec = 0, currentBeatIndex = -1, energy = 0, sectionLabel = null } = {}) {
    if (currentBeatIndex !== this._lastBeatIndex) {
      this.state.beatPulse = 1.0;
      this._lastBeatIndex = currentBeatIndex;
    }
    this.state.elapsedSec = elapsedSec;
    this.state.energy = energy;
    this.state.sectionLabel = sectionLabel;
  }

  _sketch(p) {
    this._p = p;

    p.setup = () => {
      const container = p.canvas.parentElement;
      p.createCanvas(container.clientWidth, container.clientHeight);
      p.colorMode(p.HSB, 360, 100, 100, 1);
      p.noStroke();
    };

    p.windowResized = () => {
      const container = p.canvas.parentElement;
      p.resizeCanvas(container.clientWidth, container.clientHeight);
    };

    p.draw = () => {
      const energy = Math.max(0, Math.min(1, this.state.energy));
      const hue = (this.state.elapsedSec * 6) % 360;

      // わずかに前フレームを残すトレイル効果
      p.fill(hue, 40, 8, 0.35);
      p.rect(0, 0, p.width, p.height);

      const pulse = this.state.beatPulse;
      this.state.beatPulse *= 0.85;

      const baseR = Math.min(p.width, p.height) * 0.22;
      const r = baseR * (0.7 + energy * 0.6 + pulse * 0.35);

      p.fill(hue, 70, 55 + energy * 35, 0.55);
      p.ellipse(p.width / 2, p.height / 2, r * 2, r * 2);

      p.fill((hue + 180) % 360, 60, 70, 0.3);
      p.ellipse(p.width / 2, p.height / 2, r * 1.3, r * 1.3);

      if (this.state.sectionLabel) {
        p.fill(0, 0, 100, 0.8);
        p.textAlign(p.CENTER, p.CENTER);
        p.textSize(16);
        p.text(this.state.sectionLabel, p.width / 2, p.height - 28);
      }
    };
  }
}
