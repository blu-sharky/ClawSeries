/**
 * 应用入口 - 初始化和导航
 */

const App = {
    async init() {
        Chat.init();
        this.refreshProjectList();
        this.startSystemStatusPolling();
    },

    async refreshProjectList() {
        const list = document.getElementById('project-list');
        try {
            const data = await Api.getProjects();

            if (!data.projects || data.projects.length === 0) {
                list.innerHTML = '<div style="padding: 8px 16px; font-size: 12px; color: rgba(255,255,255,0.3);">暂无项目</div>';
                return;
            }

            list.innerHTML = data.projects.map(p => {
                const statusClass = p.status === 'in_progress' ? 'in-progress' : p.status;
                const showContinue = p.status === 'paused' || p.status === 'pending' || (p.status === 'in_progress' && p.current_stage);
                return `
                    <div class="project-nav-item-wrapper">
                        <button class="project-nav-item" data-pid="${p.project_id}" onclick="ProjectView.show('${p.project_id}')">
                            <span class="project-nav-status ${statusClass}"></span>
                            <span class="project-nav-title">${p.title}</span>
                        </button>
                        <div class="project-nav-actions">
                            ${showContinue ? `<button class="project-action-btn continue" onclick="event.stopPropagation(); App.continueProject('${p.project_id}')" title="继续制片">▶</button>` : ''}
                            <button class="project-action-btn delete" onclick="event.stopPropagation(); App.deleteProject('${p.project_id}', '${p.title}')" title="删除项目">×</button>
                        </div>
                    </div>
                `;
            }).join('');
        } catch (err) {
            list.innerHTML = '<div style="padding: 8px 16px; font-size: 12px; color: rgba(255,255,255,0.3);">无法连接后端</div>';
        }
    },

    async checkSystemStatus() {
        const indicator = document.getElementById('system-status');
        const dot = indicator.querySelector('.status-dot');
        const text = indicator.querySelector('span:last-child');

        try {
            const res = await fetch('http://localhost:8000/api/v1/system/status', { signal: AbortSignal.timeout(3000) });
            const data = await res.json();

            // Check if any critical service is down
            const apiStatus = data.api_status || {};
            const allDown = Object.values(apiStatus).every(v => v === 'not_configured');

            if (data.status === 'operational') {
                dot.className = 'status-dot healthy';
                text.textContent = allDown ? '系统正常 (未配置)' : '系统正常';
            } else {
                dot.className = 'status-dot warning';
                text.textContent = data.status;
            }
        } catch (err) {
            dot.className = 'status-dot error';
            text.textContent = '后端未连接';
        }
    },

    startSystemStatusPolling() {
        // Check immediately
        this.checkSystemStatus();
        // Then every 10 seconds
        setInterval(() => this.checkSystemStatus(), 10000);
    },

    async deleteProject(projectId, title) {
        if (!confirm(`确定要删除项目「${title}」吗？此操作不可撤销。`)) return;
        try {
            await Api.deleteProject(projectId);
            this.refreshProjectList();

            if (ProjectView.currentProjectId === projectId) {
                navigateTo('new-project');
            }
        } catch (err) {
            alert('删除失败: ' + err.message);
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
            alert('继续制片失败: ' + err.message);
        }
    }
};

function navigateTo(view) {
    if (ProjectView._refreshTimer) {
        clearInterval(ProjectView._refreshTimer);
        ProjectView._refreshTimer = null;
    }
    // Hide all views
    document.getElementById('view-new-project').classList.add('hidden');
    document.getElementById('view-project-detail').classList.add('hidden');
    document.getElementById('view-settings').classList.add('hidden');
    document.getElementById('view-dubbing').classList.add('hidden');

    // Update nav state
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.project-nav-item').forEach(el => el.classList.remove('active'));
    document.querySelector(`[data-view="${view}"]`)?.classList.add('active');

    if (view === 'new-project') {
        document.getElementById('view-new-project').classList.remove('hidden');
    } else if (view === 'settings') {
        document.getElementById('view-settings').classList.remove('hidden');
        Settings.init();
    } else if (view === 'dubbing') {
        document.getElementById('view-dubbing').classList.remove('hidden');
        DubbingView.init();
    }
}

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});
