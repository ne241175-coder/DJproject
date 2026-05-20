// --- ピアノ演奏・音源コントロール ---
let audioCtx = null;
let activeNotes = new Map(); // 現在押されている音のリスト (ID -> true)
let playingOscillators = new Map(); // 実際のWeb Audio音源 (ID -> {osc, gain})
var add = 0;
var pool = [];

// 鍵盤カラーデータ
var grn={21:"#004A00",22:"#004E00",23:"#005200",24:"#005600",25:"#005A00",26:"#005F00",27:"#006300",28:"#006700",29:"#006B00",30:"#006F00",31:"#007400",32:"#007800",33:"#007C00",34:"#008000",35:"#008400",36:"#008900",37:"#008D00",38:"#009100",39:"#009500",40:"#009900",41:"#009E00",42:"#00A200",43:"#00A600",44:"#00AA00",45:"#00AF00",46:"#00B300",47:"#00B700",48:"#00BB00",49:"#00BF00",50:"#00C400",51:"#00C800",52:"#00CC00",53:"#00D000",54:"#00D400",55:"#00D900",56:"#00DD00",57:"#00E100",58:"#00E500",59:"#00E900",60:"#00EE00",61:"#00F200",62:"#00F600",63:"#00FA00",64:"#00FF00",65:"#00ff00",66:"#05ff05",67:"#0bff0b",68:"#10ff10",69:"#16ff16",70:"#1Bff1B",71:"#21ff21",72:"#27ff27",73:"#2Cff2C",74:"#32ff32",75:"#37ff37",76:"#3Dff3D",77:"#42ff42",78:"#48ff48",79:"#4Eff4E",80:"#53ff53",81:"#59ff59",82:"#5Eff5E",83:"#64ff64",84:"#6Aff6A",85:"#6Fff6F",86:"#75ff75",87:"#7Aff7A",88:"#80ff80",89:"#85ff85",90:"#8Bff8B",91:"#91ff91",92:"#96ff96",93:"#9Cff9C",94:"#A1ffA1",95:"#A7ffA7",96:"#ADffAD",97:"#B2ffB2",98:"#B8ffB8",99:"#BDffBD",100:"#C3ffC3",101:"#C8ffC8",102:"#CEffCE",103:"#D4ffD4",104:"#D6ffD6",105:"#D8ffD8",106:"#DAffDA",107:"#DCffDC",108:"#DEffDE"};
var idcolor={21:"wh",23:"wh",24:"wh",26:"wh",28:"wh",29:"wh",31:"wh",33:"wh",35:"wh",36:"wh",38:"wh",40:"wh",41:"wh",43:"wh",45:"wh",47:"wh",48:"wh",50:"wh",52:"wh",53:"wh",55:"wh",57:"wh",59:"wh",60:"wh",62:"wh",64:"wh",65:"wh",67:"wh",69:"wh",71:"wh",72:"wh",74:"wh",76:"wh",77:"wh",79:"wh",81:"wh",83:"wh",84:"wh",86:"wh",88:"wh",89:"wh",91:"wh",93:"wh",95:"wh",96:"wh",98:"wh",100:"wh",101:"wh",103:"wh",105:"wh",107:"wh",108:"wh",22:"bl",25:"bl",27:"bl",30:"bl",32:"bl",34:"bl",37:"bl",39:"bl",42:"bl",44:"bl",46:"bl",49:"bl",51:"bl",54:"bl",56:"bl",58:"bl",61:"bl",63:"bl",66:"bl",68:"bl",70:"bl",73:"bl",75:"bl",78:"bl",80:"bl",82:"bl",85:"bl",87:"bl",90:"bl",92:"bl",94:"bl",97:"bl",99:"bl",102:"bl",104:"bl",106:"bl"};
var keycode={"KeyA":44,"KeyZ":45,"KeyS":46,"KeyX":47,"KeyC":48,"KeyF":49,"KeyV":50,"KeyG":51,"KeyB":52,"KeyN":53,"KeyJ":54,"KeyM":55,"Digit1":56,"KeyK":56,"Comma":57,"KeyQ":57,"KeyL":58,"Digit2":58,"Period":59,"KeyW":59,"Slash":60,"KeyE":60,"Quote":61,"Digit4":61,"IntlRo":62,"KeyR":62,"Backslash":63,"Digit5":63,"KeyT":64,"KeyY":65,"Digit7":66,"KeyU":67,"Digit8":68,"KeyI":69,"Digit9":70,"KeyO":71,"KeyP":72,"Minus":73,"BracketLeft":74,"Equal":75,"BracketRight":76};

function initAudio() {
  if (audioCtx === null) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
}

function getFrequency(n) {
  return 440 * Math.pow(2, (n - 69) / 12);
}

function sub_playSound(id) {
  initAudio();
  if (playingOscillators.has(id)) return; 

  const rawFreq = getFrequency(Number(id));

  // 押された音を記録
  activeNotes.set(id, true);
  
  // コード判定関数の呼び出し（chord-finder.js内の関数）
  if (typeof updateChordAnalysis === "function") {
      updateChordAnalysis();
  }

  // 鍵盤の色変更
  if(document.getElementById(id)) document.getElementById(id).style.backgroundColor = grn[id];
  
  var vlm = document.getElementById("vol_piano").value;
  var avlm = Number(vlm) * 0.1;

  const oscillator = audioCtx.createOscillator();
  const gainNode = audioCtx.createGain();

  oscillator.type = 'triangle'; 
  oscillator.frequency.setValueAtTime(rawFreq, audioCtx.currentTime);
  gainNode.gain.setValueAtTime(avlm, audioCtx.currentTime);

  oscillator.connect(gainNode);
  gainNode.connect(audioCtx.destination);
  oscillator.start();

  playingOscillators.set(id, {osc: oscillator, gain: gainNode});
}

function sub_stopSound(id) {
  const sound = playingOscillators.get(id);
  if (sound) {
    sound.gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.1);
    sound.osc.stop(audioCtx.currentTime + 0.12);
    playingOscillators.delete(id);
    
    // 離された音をデータから削除
    activeNotes.delete(id);
    
    // コード判定関数の再呼び出し
    if (typeof updateChordAnalysis === "function") {
        updateChordAnalysis();
    }
  }
}

// マウスイベントリスナーの設定
window.addEventListener('DOMContentLoaded', function() {
  const wk = document.getElementsByClassName('wk');
  const bk = document.getElementsByClassName('bk');

  const setup = (list, defColor) => {
    for (let i = 0; i < list.length; i++) {
      list[i].addEventListener("mousedown", function() { sub_playSound(Number(this.id)); });
      list[i].addEventListener("mouseup", function() { 
        sub_stopSound(Number(this.id));
        this.style.backgroundColor = defColor; 
      });
      list[i].addEventListener("mouseout", function() { 
        sub_stopSound(Number(this.id));
        this.style.backgroundColor = defColor; 
      });
    }
  };
  setup(wk, "#fff");
  setup(bk, "#000");
});

// PCキーボード操作のリスナー
window.addEventListener('keydown', function(e) {
  const kid = keycode[e.code] ? keycode[e.code] + add : null;
  if (kid && pool[kid] == undefined) {
    sub_playSound(kid);
    pool[kid] = 1;
  }
});

window.addEventListener('keyup', function(e) {
  const kid = keycode[e.code] ? keycode[e.code] + add : null;
  if (kid) {
    sub_stopSound(kid); 
    const box = document.getElementById(kid);
    if (box) box.style.backgroundColor = idcolor[kid] === "bl" ? "#000" : "#fff";
    pool[kid] = undefined;
  }
});

function pianovlm(n) {
  let v = Number(document.getElementById("vol_piano").value) + n;
  document.getElementById("vol_piano").value = Math.max(0, Math.min(10, v));
}