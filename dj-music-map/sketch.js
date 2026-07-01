// --- データ設定 ---
let nodes = [];
let targetCenterNodeId = 'rock'; // 現在中心にいるノードID
let selectedNodeId = null;       // 【変更】現在1クリック目で「選択（ロックオン）」されているノードID

const nodeSize = 60; // 点の大きさ（半径）
const ease = 0.08;   // 移動の滑らかさ
const pulseSpeed = 0.05; // 鼓動のスピード
const pulseRange = 6;  // 鼓動の範囲

// データ本体 (名前,ID,初期のtarget座標)
let nodeData = {
  'rock':    { label: "Rock",    targetX: 0,   targetY: 0 },
  'classic': { label: "Classic", targetX: 0,   targetY: -150 },
  'jpop':    { label: "Jpop",    targetX: -200, targetY: 100 },
  'funk':    { label: "Funk",    targetX: 50,  targetY: 200 },
  'fusion':  { label: "Fusion",  targetX: 300, targetY: 170 },
  'math':    { label: "Math\nRock", targetX: 250, targetY: -60 },
  'jazz':    { label: "Jazz",    targetX: 210, targetY: -220 }
};

// 接続データ (IDペアの配列)
const connections = [
  ['rock', 'classic'],
  ['rock', 'jpop'],
  ['rock', 'funk'],
  ['rock', 'fusion'],
  ['rock', 'math'],
  ['math', 'jazz']
];

function setup() {
  createCanvas(windowWidth, windowHeight);
  
  // 初期データの構築
  for (let id in nodeData) {
    let data = nodeData[id];
    nodes.push({
      id: id,
      label: data.label,
      x: data.targetX, 
      y: data.targetY,
      targetX: data.targetX,
      targetY: data.targetY
    });
  }
}

function draw() {
  background(245);

  // キャンバスの中心を(0,0)にずらす
  translate(width / 2, height / 2);

  // --- 1. アニメーション計算 ---
  for (let node of nodes) {
    node.x += (node.targetX - node.x) * ease;
    node.y += (node.targetY - node.y) * ease;
  }

  // --- 2. 線の描画 ---
  stroke(100);
  strokeWeight(2);
  noFill();

  for (let conn of connections) {
    let nodeA = findNodeById(conn[0]);
    let nodeB = findNodeById(conn[1]);
    if (nodeA && nodeB) {
      line(nodeA.x, nodeA.y, nodeB.x, nodeB.y);
    }
  }

  // --- 3. 点（円）の描画 ---
  for (let node of nodes) {
    stroke(0);
    strokeWeight(2);
    fill(255);

    // 基本のサイズ
    let d = nodeSize;

    // 【中心にいるジャンル】は常にフワフワと鼓動させる
    if (node.id === targetCenterNodeId) {
      d = nodeSize + sin(frameCount * pulseSpeed) * pulseRange;
    }
    
    ellipse(node.x, node.y, d, d);

    // 【1回クリックされて選択中（ロックオン）のジャンル】に枠線を表示
    if (node.id === selectedNodeId) {
      noFill();
      stroke(0); // 黒い太枠（色をつけたい場合はここを変える）
      strokeWeight(3);
      // 選択枠も少し大きめに表示して目立たせる
      ellipse(node.x, node.y, nodeSize + 12, nodeSize + 12);
    }
  }

  // --- 4. 文字の描画 ---
  noStroke();
  fill(0);
  textAlign(CENTER, CENTER);
  textSize(14);
  
  for (let node of nodes) {
    text(node.label, node.x, node.y);
  }
}

// --- イベント処理 ---

function mousePressed() {
  // マウス座標をキャンバスの中心基準に直す
  let mx = mouseX - width / 2;
  let my = mouseY - height / 2;

  // どの点がクリックされたか判定
  for (let node of nodes) {
    let d = dist(mx, my, node.x, node.y);
    
    if (d < nodeSize / 2) {
      // 現在中心にいるジャンルをクリックした場合は何もしない
      if (node.id === targetCenterNodeId) break;

      // 【判定ロジック】
      // すでに選択（ロックオン）されているジャンルを、もう一度クリックした場合
      if (node.id === selectedNodeId) {
        // かつ、現在の中心と繋がっていれば移動する
        if (isConnected(targetCenterNodeId, node.id)) {
          setNewCenter(node.id);
          selectedNodeId = null; // 移動したらロックオンは解除
        } else {
          console.log(`直接繋がっていないため移動できません。`);
        }
      } 
      // まだ選択されていないジャンルを初めてクリックした場合
      else {
        // 繋がっているジャンルしか選択できないようにする
        if (isConnected(targetCenterNodeId, node.id)) {
          selectedNodeId = node.id; // ロックオン状態にする
        } else {
          console.log(`繋がっていないジャンルは選択できません。`);
        }
      }
      break;
    }
  }
}

// --- 補助関数 ---

function isConnected(idA, idB) {
  for (let conn of connections) {
    if ((conn[0] === idA && conn[1] === idB) || (conn[0] === idB && conn[1] === idA)) {
      return true;
    }
  }
  return false;
}

function findNodeById(id) {
  return nodes.find(n => n.id === id);
}

function setNewCenter(newCenterId) {
  let newCenterNode = findNodeById(newCenterId);
  if (!newCenterNode) return;

  newCenterNode.targetX = 0;
  newCenterNode.targetY = 0;
  
  for (let node of nodes) {
    if (node.id === newCenterId) continue;
    
    let originalData = nodeData[node.id];
    let centerData = nodeData[newCenterId];
    
    node.targetX = originalData.targetX - centerData.targetX;
    node.targetY = originalData.targetY - centerData.targetY;
  }
  
  targetCenterNodeId = newCenterId;
}

function windowResized() {
  resizeCanvas(windowWidth, windowHeight);
}