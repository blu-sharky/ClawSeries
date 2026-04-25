/**
 * 应用入口 - 初始化和导航
 */

const App = {
    async init() {
        Chat.init();
        this.refreshProjectList();
        this.startSystemStatusPolling();
        this._updateLangToggle();
    },

    _updateLangToggle() {
        const label = document.getElementById('lang-label');
        if (label) label.textContent = I18n.getLocale() === 'zh-CN' ? 'EN' : '中文';
    },

    async refreshProjectList() {
        const list = document.getElementById('project-list');
        try {
            const data = await Api.getProjects();

            if (!data.projects || data.projects.length === 0) {
                list.innerHTML = `<div style="padding: 8px 16px; font-size: 12px; color: rgba(255,255,255,0.3);">${I18n.t('app.noProjects')}</div>`;
                return;
            }

            list.innerHTML = data.projects.map(p => {
                const statusClass = p.status === 'in_progress' ? 'in-progress' : p.status;
                const showContinue = p.status !== 'completed';
                return `
                    <div class="project-nav-item-wrapper">
                        <button class="project-nav-item" data-pid="${p.project_id}" onclick="ProjectView.show('${p.project_id}')">
                            <span class="project-nav-status ${statusClass}"></span>
                            <span class="project-nav-title">${p.title}</span>
                        </button>
                        <div class="project-nav-actions">
                            ${showContinue ? `<button class="project-action-btn continue" onclick="event.stopPropagation(); App.continueProject('${p.project_id}')" title="${I18n.t('project.startProduction')}">▶</button>` : ''}
                            <button class="project-action-btn delete" onclick="event.stopPropagation(); App.deleteProject('${p.project_id}', '${p.title}')" title="${I18n.t('project.newProject')}">×</button>
                        </div>
                    </div>
                `;
            }).join('');
        } catch (err) {
            list.innerHTML = `<div style="padding: 8px 16px; font-size: 12px; color: rgba(255,255,255,0.3);">${I18n.t('app.backendOffline')}</div>`;
        }
    },

    async checkSystemStatus() {
        const indicator = document.getElementById('system-status');
        const dot = indicator.querySelector('.status-dot');
        const text = indicator.querySelector('span:last-child');

        try {
            const res = await fetch('http://localhost:8000/api/v1/system/status', { signal: AbortSignal.timeout(3000) });
            const data = await res.json();

            const apiStatus = data.api_status || {};
            const allDown = Object.values(apiStatus).every(v => v === 'not_configured');

            if (data.status === 'operational') {
                dot.className = 'status-dot healthy';
                text.textContent = allDown ? I18n.t('app.systemOkUnconfigured') : I18n.t('app.systemOk');
            } else {
                dot.className = 'status-dot warning';
                text.textContent = data.status;
            }
        } catch (err) {
            dot.className = 'status-dot error';
            text.textContent = I18n.t('app.backendDisconnected');
        }
    },

    startSystemStatusPolling() {
        this.checkSystemStatus();
        setInterval(() => this.checkSystemStatus(), 10000);
    },

    async deleteProject(projectId, title) {
        if (!confirm(I18n.t('app.deleteConfirm', { title }))) return;
        try {
            await Api.deleteProject(projectId);
            this.refreshProjectList();

            if (ProjectView.currentProjectId === projectId) {
                navigateTo('new-project');
            }
        } catch (err) {
            alert(I18n.t('app.deleteFailed', { msg: err.message }));
        }
    },

    async continueProject(projectId) {
        try {
            await Api.continueProject(projectId);
            this.refreshProjectList();

            if (ProjectView.currentProjectId === projectId) {
                ProjectView.show(projectId);
            }
        } catch (err) {
            alert(I18n.t('app.continueFailed', { msg: err.message }));
        }
    }
};

function navigateTo(view) {
    if (ProjectView._refreshTimer) {
        clearInterval(ProjectView._refreshTimer);
        ProjectView._refreshTimer = null;
    }
    if (window.VideoView && VideoView._timer) {
        clearInterval(VideoView._timer);
        VideoView._timer = null;
    }
    document.getElementById('view-new-project').classList.add('hidden');
    document.getElementById('view-project-detail').classList.add('hidden');
    document.getElementById('view-settings').classList.add('hidden');
    document.getElementById('view-video').classList.add('hidden');
    document.getElementById('view-dubbing').classList.add('hidden');

    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.project-nav-item').forEach(el => el.classList.remove('active'));
    document.querySelector(`[data-view="${view}"]`)?.classList.add('active');

    if (view === 'new-project') {
        document.getElementById('view-new-project').classList.remove('hidden');
    } else if (view === 'settings') {
        document.getElementById('view-settings').classList.remove('hidden');
        Settings.init();
    } else if (view === 'video') {
        document.getElementById('view-video').classList.remove('hidden');
        VideoView.init();
    } else if (view === 'dubbing') {
        document.getElementById('view-dubbing').classList.remove('hidden');
        DubbingView.init();
    }
}

function toggleLanguage() {
    const next = I18n.getLocale() === 'zh-CN' ? 'en' : 'zh-CN';
    I18n.setLocale(next);
    location.reload();
}

document.addEventListener('DOMContentLoaded', () => {
    App.init();
});
