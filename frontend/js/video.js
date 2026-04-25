const VideoView = {
    _timer: null,
    _selected: null,
    _lastTasksJson: null,

    async init() {
        await this.load();
        clearInterval(this._timer);
        this._timer = setInterval(() => this.load(), 5000);
    },

    async load() {
        const el = document.getElementById('video-content');
        if (!el) return;
        try {
            const data = await Api.getVideoTasks();
            const tasks = data.tasks || [];

            const snapshot = JSON.stringify(tasks.map(t => ({
                id: t.task_id, status: t.status, shot_status: t.shot_status,
                frame: t.first_frame_path, video: t.video_url, prompt: t.shot_description,
            })));
            if (snapshot === this._lastTasksJson) return;
            this._lastTasksJson = snapshot;

            el.innerHTML = `
                <div class="card video-board">
                    <div class="video-board-header">
                        <div>
                            <h3>${I18n.t('video.tasks')}</h3>
                            <div class="video-board-subtitle">${I18n.t('video.tasksSubtitle')}</div>
                        </div>
                        <button class="btn-secondary btn-sm" onclick="VideoView.load()">${I18n.t('video.refresh')}</button>
                    </div>
                    ${tasks.length ? `<div class="video-card-grid">${tasks.map(t => this._taskHtml(t)).join('')}</div>` : `<div class="video-empty">${I18n.t('video.noTasks')}</div>`}
                    <div id="video-detail" class="video-detail"></div>
                </div>
            `;
            if (this._selected) {
                const selected = tasks.find(t => t.task_id === this._selected.taskId);
                if (selected) await this.showDetail(selected.task_id, selected.project_id, selected.episode_id, selected.shot_id || '', false);
            }
        } catch (err) {
            el.innerHTML = `<div class="error-state"><p>${I18n.t('video.loadFailed', { msg: err.message })}</p></div>`;
        }
    },

    _taskHtml(t) {
        const shotTitle = t.shot_number ? I18n.t('video.shotTitle', { num: t.shot_number }) : I18n.t('video.allShots');
        const active = this._selected?.taskId === t.task_id ? 'active' : '';
        return `
            <button class="video-task-card ${active}" data-task-id="${this._escapeAttr(t.task_id)}" onclick="VideoView.showDetail('${this._escapeAttr(t.task_id)}', '${this._escapeAttr(t.project_id)}', '${this._escapeAttr(t.episode_id || '')}', '${this._escapeAttr(t.shot_id || '')}')">
                <div class="video-frame-box">
                    ${t.first_frame_path ? `<img src="${MEDIA_BASE}${this._escapeAttr(t.first_frame_path)}" alt="${I18n.t('video.noFrame')}">` : `<div class="video-frame-empty">${I18n.t('video.noFrame')}</div>`}
                </div>
                <div class="video-card-body">
                    <div class="video-card-title">${this._escape(t.project_title || t.project_id)}</div>
                    <div class="video-card-meta">${I18n.t('video.ep', { n: t.episode_number || '-' })} \xB7 ${this._escape(shotTitle)}</div>
                    <div class="video-card-meta">${I18n.t('video.duration')}\uFF1A${this._escape(t.shot_duration || '-')} \xB7 ${I18n.t('video.task')}\uFF1A${this._escape(t.status)}</div>
                    <div class="video-card-desc">${this._escape(t.shot_description || I18n.t('video.noPrompt'))}</div>
                    <div class="video-card-footer">
                        <span class="episode-status ${this._escapeAttr(t.shot_status || t.status)}">${this._escape(t.shot_status || t.status)}</span>
                        ${t.video_url ? `<a href="${MEDIA_BASE}${this._escapeAttr(t.video_url)}" target="_blank" onclick="event.stopPropagation()">${I18n.t('video.viewVideo')}</a>` : ''}
                    </div>
                    ${t.error_message ? `<div class="trace-error">${this._escape(t.error_message)}</div>` : ''}
                </div>
            </button>
        `;
    },

    async showDetail(taskId, projectId, episodeId, shotId, scroll = true) {
        this._selected = { taskId, projectId, episodeId, shotId };
        document.querySelectorAll('.video-task-card').forEach(card => {
            card.classList.toggle('active', card.dataset.taskId === taskId);
        });

        const detail = document.getElementById('video-detail');
        if (!detail) return;
        detail.innerHTML = `<div class="video-empty">${I18n.t('video.loadingLogs')}</div>`;

        const [tasksData, timelineData] = await Promise.all([
            Api.getVideoTasks(),
            Api.getProjectTimeline(projectId),
        ]);
        const task = (tasksData.tasks || []).find(t => t.task_id === taskId) || this._selected;
        const events = (timelineData.timeline || []).filter(e => e.episode_id === episodeId && (!shotId || e.shot_id === shotId));
        const prompt = this._latestPrompt(events, task);
        const framePath = this._latestFrame(events, task);

        detail.innerHTML = `
            <div class="video-detail-header">
                <div>
                    <div class="section-title" style="margin:0;">${I18n.t('video.ep', { n: task.episode_number || '-' })} \xB7 ${I18n.t('video.shot', { n: task.shot_number || '-' })}</div>
                    <div class="video-board-subtitle">${this._escape(task.project_title || projectId)} \xB7 ${this._escape(task.shot_status || task.status || '')}</div>
                </div>
                ${task.video_url ? `<a class="btn-secondary btn-sm" href="${MEDIA_BASE}${this._escapeAttr(task.video_url)}" target="_blank">${I18n.t('video.viewVideo')}</a>` : ''}
            </div>
            <div class="video-detail-grid">
                <div class="video-frame-box detail">
                    ${framePath ? `<img src="${MEDIA_BASE}${this._escapeAttr(framePath)}" alt="${I18n.t('video.noFrame')}">` : `<div class="video-frame-empty">${I18n.t('video.noFrame')}</div>`}
                </div>
                <details class="monitor-stream-card prompt" open>
                    <summary class="monitor-stream-summary">
                        <div class="monitor-stream-copy">
                            <div class="agent-monitor-label">${I18n.t('video.latestPrompt')}</div>
                            <div class="monitor-stream-preview">${this._escape(this._monitorPreview(prompt, I18n.t('video.noPrompt')))}</div>
                        </div>
                        <div class="monitor-stream-meta">${this._escape(this._monitorStatText(prompt, I18n.t('video.noPrompt')))}</div>
                    </summary>
                    <pre class="agent-monitor-text prompt">${this._escape(prompt || I18n.t('video.noPrompt'))}</pre>
                </details>
            </div>
            <div class="section-title" style="margin-top: 16px;">${I18n.t('video.genLogs')}</div>
            ${this._timelineHtml(events)}
        `;
        if (scroll) detail.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },

    _timelineHtml(events) {
        if (!events.length) return `<div class="video-empty">${I18n.t('video.noLogs')}</div>`;
        return `
            <div class="timeline-list">
                ${events.map(e => {
                    const p = e.payload || {};
                    const meta = this._agentMeta(e.agent_id);
                    return `
                        <div class="timeline-entry">
                            <div class="timeline-icon" style="background: ${meta.color}"><span class="material-symbols-outlined">${meta.icon}</span></div>
                            <div class="timeline-content">
                                <div class="timeline-header">
                                    <span class="timeline-agent">${this._escape(meta.name)}</span>
                                    <span class="timeline-title">${this._escape(e.title)}</span>
                                    <span class="timeline-time">${new Date(e.created_at).toLocaleTimeString(I18n.getLocale())}</span>
                                </div>
                                <div class="timeline-message">${this._escape(e.message)}</div>
                                ${p.prompt ? `<div class="trace-detail">Prompt: ${this._escape(p.prompt)}</div>` : ''}
                                ${p.first_frame_path ? `<div class="trace-detail"><img src="${MEDIA_BASE}${this._escapeAttr(p.first_frame_path)}" class="video-log-frame" alt="${I18n.t('video.noFrame')}"></div>` : ''}
                                ${p.output ? `<div class="trace-detail">Output: ${this._escape(p.output)}</div>` : ''}
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
    },

    _latestPrompt(events, task) {
        const promptEvent = [...events].reverse().find(e => e.payload?.prompt);
        return promptEvent?.payload?.prompt || task.shot_description || '';
    },

    _latestFrame(events, task) {
        const frameEvent = [...events].reverse().find(e => e.payload?.first_frame_path || (e.payload?.output || '').match(/\.(png|jpg|jpeg|webp)$/i));
        return frameEvent?.payload?.first_frame_path || ((frameEvent?.payload?.output || '').match(/\.(png|jpg|jpeg|webp)$/i) ? frameEvent.payload.output : '') || task.first_frame_path || '';
    },

    _monitorPreview(value, fallback) {
        const normalized = String(value || '').replace(/```json\n?/g, '').replace(/```/g, '').trim();
        if (!normalized) return fallback;
        const lines = normalized.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
        const firstMeaningfulLine = (lines[0] === '{' || lines[0] === '[') && lines[1] ? lines[1] : (lines[0] || normalized);
        return firstMeaningfulLine.length > 88 ? `${firstMeaningfulLine.slice(0, 88)}…` : firstMeaningfulLine;
    },

    _monitorStatText(value, fallback) {
        const normalized = String(value || '').replace(/```json\n?/g, '').replace(/```/g, '').trim();
        if (!normalized) return fallback;
        const lineCount = normalized.split(/\r?\n/).filter(Boolean).length;
        return I18n.t('project.monitor.lineChar', { lines: lineCount, chars: normalized.length });
    },

    _agentMeta(agentId) {
        return (typeof AGENT_META !== 'undefined' && AGENT_META[agentId]) || { icon: 'smart_toy', color: '#6b7280', name: 'Agent' };
    },

    _escape(v) {
        return String(v ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    },

    _escapeAttr(v) {
        return this._escape(v).replace(/'/g, '&#39;');
    }
};
