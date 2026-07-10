// p5.jsによるジャンル類似度ネットワークの描画(前景レイヤー)。
// ノード=ジャンル、エッジ太さ/濃さ=類似度。クリック時の意味づけはplayer.js側が
// 「同ジャンルか異ジャンルか」を判断して処理する(このクラスはクリック位置の
// ジャンル特定と描画のみを担当する)。

export class NetworkGraph {
  constructor(containerId, { onGenreClick } = {}) {
    this.onGenreClick = onGenreClick;
    this.nodes = [];
    this.edges = [];
    this.currentGenre = null;
    this.positions = {};
    this._p = null;

    const container = document.getElementById(containerId);
    this.p5instance = new window.p5((p) => this._sketch(p), container);
  }

  setNetwork(network) {
    this.nodes = network.nodes || [];
    this.edges = network.edges || [];
    this._layout();
  }

  setCurrentGenre(genre) {
    this.currentGenre = genre;
  }

  _nodeRadius(node) {
    return 26 + Math.min(node.track_count, 10) * 4;
  }

  _layout() {
    if (!this._p) return;
    const n = this.nodes.length;
    const cx = this._p.width / 2;
    const cy = this._p.height / 2;
    const radius = Math.min(cx, cy) * 0.72;
    this.positions = {};
    this.nodes.forEach((node, i) => {
      const angle = (i / Math.max(n, 1)) * Math.PI * 2 - Math.PI / 2;
      this.positions[node.genre] = {
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
      };
    });
  }

  _sketch(p) {
    this._p = p;

    p.setup = () => {
      const container = p.canvas.parentElement;
      p.createCanvas(container.clientWidth, container.clientHeight);
      p.textFont("sans-serif");
      this._layout();
    };

    p.windowResized = () => {
      const container = p.canvas.parentElement;
      p.resizeCanvas(container.clientWidth, container.clientHeight);
      this._layout();
    };

    p.draw = () => {
      p.clear();

      for (const edge of this.edges) {
        const a = this.positions[edge.genre_a];
        const b = this.positions[edge.genre_b];
        if (!a || !b) continue;
        const sim = Math.max(0, Math.min(1, edge.similarity));
        p.stroke(180, 180, 255, 40 + sim * 180);
        p.strokeWeight(0.5 + sim * 3);
        p.line(a.x, a.y, b.x, b.y);
      }

      for (const node of this.nodes) {
        const pos = this.positions[node.genre];
        if (!pos) continue;
        const isCurrent = node.genre === this.currentGenre;
        const r = this._nodeRadius(node);

        p.noStroke();
        p.fill(isCurrent ? p.color(124, 92, 255) : p.color(50, 52, 68));
        p.ellipse(pos.x, pos.y, r, r);

        p.noFill();
        p.stroke(isCurrent ? 255 : 150);
        p.strokeWeight(isCurrent ? 3 : 1);
        p.ellipse(pos.x, pos.y, r, r);

        p.noStroke();
        p.fill(240);
        p.textAlign(p.CENTER, p.CENTER);
        p.textSize(13);
        p.text(`${node.genre}\n(${node.track_count})`, pos.x, pos.y);
      }
    };

    p.mousePressed = () => {
      if (p.mouseX < 0 || p.mouseY < 0 || p.mouseX > p.width || p.mouseY > p.height) return;
      for (const node of this.nodes) {
        const pos = this.positions[node.genre];
        if (!pos) continue;
        const r = this._nodeRadius(node);
        if (p.dist(p.mouseX, p.mouseY, pos.x, pos.y) <= r / 2) {
          if (this.onGenreClick) this.onGenreClick(node.genre);
          return;
        }
      }
    };
  }
}
