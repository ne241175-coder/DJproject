// --- コード判定アルゴリズム専用ロジック ---

const noteNames = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];

const chordDict = {
    "0,7": "5", // パワーコード
    "0,4,7": "M",
    "0,3,7": "m",
    "0,3,6": "dim",
    "0,4,8": "aug",
    "0,4,7,11": "M7",
    "0,3,7,10": "m7",
    "0,4,7,10": "7",
    "0,3,6,10": "m7-5",
    "0,3,6,9": "dim7",
    "0,3,7,9": "m6",
    "0,4,8,11": "augM7",
    "0,4,8,10": "aug7",
};

// ピアノ側で押されている音（activeNotes）を元に画面表示を更新する
function updateChordAnalysis() {
  const chordResultDiv = document.getElementById('chord-result');
  const displayContentDiv = document.getElementById('display-content');
  
  // piano.js側にある activeNotes のデータ数を確認
  if (!activeNotes || activeNotes.size === 0) {
    chordResultDiv.innerText = "--";
    displayContentDiv.innerText = "鍵盤を押すとコードを判定します";
    return;
  }

  // 現在押されているMIDIノート番号の配列を取得して低い順にソート
  let inputNotes = Array.from(activeNotes.keys()).sort((a, b) => a - b);
  
  // 構成音の名前一覧をテキスト化 (例: "C, E, G")
  let currentNoteNames = inputNotes.map(n => noteNames[(n - 12) % 12]);
  displayContentDiv.innerText = "構成音: " + currentNoteNames.join(", ");

  // 最低音（ベース音）を取得
  const bassNote = noteNames[(inputNotes[0] - 12) % 12];
  let foundChord = null;
  let rootName = "";

  // 転回形を考慮し、押されている全ての音をルート候補としてループ検証
  for (let i = 0; i < inputNotes.length; i++) {
      let potentialRoot = (inputNotes[i] - 12) % 12;
      
      // 各音のルートからの相対的な半音数を計算 (0〜11に収める)
      let relative = inputNotes.map(n => ((n - 12) % 12 - potentialRoot + 12) % 12);
      
      // 判定対象の度数（1度、短3、長3、減5、完全5、増5、長6、短7、長7）
      let basicDegrees = [0, 3, 4, 6, 7, 8, 9, 10, 11]; 
      let filteredRelative = relative.filter(n => basicDegrees.includes(n));

      // 重複音を排除してソートし、文字列のキーにする (例: "0,4,7")
      let uniqueSorted = [...new Set(filteredRelative)].sort((a, b) => a - b);
      let key = uniqueSorted.join(",");

      // 辞書に一致するコード形があれば確定
      if (chordDict[key]) {
          foundChord = chordDict[key];
          rootName = noteNames[potentialRoot];
          break; 
      }
  }

  // 結果をHTMLディスプレイに反映
  if (!foundChord) {
      chordResultDiv.innerText = "???";
  } else {
      let result = rootName + " " + foundChord;
      // 分数コード (オンコード) の判定
      if (rootName !== bassNote) {
          result += " / " + bassNote;
      }
      chordResultDiv.innerText = result;
  }
}