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
        en: "\uD83C\uDDFA\uD83C\uDDF8 English", zh: "\uD83C\uDDE8\uD83C\uDDF3 Chinese", ja: "\uD83C\uDDEF\uD83C\uDDF5 Japanese",
        ko: "\uD83C\uDDF0\uD83C\uDDF7 Korean", es: "\uD83C\uDDEA\uD83C\uDDF8 Spanish", fr: "\uD83C\uDDEB\uD83C\uDDF7 French",
        de: "\uD83C\uDDE9\uD83C\uDDEA German", pt: "\uD83C\uDDE7\uD83C\uDDF7 Portuguese", hi: "\uD83C\uDDEE\uD83C\uDDF3 Hindi",
        th: "\uD83C\uDDF9\uD83C\uDDED Thai", ru: "\uD83C\uDDF7\uD83C\uDDFA Russian", ar: "\uD83C\uDDF8\uD83C\uDDE6 Arabic",
        it: "\uD83C\uDDEE\uD83C\uDDF9 Italian"
    },

    STEPS: [
        { key: "extracting_audio", icon: "\uD83C\uDFB5", get label() { return I18n.t('dubbing.step.extractAudio'); } },
        { key: "separating_vocals", icon: "\uD83C\uDFA4", get label() { return I18n.t('dubbing.step.separateVocals'); } },
        { key: "transcribing", icon: "\uD83D\uDCDD", get label() { return I18n.t('dubbing.step.transcribe'); } },
        { key: "translating", icon: "\uD83C\uDF10", get label() { return I18n.t('dubbing.step.translate'); } },
        { key: "generating_speech", icon: "\uD83D\uDDE3\uFE0F", get label() { return I18n.t('dubbing.step.generateSpeech'); } },
        { key: "merging", icon: "\uD83C\uDFAC", get label() { return I18n.t('dubbing.step.merge'); } },
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
                <h2>${I18n.t('dubbing.title')}</h2>
                <p>${this.demoMode
                    ? I18n.t('dubbing.demoModeDesc')
                    : I18n.t('dubbing.normalModeDesc')}</p>
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

    _renderLangSelector() {
        const btns = Object.entries(this.LANGUAGES).map(([code, name]) =>
            `<button class="dubbing-lang-btn${this.selectedLang === code ? ' selected' : ''}" data-lang="${code}">${name}</button>`
        ).join('');
        return `
            <div class="dubbing-lang-section">
                <h3>${I18n.t('dubbing.selectLang')}</h3>
                <div class="dubbing-lang-grid">${btns}</div>
            </div>
        `;
    },

    _renderDemoSourceSection() {
        const selectedFile = this.selectedVideoPath
            ? `<div class="dubbing-selected-file">
                <span class="file-icon">\uD83D\uDCC1</span>
                <span>${this.selectedVideoPath.split('/').pop()}</span>
                <span class="file-remove" onclick="DubbingView.clearVideo()">\u2715</span>
               </div>`
            : '';
        return `
            <div class="dubbing-source-section">
                <h3>${I18n.t('dubbing.selectVideo')}</h3>
                <div class="dubbing-upload-area" id="dubbing-drop-zone">
                    <div class="dubbing-upload-icon">\uD83D\uDCC1</div>
                    <div class="dubbing-upload-text">${I18n.t('dubbing.dragDrop')}</div>
                    <div class="dubbing-upload-hint">${I18n.t('dubbing.supportFormats')}</div>
                    <input type="file" id="dubbing-file-input" accept="video/*">
                </div>
                ${selectedFile}
                <div class="dubbing-test-mode">
                    <label class="toggle-switch">
                        <input type="checkbox" id="dubbing-use-test-video">
                        <span class="toggle-slider"></span>
                    </label>
                    <label for="dubbing-use-test-video">${I18n.t('dubbing.useTestVideo')}</label>
                </div>
            </div>
        `;
    },

    _renderProjectSelector() {
        if (this.completedProjects.length === 0) {
            return `
                <div class="dubbing-source-section">
                    <h3>${I18n.t('dubbing.selectProject')}</h3>
                    <div class="dubbing-empty-state">
                        <div class="dubbing-empty-icon">\uD83D\uDCFA</div>
                        <p>${I18n.t('dubbing.noCompleted')}</p>
                        <p class="dubbing-empty-hint">${I18n.t('dubbing.noCompletedHint')}</p>
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
                        <span class="dubbing-project-meta">${I18n.t('dubbing.episodes', { n: p.episodes.length })}</span>
                    </div>
                    ${isSelected ? this._renderEpisodeList(p) : ''}
                </div>
            `;
        }).join('');

        return `
            <div class="dubbing-source-section">
                <h3>${I18n.t('dubbing.selectProject')}</h3>
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
                ? `<span class="dubbing-ep-dub-count">${I18n.t('dubbing.dubTasks', { n: dubCount })}</span>`
                : '';
            return `
                <div class="dubbing-episode-item">
                    <label class="dubbing-episode-label">
                        <input type="checkbox" class="dubbing-ep-checkbox" data-ep-id="${ep.episode_id}" ${checked}>
                        <span>${I18n.t('dubbing.episodeLabel', { n: ep.episode_number, title: ep.title })}</span>
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
                        <span class="dubbing-select-all-text">${I18n.t('dubbing.selectAll')}</span>
                    </label>
                </div>
                ${items}
            </div>
        `;
    },

    _renderStartButton() {
        return `
            <div class="dubbing-start-section">
                <button class="dubbing-start-btn" id="dubbing-start-btn" onclick="DubbingView.startDubbing()" disabled>
                    ${I18n.t('dubbing.startDubbing')}
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
                <span class="dubbing-step-icon">${cls === 'done' ? '\u2713' : s.icon}</span>
                <span>${s.label}</span>
            </div>`;
        }).join('');

        return `
            <div class="dubbing-progress-section">
                <div class="dubbing-progress-header">
                    <h3>${currentStep || I18n.t('dubbing.processing')}</h3>
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
                    <h3>${I18n.t('dubbing.batchProgress')}</h3>
                    <span class="dubbing-progress-percent">${I18n.t('dubbing.batchComplete', { completed, total })}</span>
                </div>
                <div class="dubbing-progress-bar">
                    <div class="dubbing-progress-fill" style="width: ${pct}%"></div>
                </div>
                <div class="dubbing-batch-stats">
                    <span class="dubbing-batch-stat done">${I18n.t('dubbing.batchDone', { n: completed })}</span>
                    <span class="dubbing-batch-stat fail">${I18n.t('dubbing.batchFail', { n: failed })}</span>
                    <span class="dubbing-batch-stat run">${I18n.t('dubbing.batchRunning', { n: running })}</span>
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
                <h3>${I18n.t('dubbing.dubComplete')}</h3>
                <p>${I18n.t('dubbing.targetLang', { lang: targetLang })}</p>
                <div class="dubbing-result-video">
                    <video controls src="${videoUrl}"></video>
                </div>
                <div class="dubbing-result-actions">
                    <a class="btn-primary" href="${videoUrl}" download style="text-decoration:none;padding:10px 24px;border-radius:8px;font-size:14px;">${I18n.t('dubbing.downloadDub')}</a>
                    <button class="btn-secondary" onclick="DubbingView.init()">${I18n.t('dubbing.dubAgain')}</button>
                </div>
            </div>
        `;
    },

    _renderError(status) {
        return `
            <div class="dubbing-error">
                <h3>${I18n.t('dubbing.dubFailed')}</h3>
                <p>${status.error_message || I18n.t('dubbing.unknownError')}</p>
                <button class="btn-secondary" style="margin-top:12px" onclick="DubbingView.init()">${I18n.t('dubbing.retry')}</button>
            </div>
        `;
    },

    _bindEvents() {
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
        const fileInput = document.getElementById('dubbing-file-input');
        if (fileInput) {
            fileInput.addEventListener('change', (e) => this._handleFileUpload(e.target.files[0]));
        }

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

        list.addEventListener('click', (e) => {
            const card = e.target.closest('.dubbing-project-card');
            if (!card) return;
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
            alert(I18n.t('dubbing.uploadFailed', { msg: err.message }));
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
                <span class="file-icon">\uD83D\uDCC1</span>
                <span>${this.selectedVideoPath.split('/').pop()}</span>
                <span class="file-remove" onclick="DubbingView.clearVideo()">\u2715</span>
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

    async startDubbing() {
        if (!this.selectedLang) return;

        const btn = document.getElementById('dubbing-start-btn');
        if (btn) { btn.disabled = true; btn.textContent = I18n.t('dubbing.starting'); }

        try {
            if (this.demoMode) {
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
                    alert(I18n.t('dubbing.startFailed', { msg: data.detail || JSON.stringify(data) }));
                    if (btn) { btn.disabled = false; btn.textContent = I18n.t('dubbing.startDubbing'); }
                }
            } else {
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
                    alert(I18n.t('dubbing.startFailed', { msg: data.detail || JSON.stringify(data) }));
                    if (btn) { btn.disabled = false; btn.textContent = I18n.t('dubbing.startDubbing'); }
                }
            }
        } catch (err) {
            alert(I18n.t('dubbing.startFailed', { msg: err.message }));
            if (btn) { btn.disabled = false; btn.textContent = I18n.t('dubbing.startDubbing'); }
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
                            <h3>${completed.length === tasks.length ? I18n.t('dubbing.allComplete') : I18n.t('dubbing.partialComplete')}</h3>
                            <p>${I18n.t('dubbing.resultSummary', { completed: completed.length, failed: failed.length, total: tasks.length })}</p>
                            <div class="dubbing-result-actions">
                                <button class="btn-secondary" onclick="DubbingView.init()">${I18n.t('dubbing.dubAgain')}</button>
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

    async loadCompletedProjects() {
        try {
            const res = await fetch('http://localhost:8000/api/v1/dubbing/completed-projects');
            const data = await res.json();
            this.completedProjects = data.projects || [];
        } catch (err) {
            this.completedProjects = [];
        }

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
                const time = t.created_at ? new Date(t.created_at).toLocaleString(I18n.getLocale()) : '';
                return `<div class="dubbing-history-item">
                    <div class="dubbing-history-status ${sClass}"></div>
                    <div class="dubbing-history-info">
                        <span>${t.source_video_path.split('/').pop()}</span>
                        <span class="lang-badge">${lang} \xB7 ${time}</span>
                    </div>
                    <div class="dubbing-history-actions">
                        ${t.status === 'completed' ? `<a class="btn-secondary btn-sm" href="http://localhost:8000/api/v1/dubbing/${t.task_id}/download" download>${I18n.t('dubbing.download')}</a>` : ''}
                        ${['pending','extracting_audio','separating_vocals','transcribing','translating','generating_speech','merging'].includes(t.status) ? `<button class="btn-secondary btn-sm" onclick="DubbingView.watchTask('${t.task_id}')">${I18n.t('dubbing.watch')}</button>` : ''}
                    </div>
                </div>`;
            }).join('');

            container.innerHTML = `<h3>${I18n.t('dubbing.history')}</h3><div class="dubbing-history-list">${items}</div>`;
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
