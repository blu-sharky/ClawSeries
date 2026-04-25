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

            // Snapshot comparison: skip DOM update if data unchanged
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
                            <h3>视频任务</h3>
                            <div class="video-board-subtitle">点击镜头卡片查看提示词和生成日志</div>
                        </div>
                        <button class="btn-secondary btn-sm" onclick="VideoView.load()">刷新</button>
                    </div>
                    ${tasks.length ? `<div class="video-card-grid">${tasks.map(t => this._taskHtml(t)).join('')}</div>` : '<div class="video-empty">暂无视频生成任务</div>'}
                    <div id="video-detail" class="video-detail"></div>
                </div>
            `;
            if (this._selected) {
                const selected = tasks.find(t => t.task_id === this._selected.taskId);
                if (selected) await this.showDetail(selected.task_id, selected.project_id, selected.episode_id, selected.shot_id || '', false);
            }
        } catch (err) {
            el.innerHTML = `<div class="error-state"><p>加载视频任务失败: ${this._escape(err.message)}</p></div>`;
        }
    },

    _taskHtml(t) {
        const shotTitle = t.shot_number ? `镜头 ${t.shot_number}` : '整集镜头';
        const active = this._selected?.taskId === t.task_id ? 'active' : '';
        return `
            <button class="video-task-card ${active}" data-task-id="${this._escapeAttr(t.task_id)}" onclick="VideoView.showDetail('${this._escapeAttr(t.task_id)}', '${this._escapeAttr(t.project_id)}', '${this._escapeAttr(t.episode_id || '')}', '${this._escapeAttr(t.shot_id || '')}')">
                <div class="video-frame-box">
                    ${t.first_frame_path ? `<img src="${MEDIA_BASE}${this._escapeAttr(t.first_frame_path)}" alt="首帧图片">` : '<div class="video-frame-empty">暂无首帧</div>'}
                </div>
                <div class="video-card-body">
                    <div class="video-card-title">${this._escape(t.project_title || t.project_id)}</div>
                    <div class="video-card-meta">第${this._escape(t.episode_number || '-')}集 · ${this._escape(shotTitle)}</div>
                    <div class="video-card-meta">时长：${this._escape(t.shot_duration || '-')} · 任务：${this._escape(t.status)}</div>
                    <div class="video-card-desc">${this._escape(t.shot_description || '暂无提示词')}</div>
                    <div class="video-card-footer">
                        <span class="episode-status ${this._escapeAttr(t.shot_status || t.status)}">${this._escape(t.shot_status || t.status)}</span>
                        ${t.video_url ? `<a href="${MEDIA_BASE}${this._escapeAttr(t.video_url)}" target="_blank" onclick="event.stopPropagation()">查看视频</a>` : ''}
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
        detail.innerHTML = '<div class="video-empty">加载日志中...</div>';

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
                    <div class="section-title" style="margin:0;">第${this._escape(task.episode_number || '-')}集 · 镜头 ${this._escape(task.shot_number || '-')}</div>
                    <div class="video-board-subtitle">${this._escape(task.project_title || projectId)} · ${this._escape(task.shot_status || task.status || '')}</div>
                </div>
                ${task.video_url ? `<a class="btn-secondary btn-sm" href="${MEDIA_BASE}${this._escapeAttr(task.video_url)}" target="_blank">查看视频</a>` : ''}
            </div>
            <div class="video-detail-grid">
                <div class="video-frame-box detail">
                    ${framePath ? `<img src="${MEDIA_BASE}${this._escapeAttr(framePath)}" alt="首帧图片">` : '<div class="video-frame-empty">暂无首帧</div>'}
                </div>
                <details class="monitor-stream-card prompt" open>
                    <summary class="monitor-stream-summary">
                        <div class="monitor-stream-copy">
                            <div class="agent-monitor-label">最新提示词</div>
                            <div class="monitor-stream-preview">${this._escape(this._monitorPreview(prompt, '暂无提示词'))}</div>
                        </div>
                        <div class="monitor-stream-meta">${this._escape(this._monitorStatText(prompt, '暂无提示词'))}</div>
                    </summary>
                    <pre class="agent-monitor-text prompt">${this._escape(prompt || '暂无提示词')}</pre>
                </details>
            </div>
            <div class="section-title" style="margin-top: 16px;">生成日志</div>
            ${this._timelineHtml(events)}
        `;
        if (scroll) detail.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },

    _timelineHtml(events) {
        if (!events.length) return '<div class="video-empty">暂无日志</div>';
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
                                    <span class="timeline-time">${new Date(e.created_at).toLocaleTimeString()}</span>
                                </div>
                                <div class="timeline-message">${this._escape(e.message)}</div>
                                ${p.prompt ? `<div class="trace-detail">Prompt: ${this._escape(p.prompt)}</div>` : ''}
                                ${p.first_frame_path ? `<div class="trace-detail"><img src="${MEDIA_BASE}${this._escapeAttr(p.first_frame_path)}" class="video-log-frame" alt="首帧图片"></div>` : ''}
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
        return `${lineCount} 行 · ${normalized.length} 字`;
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
