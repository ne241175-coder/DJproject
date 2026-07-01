// ==========================================
// 1. データ定義（曲調マップのノード情報）
// ==========================================
// 点の座標(x, y)と、それに対応する音楽ファイル、BPM、色を定義します
const nodes = [
    { id: 1, name: "Chill Beat", x: 200, y: 300, audioPath: "audio/track1.mp3", bpm: 90, color: [0, 255, 255] },
    { id: 2, name: "Main House", x: 400, y: 200, audioPath: "audio/track2.mp3", bpm: 124, color: [255, 0, 128] },
    { id: 3, name: "Techno Peak", x: 600, y: 350, audioPath: "audio/track3.mp3", bpm: 130, color: [128, 0, 255] }
];

// 線でつなぐペア（近い曲調同士を結ぶ）
const connections = [
    { from: 1, to: 2 },
    { from: 2, to: 3 }
];

// ==========================================
// 2. グローバル変数
// ==========================================
let currentSound = null;
let fft; // 音声解析用オブジェクト
let activeNode = null;
let targetVolume = 1.0;
let currentVolume = 1.0;
let isStarted = false;
let vjPulse = 0; // VJの弾けるエフェクト用変数

// ==========================================
// 3. p5.js メインロジック
// ==========================================
function setup() {
    createCanvas(windowWidth, windowHeight);
    
    // 音声解析（FFT）の初期化
    fft = new p5.FFT();
    
    // スタートボタンの処理
    document.getElementById("start-btn").addEventListener("click", () => {
        isStarted = true;
        document.getElementById("start-overlay").style.display = "none";
        // 初期曲として最初のノードを再生
        switchTrack(nodes[0]);
    });
}

function draw() {
    // ------------------------------------------
    // 【VJ機能】音声解析データで背景を描画（旧VJの役割）
    // ------------------------------------------
    // 音声を解析（音量・周波数）
    fft.analyze();
    let bass = fft.getEnergy("bass");     // 低音の強さ (0〜255)
    let treble = fft.getEnergy("treble"); // 高音の強さ (0〜255)
    
    // 音量（エネルギー）に合わせてVJのパルス（ブレ）を計算
    vjPulse = map(bass, 0, 255, 0, 150);
    
    // 背景の描画（BPMと音量で色と透明度が変わるサイケデリックな背景）
    let bpmSpeed = activeNode ? activeNode.bpm / 60 : 1;
    let bgColor = activeNode ? activeNode.color : [20, 20, 20];
    
    background(bgColor[0] * 0.1, bgColor[1] * 0.1, bgColor[2] * 0.1, 40); // 残像エフェクト
    
    // 音楽と連動して動く背景の円（VJエフェクト）
    push();
    translate(width / 2, height / 2);
    noFill();
    strokeWeight(2 + treble / 50);
    // 現在の曲の色をベースにサイケデリックな円を描く
    for (let i = 0; i < 5; i++) {
        stroke(bgColor[0], bgColor[1], bgColor[2], 255 - i * 40);
        let size = (sin(frameCount * 0.02 * bpmSpeed + i) * 200) + vjPulse * (i + 1) * 0.5;
        ellipse(0, 0, abs(size), abs(size));
    }
    pop();

    // ------------------------------------------
    // 【DJマップ機能】点と線のマップを描画（旧dj-music-mapの役割）
    // ------------------------------------------
    if (!isStarted) return;

    // 線（コネクション）の描画
    stroke(255, 255, 255, 80);
    strokeWeight(2);
    for (let conn of connections) {
        let fromNode = nodes.find(n => n.id === conn.from);
        let toNode = nodes.find(n => n.id === conn.to);
        line(fromNode.x, fromNode.y, toNode.x, toNode.y);
    }

    // 点（ノード）の描画
    for (let node of nodes) {
        // 選択中のノードは大きく光らせる
        if (activeNode && activeNode.id === node.id) {
            fill(node.color[0], node.color[1], node.color[2], 200);
            stroke(255);
            strokeWeight(4);
            ellipse(node.x, node.y, 40 + vjPulse * 0.2, 40 + vjPulse * 0.2); // 音に合わせて点も弾ける
        } else {
            fill(node.color[0], node.color[1], node.color[2], 120);
            noStroke();
            ellipse(node.x, node.y, 25, 25);
        }
        
        // 曲名のテキスト表示
        fill(255);
        noStroke();
        textAlign(CENTER);
        text(node.name, node.x, node.y - 25);
        text(`BPM: ${node.bpm}`, node.x, node.y + 30);
    }

    // 滑らかな音量制御（クロスフェード処理用）
    if (currentSound) {
        currentVolume = lerp(currentVolume, targetVolume, 0.05);
        currentSound.setVolume(currentVolume);
    }
}

// ------------------------------------------
// 4. DJインタラクション（クリックで曲変更）
// ------------------------------------------
function mousePressed() {
    if (!isStarted) return;

    // クリックされた位置が、どなかの点（ノード）に近いかチェック
    for (let node of nodes) {
        let d = dist(mouseX, mouseY, node.x, node.y);
        if (d < 25) { // 点の当たり判定
            if (!activeNode || activeNode.id !== node.id) {
                switchTrack(node);
            }
            break;
        }
    }
}

// 曲を切り替える（DJミックス）関数
function switchTrack(node) {
    activeNode = node;
    console.log(`Now Playing: ${node.name} (BPM: ${node.bpm})`);

    // もしすでに曲が流れていたら停止
    if (currentSound) {
        currentSound.stop();
    }

    // p5.soundで新しい音源を読み込んで再生
    currentSound = loadSound(node.audioPath, () => {
        currentSound.loop(); // ループ再生
        currentVolume = 1.0;
        currentSound.setVolume(currentVolume);
    });
}

// 画面サイズが変わったらキャンバスも自動追従
function windowResized() {
    resizeCanvas(windowWidth, windowHeight);
}
