const VideoView = {
    _timer: null,

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
            el.innerHTML = `
                <div class="card" style="padding:16px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                        <h3>视频任务</h3>
                        <button class="btn-secondary btn-sm" onclick="VideoView.load()">刷新</button>
                    </div>
                    ${tasks.length ? tasks.map(t => this._taskHtml(t)).join('') : '<div style="color:var(--text-secondary);">暂无视频生成任务</div>'}
                </div>
            `;
        } catch (err) {
            el.innerHTML = `<div class="error-state"><p>加载视频任务失败: ${err.message}</p></div>`;
        }
    },

    _taskHtml(t) {
        const shotTitle = t.shot_number ? `镜头 ${t.shot_number}` : '整集镜头';
        return `
            <div class="trace-entry" style="margin-bottom:12px;">
                <div class="trace-header">
                    <span class="trace-stage">${this._escape(t.project_title || t.project_id)}</span>
                    <span class="trace-agent">第${t.episode_number || '-'}集 · ${shotTitle}</span>
                    <span class="episode-status ${t.status}">${t.status}</span>
                </div>
                ${t.shot_description ? `<div class="trace-detail">Prompt: ${this._escape(t.shot_description)}</div>` : ''}
                ${t.first_frame_path ? `<div class="trace-detail"><img src="${MEDIA_BASE}${t.first_frame_path}" style="width:160px;border-radius:6px;margin-top:6px;"></div>` : ''}
                ${t.video_url ? `<div class="trace-detail"><a href="${MEDIA_BASE}${t.video_url}" target="_blank">查看视频</a></div>` : ''}
                ${t.error_message ? `<div class="trace-error">${this._escape(t.error_message)}</div>` : ''}
                ${t.project_id && t.episode_id ? `<button class="btn-secondary btn-sm" style="margin-top:8px;" onclick="VideoView.showLogs('${t.task_id}', '${t.project_id}', '${t.episode_id}', '${t.shot_id || ''}')">查看日志</button>` : ''}
                <div id="video-logs-${t.task_id}" style="margin-top:8px;"></div>
            </div>
        `;
    },

    async showLogs(taskId, projectId, episodeId, shotId) {
        const data = await Api.getProjectTimeline(projectId);
        const events = (data.timeline || []).filter(e => e.episode_id === episodeId && (!shotId || e.shot_id === shotId));
        const box = document.getElementById(`video-logs-${taskId}`);
        if (!box) return;
        box.innerHTML = events.length ? events.map(e => {
            const p = e.payload || {};
            return `
                <div class="timeline-entry">
                    <div class="timeline-content">
                        <div class="timeline-header"><span class="timeline-title">${this._escape(e.title)}</span><span class="timeline-time">${new Date(e.created_at).toLocaleTimeString()}</span></div>
                        <div class="timeline-message">${this._escape(e.message)}</div>
                        ${p.prompt ? `<div class="trace-detail">Prompt: ${this._escape(p.prompt)}</div>` : ''}
                        ${p.first_frame_path ? `<div class="trace-detail"><img src="${MEDIA_BASE}${p.first_frame_path}" style="width:160px;border-radius:6px;margin-top:6px;"></div>` : ''}
                        ${p.output ? `<div class="trace-detail">${this._escape(p.output)}</div>` : ''}
                    </div>
                </div>
            `;
        }).join('') : '<div style="color:var(--text-secondary);">暂无日志</div>';
    },

    _escape(v) {
        return String(v || '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    }
};
