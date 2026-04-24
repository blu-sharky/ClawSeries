/**
 * Dubbing module — video dubbing UI
 */

const DubbingView = {
    selectedLang: null,
    selectedVideoPath: null,
    currentTaskId: null,
    pollingTimer: null,

    LANGUAGES: {
        en: "🇺🇸 English", zh: "🇨🇳 Chinese", ja: "🇯🇵 Japanese",
        ko: "🇰🇷 Korean", es: "🇪🇸 Spanish", fr: "🇫🇷 French",
        de: "🇩🇪 German", pt: "🇧🇷 Portuguese", hi: "🇮🇳 Hindi",
        th: "🇹🇭 Thai", ru: "🇷🇺 Russian", ar: "🇸🇦 Arabic",
        it: "🇮🇹 Italian"
    },

    STEPS: [
        { key: "extracting_audio", icon: "🎵", label: "提取音频" },
        { key: "separating_vocals", icon: "🎤", label: "分离人声" },
        { key: "transcribing", icon: "📝", label: "语音转文字" },
        { key: "translating", icon: "🌐", label: "翻译" },
        { key: "generating_speech", icon: "🗣️", label: "生成配音" },
        { key: "merging", icon: "🎬", label: "合成视频" },
    ],

    STEP_MAP: {
        extracting_audio: 0, separating_vocals: 1, transcribing: 2,
        translating: 3, generating_speech: 4, merging: 5,
    },

    async init() {
        this.selectedLang = null;
        this.selectedVideoPath = null;
        this.currentTaskId = null;
        this.render();
        this.loadHistory();
    },

    render() {
        const container = document.getElementById('dubbing-content');
        if (!container) return;

        container.innerHTML = `
            <div class="dubbing-header">
                <h2>AI 多语言配音</h2>
                <p>一键配音整个剧集到指定语言，保持原音色和情感</p>
            </div>
            <div class="dubbing-panel">
                ${this._renderLangSelector()}
                ${this._renderSourceSection()}
                ${this._renderStartButton()}
                <div id="dubbing-progress-area"></div>
                <div id="dubbing-result-area"></div>
            </div>
            <div class="dubbing-history" id="dubbing-history"></div>
        `;
        this._bindEvents();
    },

    _renderLangSelector() {
        const btns = Object.entries(this.LANGUAGES).map(([code, name]) =>
            `<button class="dubbing-lang-btn${this.selectedLang === code ? ' selected' : ''}" data-lang="${code}">${name}</button>`
        ).join('');
        return `
            <div class="dubbing-lang-section">
                <h3>选择目标语言</h3>
                <div class="dubbing-lang-grid">${btns}</div>
            </div>
        `;
    },

    _renderSourceSection() {
        const testVideoExists = true; // test-video.mp4 is in project root
        const selectedFile = this.selectedVideoPath
            ? `<div class="dubbing-selected-file">
                <span class="file-icon">📎</span>
                <span>${this.selectedVideoPath.split('/').pop()}</span>
                <span class="file-remove" onclick="DubbingView.clearVideo()">✕</span>
               </div>`
            : '';
        return `
            <div class="dubbing-source-section">
                <h3>选择视频文件</h3>
                <div class="dubbing-upload-area" id="dubbing-drop-zone">
                    <div class="dubbing-upload-icon">📁</div>
                    <div class="dubbing-upload-text">拖拽视频文件到此处，或点击选择</div>
                    <div class="dubbing-upload-hint">支持 MP4, MOV, AVI, MKV 等格式</div>
                    <input type="file" id="dubbing-file-input" accept="video/*">
                </div>
                ${selectedFile}
                <div class="dubbing-test-mode">
                    <label class="toggle-switch">
                        <input type="checkbox" id="dubbing-use-test-video">
                        <span class="toggle-slider"></span>
                    </label>
                    <label for="dubbing-use-test-video">使用内置测试视频 (test-video.mp4)</label>
                </div>
            </div>
        `;
    },

    _renderStartButton() {
        return `
            <div class="dubbing-start-section">
                <button class="dubbing-start-btn" id="dubbing-start-btn" onclick="DubbingView.startDubbing()" disabled>
                    🎬 开始配音
                </button>
            </div>
        `;
    },

    _renderProgress(status) {
        const pct = status.progress || 0;
        const currentStep = status.current_step || status.status || '';
        const stepIdx = this.STEP_MAP[status.status] ?? -1;

        const stepsHtml = this.STEPS.map((s, i) => {
            let cls = '';
            if (i < stepIdx) cls = 'done';
            else if (i === stepIdx) cls = 'active';
            if (status.status === 'failed' && i === stepIdx) cls = 'error';
            return `<div class="dubbing-step ${cls}">
                <span class="dubbing-step-icon">${cls === 'done' ? '✓' : s.icon}</span>
                <span>${s.label}</span>
            </div>`;
        }).join('');

        return `
            <div class="dubbing-progress-section">
                <div class="dubbing-progress-header">
                    <h3>${currentStep || '处理中...'}</h3>
                    <span class="dubbing-progress-percent">${pct}%</span>
                </div>
                <div class="dubbing-progress-bar">
                    <div class="dubbing-progress-fill" style="width: ${pct}%"></div>
                </div>
                <div class="dubbing-progress-steps">${stepsHtml}</div>
            </div>
        `;
    },

    _renderResult(status) {
        const taskId = status.task_id;
        const targetLang = this.LANGUAGES[status.target_language] || status.target_language;
        const videoUrl = `http://localhost:8000/api/v1/dubbing/${taskId}/download`;
        return `
            <div class="dubbing-result-section">
                <h3>✓ 配音完成</h3>
                <p>目标语言: ${targetLang}</p>
                <div class="dubbing-result-video">
                    <video controls src="${videoUrl}"></video>
                </div>
                <div class="dubbing-result-actions">
                    <a class="btn-primary" href="${videoUrl}" download style="text-decoration:none;padding:10px 24px;border-radius:8px;font-size:14px;">⬇ 下载配音视频</a>
                    <button class="btn-secondary" onclick="DubbingView.init()">🔄 再次配音</button>
                </div>
            </div>
        `;
    },

    _renderError(status) {
        return `
            <div class="dubbing-error">
                <h3>✗ 配音失败</h3>
                <p>${status.error_message || '未知错误'}</p>
                <button class="btn-secondary" style="margin-top:12px" onclick="DubbingView.init()">重试</button>
            </div>
        `;
    },

    _bindEvents() {
        // Language selection
        const langGrid = document.querySelector('.dubbing-lang-grid');
        if (langGrid) {
            langGrid.addEventListener('click', (e) => {
                const btn = e.target.closest('.dubbing-lang-btn');
                if (!btn) return;
                this.selectedLang = btn.dataset.lang;
                langGrid.querySelectorAll('.dubbing-lang-btn').forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');
                this._updateStartButton();
            });
        }

        // File upload
        const fileInput = document.getElementById('dubbing-file-input');
        if (fileInput) {
            fileInput.addEventListener('change', (e) => this._handleFileUpload(e.target.files[0]));
        }

        // Drag and drop
        const dropZone = document.getElementById('dubbing-drop-zone');
        if (dropZone) {
            dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
            dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
            dropZone.addEventListener('drop', (e) => {
                e.preventDefault();
                dropZone.classList.remove('drag-over');
                if (e.dataTransfer.files.length) this._handleFileUpload(e.dataTransfer.files[0]);
            });
        }

        // Test video toggle
        const testToggle = document.getElementById('dubbing-use-test-video');
        if (testToggle) {
            testToggle.addEventListener('change', (e) => {
                if (e.target.checked) {
                    this.selectedVideoPath = 'test-video.mp4';
                } else {
                    this.selectedVideoPath = null;
                }
                this._updateSourceDisplay();
                this._updateStartButton();
            });
        }
    },

    async _handleFileUpload(file) {
        if (!file) return;
        try {
            const formData = new FormData();
            formData.append('file', file);
            const res = await fetch('http://localhost:8000/api/v1/dubbing/upload', {
                method: 'POST',
                body: formData,
            });
            const data = await res.json();
            this.selectedVideoPath = data.path;
            this._updateSourceDisplay();
            this._updateStartButton();
        } catch (err) {
            alert('上传失败: ' + err.message);
        }
    },

    _updateSourceDisplay() {
        const section = document.querySelector('.dubbing-source-section');
        if (!section) return;
        const existing = section.querySelector('.dubbing-selected-file');
        if (existing) existing.remove();

        if (this.selectedVideoPath) {
            const div = document.createElement('div');
            div.className = 'dubbing-selected-file';
            div.innerHTML = `
                <span class="file-icon">📎</span>
                <span>${this.selectedVideoPath.split('/').pop()}</span>
                <span class="file-remove" onclick="DubbingView.clearVideo()">✕</span>
            `;
            section.querySelector('.dubbing-upload-area').after(div);
        }
    },

    _updateStartButton() {
        const btn = document.getElementById('dubbing-start-btn');
        if (!btn) return;
        btn.disabled = !(this.selectedLang && this.selectedVideoPath);
    },

    clearVideo() {
        this.selectedVideoPath = null;
        const testToggle = document.getElementById('dubbing-use-test-video');
        if (testToggle) testToggle.checked = false;
        this._updateSourceDisplay();
        this._updateStartButton();
    },

    async startDubbing() {
        if (!this.selectedLang || !this.selectedVideoPath) return;

        const btn = document.getElementById('dubbing-start-btn');
        if (btn) { btn.disabled = true; btn.textContent = '⏳ 启动中...'; }

        try {
            const res = await fetch('http://localhost:8000/api/v1/dubbing/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_path: this.selectedVideoPath,
                    target_language: this.selectedLang,
                }),
            });
            const data = await res.json();
            if (data.task_id) {
                this.currentTaskId = data.task_id;
                this._startPolling(data.task_id);
            } else {
                alert('启动失败: ' + (data.detail || JSON.stringify(data)));
                if (btn) { btn.disabled = false; btn.textContent = '🎬 开始配音'; }
            }
        } catch (err) {
            alert('启动失败: ' + err.message);
            if (btn) { btn.disabled = false; btn.textContent = '🎬 开始配音'; }
        }
    },

    _startPolling(taskId) {
        // Hide start section, show progress
        const startSection = document.querySelector('.dubbing-start-section');
        if (startSection) startSection.style.display = 'none';

        this._pollStatus(taskId);
    },

    async _pollStatus(taskId) {
        try {
            const res = await fetch(`http://localhost:8000/api/v1/dubbing/${taskId}`);
            const status = await res.json();

            const progressArea = document.getElementById('dubbing-progress-area');
            const resultArea = document.getElementById('dubbing-result-area');

            if (status.status === 'completed') {
                if (progressArea) progressArea.innerHTML = this._renderProgress({ ...status, progress: 100 });
                if (resultArea) resultArea.innerHTML = this._renderResult(status);
                this.loadHistory();
                return; // stop polling
            }

            if (status.status === 'failed') {
                if (progressArea) progressArea.innerHTML = '';
                if (resultArea) resultArea.innerHTML = this._renderError(status);
                this.loadHistory();
                return; // stop polling
            }

            // Still running
            if (progressArea) progressArea.innerHTML = this._renderProgress(status);
            if (resultArea) resultArea.innerHTML = '';

            // Poll again
            this.pollingTimer = setTimeout(() => this._pollStatus(taskId), 2000);
        } catch (err) {
            console.error('Poll error:', err);
            this.pollingTimer = setTimeout(() => this._pollStatus(taskId), 5000);
        }
    },

    async loadHistory() {
        const container = document.getElementById('dubbing-history');
        if (!container) return;

        try {
            const res = await fetch('http://localhost:8000/api/v1/dubbing');
            const data = await res.json();

            if (!data.tasks || data.tasks.length === 0) {
                container.innerHTML = '';
                return;
            }

            const statusMap = {
                completed: 'completed', failed: 'failed',
                pending: 'pending', extracting_audio: 'in-progress',
                separating_vocals: 'in-progress', transcribing: 'in-progress',
                translating: 'in-progress', generating_speech: 'in-progress',
                merging: 'in-progress',
            };

            const items = data.tasks.map(t => {
                const sClass = statusMap[t.status] || 'pending';
                const lang = this.LANGUAGES[t.target_language] || t.target_language;
                const time = t.created_at ? new Date(t.created_at).toLocaleString('zh-CN') : '';
                return `<div class="dubbing-history-item">
                    <div class="dubbing-history-status ${sClass}"></div>
                    <div class="dubbing-history-info">
                        <span>${t.source_video_path.split('/').pop()}</span>
                        <span class="lang-badge">${lang} · ${time}</span>
                    </div>
                    <div class="dubbing-history-actions">
                        ${t.status === 'completed' ? `<a class="btn-secondary btn-sm" href="http://localhost:8000/api/v1/dubbing/${t.task_id}/download" download>下载</a>` : ''}
                        ${['pending','extracting_audio','separating_vocals','transcribing','translating','generating_speech','merging'].includes(t.status) ? `<button class="btn-secondary btn-sm" onclick="DubbingView.watchTask('${t.task_id}')">查看</button>` : ''}
                    </div>
                </div>`;
            }).join('');

            container.innerHTML = `<h3>配音历史</h3><div class="dubbing-history-list">${items}</div>`;
        } catch (err) {
            container.innerHTML = '';
        }
    },

    watchTask(taskId) {
        this.currentTaskId = taskId;
        const startSection = document.querySelector('.dubbing-start-section');
        if (startSection) startSection.style.display = 'none';
        this._pollStatus(taskId);
    },

    destroy() {
        if (this.pollingTimer) {
            clearTimeout(this.pollingTimer);
            this.pollingTimer = null;
        }
    },
};
