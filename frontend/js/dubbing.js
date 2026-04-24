/**
 * Dubbing module — video dubbing UI with project selection and batch dubbing
 */

const DubbingView = {
    selectedLang: null,
    selectedVideoPath: null,
    currentTaskId: null,
    pollingTimer: null,
    batchTaskIds: [],
    demoMode: false,
    completedProjects: [],
    selectedProject: null,
    selectedEpisodes: new Set(),

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
        this.batchTaskIds = [];
        this.selectedProject = null;
        this.selectedEpisodes = new Set();

        // Load settings to check demo mode
        try {
            const res = await fetch('http://localhost:8000/api/v1/settings/models');
            const data = await res.json();
            this.demoMode = data.dubbing_test_mode === true || data.dubbing_test_mode === "true";
        } catch (e) {
            this.demoMode = false;
        }

        this.render();

        if (!this.demoMode) {
            this.loadCompletedProjects();
        }
        this.loadHistory();
    },

    render() {
        const container = document.getElementById('dubbing-content');
        if (!container) return;

        container.innerHTML = `
            <div class="dubbing-header">
                <h2>AI 多语言配音</h2>
                <p>${this.demoMode
                    ? 'Demo 模式 — 可上传视频或使用内置测试视频'
                    : '选择已完成的短剧项目，一键或逐集配音到指定语言'}</p>
            </div>
            <div class="dubbing-panel">
                ${this._renderLangSelector()}
                ${this.demoMode ? this._renderDemoSourceSection() : this._renderProjectSelector()}
                ${this._renderStartButton()}
                <div id="dubbing-progress-area"></div>
                <div id="dubbing-result-area"></div>
            </div>
            <div class="dubbing-history" id="dubbing-history"></div>
        `;
        this._bindEvents();
    },

    // ── Language selector ────────────────────────────────────────────────
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

    // ── Demo mode source (file upload + test video) ──────────────────────
    _renderDemoSourceSection() {
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

    // ── Project selector (non-demo mode) ─────────────────────────────────
    _renderProjectSelector() {
        if (this.completedProjects.length === 0) {
            return `
                <div class="dubbing-source-section">
                    <h3>选择短剧项目</h3>
                    <div class="dubbing-empty-state">
                        <div class="dubbing-empty-icon">📺</div>
                        <p>暂无已完成的短剧项目</p>
                        <p class="dubbing-empty-hint">请先在"制作"流程中完成一个短剧项目，然后在此处进行配音</p>
                    </div>
                </div>
            `;
        }

        const projectCards = this.completedProjects.map(p => {
            const isSelected = this.selectedProject === p.project_id;
            return `
                <div class="dubbing-project-card${isSelected ? ' selected' : ''}" data-project-id="${p.project_id}">
                    <div class="dubbing-project-info">
                        <h4>${p.title}</h4>
                        <span class="dubbing-project-meta">${p.episodes.length} 集</span>
                    </div>
                    ${isSelected ? this._renderEpisodeList(p) : ''}
                </div>
            `;
        }).join('');

        return `
            <div class="dubbing-source-section">
                <h3>选择短剧项目</h3>
                <div class="dubbing-project-list">${projectCards}</div>
            </div>
        `;
    },

    _renderEpisodeList(project) {
        const allSelected = project.episodes.every(ep => this.selectedEpisodes.has(ep.episode_id));
        const items = project.episodes.map(ep => {
            const checked = this.selectedEpisodes.has(ep.episode_id) ? 'checked' : '';
            const dubCount = ep.dubbing_tasks ? ep.dubbing_tasks.length : 0;
            const dubInfo = dubCount > 0
                ? `<span class="dubbing-ep-dub-count">${dubCount} 个配音任务</span>`
                : '';
            return `
                <div class="dubbing-episode-item">
                    <label class="dubbing-episode-label">
                        <input type="checkbox" class="dubbing-ep-checkbox" data-ep-id="${ep.episode_id}" ${checked}>
                        <span>第${ep.episode_number}集: ${ep.title}</span>
                    </label>
                    ${dubInfo}
                </div>
            `;
        }).join('');

        return `
            <div class="dubbing-episode-list">
                <div class="dubbing-episode-header">
                    <label class="dubbing-episode-label">
                        <input type="checkbox" class="dubbing-ep-select-all" ${allSelected ? 'checked' : ''}>
                        <span class="dubbing-select-all-text">全选</span>
                    </label>
                </div>
                ${items}
            </div>
        `;
    },

    // ── Start button ─────────────────────────────────────────────────────
    _renderStartButton() {
        return `
            <div class="dubbing-start-section">
                <button class="dubbing-start-btn" id="dubbing-start-btn" onclick="DubbingView.startDubbing()" disabled>
                    🎬 开始配音
                </button>
            </div>
        `;
    },

    // ── Progress & result renderers ──────────────────────────────────────
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

    _renderBatchProgress(tasks) {
        const total = tasks.length;
        const completed = tasks.filter(t => t.status === 'completed').length;
        const failed = tasks.filter(t => t.status === 'failed').length;
        const running = tasks.filter(t => !['completed', 'failed'].includes(t.status)).length;
        const pct = total > 0 ? Math.round((completed + failed) / total * 100) : 0;

        return `
            <div class="dubbing-progress-section">
                <div class="dubbing-progress-header">
                    <h3>批量配音进度</h3>
                    <span class="dubbing-progress-percent">${completed}/${total} 完成</span>
                </div>
                <div class="dubbing-progress-bar">
                    <div class="dubbing-progress-fill" style="width: ${pct}%"></div>
                </div>
                <div class="dubbing-batch-stats">
                    <span class="dubbing-batch-stat done">✓ ${completed} 完成</span>
                    <span class="dubbing-batch-stat fail">✗ ${failed} 失败</span>
                    <span class="dubbing-batch-stat run">⏳ ${running} 进行中</span>
                </div>
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

    // ── Event binding ────────────────────────────────────────────────────
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

        if (this.demoMode) {
            this._bindDemoEvents();
        } else {
            this._bindProjectEvents();
        }
    },

    _bindDemoEvents() {
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

    _bindProjectEvents() {
        const list = document.querySelector('.dubbing-project-list');
        if (!list) return;

        // Project card click
        list.addEventListener('click', (e) => {
            const card = e.target.closest('.dubbing-project-card');
            if (!card) return;
            // If clicking on episode list internals, don't toggle project
            if (e.target.closest('.dubbing-episode-list')) return;

            const projectId = card.dataset.projectId;
            if (this.selectedProject === projectId) {
                this.selectedProject = null;
                this.selectedEpisodes.clear();
            } else {
                this.selectedProject = projectId;
                this.selectedEpisodes.clear();
            }
            this.render();
            this.loadHistory();
        });

        // Episode checkbox
        list.addEventListener('change', (e) => {
            if (e.target.classList.contains('dubbing-ep-checkbox')) {
                const epId = e.target.dataset.epId;
                if (e.target.checked) {
                    this.selectedEpisodes.add(epId);
                } else {
                    this.selectedEpisodes.delete(epId);
                }
                this._updateStartButton();
            }

            // Select all
            if (e.target.classList.contains('dubbing-ep-select-all')) {
                const project = this.completedProjects.find(p => p.project_id === this.selectedProject);
                if (project) {
                    if (e.target.checked) {
                        project.episodes.forEach(ep => this.selectedEpisodes.add(ep.episode_id));
                    } else {
                        this.selectedEpisodes.clear();
                    }
                    this.render();
                    this.loadHistory();
                }
            }
        });
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
            section.querySelector('.dubbing-upload-area')?.after(div);
        }
    },

    _updateStartButton() {
        const btn = document.getElementById('dubbing-start-btn');
        if (!btn) return;

        if (this.demoMode) {
            btn.disabled = !(this.selectedLang && this.selectedVideoPath);
        } else {
            btn.disabled = !(this.selectedLang && this.selectedEpisodes.size > 0);
        }
    },

    clearVideo() {
        this.selectedVideoPath = null;
        const testToggle = document.getElementById('dubbing-use-test-video');
        if (testToggle) testToggle.checked = false;
        this._updateSourceDisplay();
        this._updateStartButton();
    },

    // ── Start dubbing ────────────────────────────────────────────────────
    async startDubbing() {
        if (!this.selectedLang) return;

        const btn = document.getElementById('dubbing-start-btn');
        if (btn) { btn.disabled = true; btn.textContent = '⏳ 启动中...'; }

        try {
            if (this.demoMode) {
                // Single video dubbing
                if (!this.selectedVideoPath) return;
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
            } else {
                // Batch project dubbing
                if (this.selectedEpisodes.size === 0) return;
                const res = await fetch('http://localhost:8000/api/v1/dubbing/start-batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        project_id: this.selectedProject,
                        target_language: this.selectedLang,
                        episode_ids: Array.from(this.selectedEpisodes),
                    }),
                });
                const data = await res.json();
                if (data.tasks && data.tasks.length > 0) {
                    this.batchTaskIds = data.tasks.map(t => t.task_id);
                    this._startBatchPolling();
                } else {
                    alert('启动失败: ' + (data.detail || JSON.stringify(data)));
                    if (btn) { btn.disabled = false; btn.textContent = '🎬 开始配音'; }
                }
            }
        } catch (err) {
            alert('启动失败: ' + err.message);
            if (btn) { btn.disabled = false; btn.textContent = '🎬 开始配音'; }
        }
    },

    _startPolling(taskId) {
        const startSection = document.querySelector('.dubbing-start-section');
        if (startSection) startSection.style.display = 'none';
        this._pollStatus(taskId);
    },

    _startBatchPolling() {
        const startSection = document.querySelector('.dubbing-start-section');
        if (startSection) startSection.style.display = 'none';
        this._pollBatchStatus();
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
                return;
            }

            if (status.status === 'failed') {
                if (progressArea) progressArea.innerHTML = '';
                if (resultArea) resultArea.innerHTML = this._renderError(status);
                this.loadHistory();
                return;
            }

            if (progressArea) progressArea.innerHTML = this._renderProgress(status);
            if (resultArea) resultArea.innerHTML = '';

            this.pollingTimer = setTimeout(() => this._pollStatus(taskId), 2000);
        } catch (err) {
            console.error('Poll error:', err);
            this.pollingTimer = setTimeout(() => this._pollStatus(taskId), 5000);
        }
    },

    async _pollBatchStatus() {
        try {
            const tasks = [];
            for (const tid of this.batchTaskIds) {
                const res = await fetch(`http://localhost:8000/api/v1/dubbing/${tid}`);
                tasks.push(await res.json());
            }

            const progressArea = document.getElementById('dubbing-progress-area');
            const resultArea = document.getElementById('dubbing-result-area');

            if (progressArea) progressArea.innerHTML = this._renderBatchProgress(tasks);

            const allDone = tasks.every(t => t.status === 'completed' || t.status === 'failed');

            if (allDone) {
                const completed = tasks.filter(t => t.status === 'completed');
                const failed = tasks.filter(t => t.status === 'failed');

                if (resultArea) {
                    resultArea.innerHTML = `
                        <div class="dubbing-result-section">
                            <h3>${completed.length === tasks.length ? '✓ 全部完成' : '⚠ 部分完成'}</h3>
                            <p>成功: ${completed.length} / 失败: ${failed.length} / 总计: ${tasks.length}</p>
                            <div class="dubbing-result-actions">
                                <button class="btn-secondary" onclick="DubbingView.init()">🔄 再次配音</button>
                            </div>
                        </div>
                    `;
                }
                this.loadHistory();
                return;
            }

            this.pollingTimer = setTimeout(() => this._pollBatchStatus(), 3000);
        } catch (err) {
            console.error('Batch poll error:', err);
            this.pollingTimer = setTimeout(() => this._pollBatchStatus(), 5000);
        }
    },

    // ── Load data ────────────────────────────────────────────────────────
    async loadCompletedProjects() {
        try {
            const res = await fetch('http://localhost:8000/api/v1/dubbing/completed-projects');
            const data = await res.json();
            this.completedProjects = data.projects || [];
        } catch (err) {
            this.completedProjects = [];
        }

        // Re-render project selector if we have data
        const section = document.querySelector('.dubbing-source-section');
        if (section) {
            const oldList = section.querySelector('.dubbing-project-list, .dubbing-empty-state');
            if (oldList) {
                const tmp = document.createElement('div');
                tmp.innerHTML = this._renderProjectSelector();
                const newContent = tmp.querySelector('.dubbing-source-section');
                if (newContent) {
                    section.innerHTML = newContent.innerHTML;
                    this._bindProjectEvents();
                }
            }
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
