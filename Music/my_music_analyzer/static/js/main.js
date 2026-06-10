document.getElementById('analyze-btn').addEventListener('click', async () => {
    const url = document.getElementById('youtube-url').value;
    if (!url) return alert('URLを入力してください');

    const loading = document.getElementById('loading');
    const result = document.getElementById('result');
    const genreList = document.getElementById('genre-list');

    // 画面表示のリセット
    loading.classList.remove('hidden');
    result.classList.add('hidden');
    genreList.innerHTML = '';

    try {
        // Pythonサーバー（/analyze）に非同期リクエストを送信
        const response = await fetch('/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });
        
        const data = await response.json();

        if (data.success) {
            // 結果を画面に反映
            document.getElementById('bpm-value').innerText = data.bpm;
            
            // ジャンル確率のリストを生成
            for (const [genre, percent] of Object.entries(data.genres)) {
                const li = document.createElement('li');
                li.innerHTML = `<strong>${genre}</strong>: ${percent}%`;
                genreList.appendChild(li);
            }
            
            result.classList.remove('hidden');
        } else {
            alert('解析に失敗しました: ' + data.error);
        }
    } catch (error) {
        alert('通信エラーが発生しました');
    } finally {
        loading.classList.add('hidden');
    }
});
