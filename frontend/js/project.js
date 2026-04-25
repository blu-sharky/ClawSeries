/**
 * Project detail view - linear pipeline stepper with 5 Agent identities.
 */

const AGENT_META = {
    agent_director: {
        name: '项目总监',
        icon: 'assignment',
        description: '',
        color: '#6c5ce7',
    },
    agent_chief_director: {
        name: '总导演',
        icon: 'movie_creation',
        description: '',
        color: '#e17055',
    },
    agent_visual: {
        name: '视觉总监',
        icon: 'palette',
        description: '',
        color: '#00b894',
    },
    agent_prompt: {
        name: '提示词架构师',
        icon: 'edit_note',
        description: '',
        color: '#fdcb6e',
    },
    agent_editor: {
        name: '自动化剪辑师',
        icon: 'video_library',
        description: '',
        color: '#74b9ff',
    },
};
const AGENT_ORDER = Object.keys(AGENT_META);

// Pipeline stages for the linear stepper
const PIPELINE_STAGES = [
    { stage: 'requirements_confirmed', label: '需求确认', agent: 'agent_director' },
    { stage: 'script_completed', label: '完整剧本', agent: 'agent_chief_director' },
    { stage: 'format_completed', label: '格式化分镜', agent: 'agent_prompt' },
    { stage: 'assets_completed', label: '资产锁定', agent: 'agent_visual' },
    { stage: 'shots_completed', label: '逐镜视频', agent: 'agent_visual' },
    { stage: 'project_completed', label: '合成输出', agent: 'agent_editor' },
];

const STAGE_TITLES = {
    requirements_confirmed: '需求确认',
    script_generating: '剧本生成中',
    script_completed: '完整剧本',
    format_generating: '格式化分镜中',
    format_completed: '格式化分镜',
    assets_generating: '资产生成中',
    assets_completed: '资产锁定',
    shots_generating: '逐镜视频生成中',
    shots_completed: '逐镜视频',
    episode_composing: '剧集合成中',
    episode_completed: '剧集完成',
    project_completed: '合成输出'
};

const EPISODE_STATUS_LABELS = {
    completed: '已完成',
    editing: '剪辑中',
    rendering: '渲染中',
    asset_generating: '素材生成',
    storyboarding: '分镜设计',
    scripting: '剧本编写',
    pending: '等待中',
    qc_checking: '质检中',
    failed: '失败',
};

const ProjectView = {
    currentProjectId: null,
    currentTab: 'overview',
    agentsData: null,
    agentMonitorState: {},
    ws: null,
    _userScrolling: false,
    _scrollTimeout: null,
    _refreshTimer: null,
    async show(projectId) {
        this.currentProjectId = projectId;
        this.currentTab = 'overview';
        this.agentMonitorState = {};
        this._userScrolling = false;

        if (this._refreshTimer) {
            clearInterval(this._refreshTimer);
            this._refreshTimer = null;
        }

        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }

        document.getElementById('view-new-project').classList.add('hidden');
        document.getElementById('view-settings').classList.add('hidden');
        document.getElementById('view-dubbing').classList.add('hidden');
        document.getElementById('view-project-detail').classList.remove('hidden');

        document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
        document.querySelectorAll('.project-nav-item').forEach(el => el.classList.remove('active'));
        const navItem = document.querySelector(`.project-nav-item[data-pid="${projectId}"]`);
        if (navItem) navItem.classList.add('active');

        // Set up scroll listener to detect user scrolling
        this._setupScrollListener();

        const project = await Api.getProject(projectId);
        if (!project) return;

        this._renderHeader(project);
        this._renderContent(project);

        this.ws = Api.connectWebSocket(projectId, (msg) => this._handleWsMessage(msg));
        this._refreshTimer = setInterval(() => this.refresh(), 5000);
    },

    async refresh() {
        if (!this.currentProjectId || document.getElementById('view-project-detail').classList.contains('hidden')) return;
        const project = await Api.getProject(this.currentProjectId);
        if (!project) return;
        this._renderHeader(project);
        this._renderTab(this.currentTab, project);
        App.refreshProjectList();
    },

    _renderHeader(project) {
        const header = document.getElementById('project-detail-header');
        const statusLabels = { pending: '等待中', in_progress: '制片中', completed: '已完成', paused: '已暂停', failed: '失败' };

        header.innerHTML = `
            <div class="project-header-bar">
                <div class="project-title-area">
                    <h1>${project.title}</h1>
                    <span class="project-badge ${project.status}">${statusLabels[project.status] || project.status}</span>
                </div>
                <div class="project-actions">
                    ${project.status === 'pending' ? `
                        <button class="btn-primary" onclick="ProjectView.startProduction()">启动制片</button>
                    ` : ''}
                    <button class="btn-secondary" onclick="navigateTo('new-project')">+ 新建项目</button>
                </div>
            </div>
        `;
    },

    _renderContent(project) {
        const content = document.getElementById('project-detail-content');
        content.innerHTML = `
            <div class="tabs">
                <button class="tab-btn active" onclick="ProjectView.switchTab('overview')">概览</button>
                <button class="tab-btn" onclick="ProjectView.switchTab('monitor')">总控台</button>
                <button class="tab-btn" onclick="ProjectView.switchTab('pipeline')">日志</button>
                <button class="tab-btn" onclick="ProjectView.switchTab('characters')">角色</button>
                <button class="tab-btn" onclick="ProjectView.switchTab('episodes')">剧集</button>
            </div>
            <div id="tab-content"></div>
        `;

        this._renderTab('overview', project);
    },

    async switchTab(tab) {
        this.currentTab = tab;
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.textContent === this._tabLabel(tab));
        });

        const project = await Api.getProject(this.currentProjectId);
        if (project) this._renderTab(tab, project);
    },

    _tabLabel(tab) {
        return {
            overview: '概览',
            monitor: '总控台',
            pipeline: '日志',
            characters: '角色',
            episodes: '剧集'
        }[tab] || tab;
    },

    _renderTab(tab, project) {
        const container = document.getElementById('tab-content');
        switch (tab) {
            case 'overview': this._renderOverview(container, project); break;
            case 'monitor': this._renderMonitor(container, project); break;
            case 'pipeline': this._renderPipeline(container, project); break;
            case 'characters': this._renderCharacters(container, project); break;
            case 'episodes': this._renderEpisodes(container, project); break;
        }
    },

    _orderedAgents(agents = []) {
        return [...agents].sort(
            (a, b) => AGENT_ORDER.indexOf(a.agent_id) - AGENT_ORDER.indexOf(b.agent_id)
        );
    },

    _renderPipeline(container, project) {
        // Simple log view - just the timeline
        container.innerHTML = `
            <div class="pipeline-container">
                <div class="section-title">生产事件日志</div>
                <div id="pipeline-timeline"><div style="color: var(--text-tertiary); text-align: center; padding: 24px;">加载中...</div></div>
            </div>
        `;
        this._loadTimeline();
    },

    async _loadTimeline() {
        try {
            const data = await Api.getProjectTimeline(this.currentProjectId);
            const timelineEl = document.getElementById('pipeline-timeline');
            if (!timelineEl) return;

            const events = data.timeline || [];
            if (events.length === 0) {
                timelineEl.innerHTML = '<div style="color: var(--text-tertiary); text-align: center; padding: 24px;">暂无生产事件</div>';
                return;
            }

            let html = '<div class="timeline-list">';
            for (const e of events.slice(-30)) {
                const agent = AGENT_META[e.agent_id] || { icon: 'smart_toy', color: '#6b7280', name: 'Agent' };
                html += `
                    <div class="timeline-entry">
                        <div class="timeline-icon" style="background: ${agent.color}"><span class="material-symbols-outlined">${agent.icon}</span></div>
                        <div class="timeline-content">
                            <div class="timeline-header">
                                <span class="timeline-agent">${agent.name}</span>
                                <span class="timeline-title">${e.title}</span>
                                <span class="timeline-time">${new Date(e.created_at).toLocaleTimeString()}</span>
                            </div>
                            <div class="timeline-message">${e.message}</div>
                        </div>
                    </div>
                `;
            }
            html += '</div>';
            timelineEl.innerHTML = html;
        } catch (err) {
            const timelineEl = document.getElementById('pipeline-timeline');
            if (timelineEl) timelineEl.innerHTML = '<div style="color: var(--text-tertiary); text-align: center;">加载失败</div>';
        }
    },

    _renderOverview(container, project) {
        const completed = project.episodes.filter(e => e.status === 'completed').length;
        const inProgress = project.episodes.filter(e => e.status !== 'completed' && e.status !== 'pending').length;
        const pending = project.episodes.filter(e => e.status === 'pending').length;

        container.innerHTML = `
            <div class="progress-overview">
                <div class="stat-card">
                    <div class="stat-card-label">总体进度</div>
                    <div class="stat-card-value">${project.progress}%</div>
                    <div class="progress-bar-wrapper">
                        <div class="progress-bar-track">
                            <div class="progress-bar-fill success" style="width: ${project.progress}%"></div>
                        </div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-label">已完成</div>
                    <div class="stat-card-value">${completed}</div>
                    <div class="stat-card-sub">共 ${project.episodes.length} 集</div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-label">进行中</div>
                    <div class="stat-card-value">${inProgress}</div>
                    <div class="stat-card-sub">渲染/剪辑/生成中</div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-label">等待中</div>
                    <div class="stat-card-value">${pending}</div>
                    <div class="stat-card-sub">排队等待处理</div>
                </div>
            </div>

            <div class="section-title">当前阶段</div>
            <div id="overview-agents"></div>
        `;

        this._renderAgentsMini(document.getElementById('overview-agents'), project);
    },

    _agentStatusText(status) {
        return status === 'working' ? '工作中' : status === 'error' ? '错误' : '空闲';
    },

    async _renderAgentsMini(container, project) {
        const agentsData = await Api.getAgents(project.project_id);
        let html = '<div class="agents-grid">';
        for (const agent of this._orderedAgents(agentsData.agents || [])) {
            const meta = AGENT_META[agent.agent_id] || { icon: 'smart_toy', description: '', color: '#6b7280' };
            const progress = agent.total_tasks > 0 ? Math.round(agent.completed_tasks / agent.total_tasks * 100) : 0;
            html += `
                <div class="agent-card">
                    <div class="agent-card-header">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <span class="agent-icon"><span class="material-symbols-outlined">${meta.icon}</span></span>
                            <span class="agent-name">${agent.name}</span>
                        </div>
                        <span class="agent-status">
                            <span class="agent-status-dot ${agent.status}"></span>
                            ${this._agentStatusText(agent.status)}
                        </span>
                    </div>
                    <div class="agent-task">${this._escapeHtml(agent.current_task || '等待任务')}</div>
                    <div class="agent-progress">
                        <span>${agent.completed_tasks} / ${agent.total_tasks}</span>
                        <span>${progress}%</span>
                    </div>
                    <div class="progress-bar-track">
                        <div class="progress-bar-fill" style="width: ${progress}%; background: ${meta.color}"></div>
                    </div>
                </div>
            `;
        }
        html += '</div>';
        container.innerHTML = html;
    },

    async _renderMonitor(container, project) {
        const agentsData = await Api.getAgents(project.project_id);
        const orderedAgents = this._orderedAgents(agentsData.agents || []);

        const agentDetails = await Promise.all(
            orderedAgents.map(async (agent) => {
                const eventsData = await Api.getAgentEvents(project.project_id, agent.agent_id);
                const events = eventsData.events || [];
                return {
                    agent,
                    events,
                    monitor: this._deriveMonitorState(agent.agent_id, events)
                };
            })
        );

        const active = agentDetails.find(({ agent }) => agent.status === 'working') || agentDetails[0] || null;
        const workingAgents = agentDetails.filter(({ agent }) => agent.status === 'working').length;
        const currentStageLabel = this._stageTitle(project.current_stage) || '待启动';

        // Simplified monitor: status header + agent cards with prompt/output only
        let html = `
            <section class="monitor-hero">
                <div class="monitor-hero-main">
                    <div class="monitor-hero-heading">
                        <div>
                            <div class="section-title" style="margin: 0;">总控台</div>
                        </div>
                        <div class="monitor-stage-badge ${project.status}">${this._escapeHtml(currentStageLabel)}</div>
                    </div>
                    <div class="monitor-hero-task">${active ? this._escapeHtml(active.agent.current_task || active.monitor.currentTask || '等待任务') : '当前没有活跃任务'}</div>
                    <div class="monitor-stage-strip">
                        ${PIPELINE_STAGES.map(ps => {
                            const stageInfo = (project.stages || []).find(s => s.stage === ps.stage);
                            const status = stageInfo?.status || (project.current_stage === ps.stage && project.status !== 'pending' ? 'in_progress' : 'pending');
                            const meta = AGENT_META[ps.agent] || { icon: 'smart_toy', color: '#6b7280' };
                            const stageAgent = orderedAgents.find(agent => agent.agent_id === ps.agent);
                            return `
                                <div class="monitor-stage-chip ${status} ${project.current_stage === ps.stage ? 'current' : ''}">
                                    <div class="monitor-stage-chip-icon" style="color: ${meta.color}"><span class="material-symbols-outlined">${meta.icon}</span></div>
                                    <div class="monitor-stage-chip-body">
                                        <div class="monitor-stage-chip-title">${ps.label}</div>
                                        <div class="monitor-stage-chip-meta">${this._escapeHtml(stageAgent?.name || '待分配')}</div>
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
                <div class="monitor-kpi-grid">
                    <div class="monitor-kpi-card primary">
                        <div class="monitor-kpi-label">当前阶段</div>
                        <div class="monitor-kpi-value small">${this._escapeHtml(currentStageLabel)}</div>
                        <div class="monitor-kpi-sub">项目状态：${this._escapeHtml(project.status)}</div>
                    </div>
                    <div class="monitor-kpi-card">
                        <div class="monitor-kpi-label">活跃智能体</div>
                        <div class="monitor-kpi-value">${workingAgents}</div>
                        <div class="monitor-kpi-sub">${orderedAgents.length} 个席位在线</div>
                    </div>
                    <div class="monitor-kpi-card">
                        <div class="monitor-kpi-label">总体进度</div>
                        <div class="monitor-kpi-value">${project.progress}%</div>
                        <div class="monitor-kpi-sub">${project.episodes?.length || 0} 集</div>
                    </div>
                </div>
            </section>
        `;

        // Agent panels - only show prompt/output (events/logs moved to 日志 tab)
        for (const { agent, events, monitor } of agentDetails) {
            const meta = AGENT_META[agent.agent_id] || { icon: 'smart_toy', description: '', color: '#6b7280' };
            const stageLabel = this._stageTitle(monitor.stage) || '未进入阶段';
            const progress = agent.total_tasks > 0 ? Math.round((agent.completed_tasks / agent.total_tasks) * 100) : 0;
            html += `
                <section class="monitor-panel ${agent.status}">
                    <div class="monitor-panel-header">
                        <div class="monitor-panel-title" style="color: ${meta.color};display:flex;align-items:center;gap:6px;"><span class="material-symbols-outlined" style="font-size:20px;">${meta.icon}</span> ${agent.name}</div>
                        <div class="monitor-panel-badges">
                            <span class="monitor-pill stage" id="monitor-stage-${agent.agent_id}">${this._escapeHtml(stageLabel)}</span>
                            <span class="monitor-pill status ${agent.status}">${this._agentStatusText(agent.status)}</span>
                        </div>
                    </div>
                    <div class="agent-task" id="monitor-task-${agent.agent_id}">${this._escapeHtml(agent.current_task || monitor.currentTask || '等待任务')}</div>
                    <div class="monitor-mini-stats">
                        <div class="monitor-mini-stat">
                            <span>任务</span>
                            <strong>${agent.completed_tasks} / ${agent.total_tasks}</strong>
                        </div>
                        <div class="monitor-mini-stat">
                            <span>进度</span>
                            <strong>${progress}%</strong>
                        </div>
                    </div>
                    <div class="monitor-stream-grid">
                        <details class="monitor-stream-card prompt" id="monitor-prompt-card-${agent.agent_id}">
                            <summary class="monitor-stream-summary">
                                <div class="monitor-stream-copy">
                                    <div class="agent-monitor-label">最新提示词</div>
                                    <div class="monitor-stream-preview" id="monitor-prompt-preview-${agent.agent_id}">${this._escapeHtml(this._monitorPreview(monitor.prompt, '暂无提示词'))}</div>
                                </div>
                                <div class="monitor-stream-meta" id="monitor-prompt-stat-${agent.agent_id}">${this._escapeHtml(this._monitorStatText(monitor.prompt, '暂无提示词'))}</div>
                            </summary>
                            <pre class="agent-monitor-text prompt" id="monitor-prompt-${agent.agent_id}">${this._escapeHtml(monitor.prompt || '暂无提示词')}</pre>
                        </details>
                        <details class="monitor-stream-card output" id="monitor-output-card-${agent.agent_id}" ${(monitor.output || agent.status === 'working') ? 'open' : ''}>
                            <summary class="monitor-stream-summary">
                                <div class="monitor-stream-copy">
                                    <div class="agent-monitor-label">实时反馈</div>
                                    <div class="monitor-stream-preview" id="monitor-output-preview-${agent.agent_id}">${this._escapeHtml(this._monitorPreview(monitor.output, '等待输出'))}</div>
                                </div>
                                <div class="monitor-stream-meta" id="monitor-output-stat-${agent.agent_id}">${this._escapeHtml(this._monitorStatText(monitor.output, '等待输出'))}</div>
                            </summary>
                            <div class="agent-monitor-text output" id="monitor-output-${agent.agent_id}">${this._formatMarkdown(monitor.output || '等待输出')}</div>
                        </details>
                    </div>
                </section>
            `;
        }

        container.innerHTML = html;

        // Auto-scroll to the currently working agent
        this._scrollToActiveAgent(active);
    },

    _scrollToActiveAgent(active) {
        // Don't auto-scroll if user is manually scrolling
        if (this._userScrolling) return;

        if (active) {
            const panel = document.querySelector(`.monitor-panel.${active.agent.status}`);
            if (panel) {
                panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    },

    _setupScrollListener() {
        const container = document.getElementById('tab-content');
        if (!container) return;

        container.addEventListener('scroll', () => {
            this._userScrolling = true;
            if (this._scrollTimeout) clearTimeout(this._scrollTimeout);
            this._scrollTimeout = setTimeout(() => {
                this._userScrolling = false;
            }, 3000); // Resume auto-scroll after 3s of no user scrolling
        }, { passive: true });
    },

    _deriveMonitorState(agentId, events = []) {
        const state = this.agentMonitorState[agentId] || {};
        for (const event of events) {
            if (event.event_type === 'prompt_issued' && event.payload?.prompt) {
                state.prompt = event.payload.prompt;
            }
            if (event.event_type === 'output_captured' && event.payload?.output) {
                state.output = event.payload.output;
            }
            state.metaText = `${event.title} · ${event.message}`;
            state.stage = event.stage;
        }
        this.agentMonitorState[agentId] = state;
        return state;
    },

    _escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    },

    _formatMarkdown(value) {
        return this._escapeHtml(value)
            .replace(/^### (.+)$/gm, '<h3>$1</h3>')
            .replace(/^## (.+)$/gm, '<h2>$1</h2>')
            .replace(/^# (.+)$/gm, '<h1>$1</h1>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/^- (.+)$/gm, '<li>$1</li>')
            .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
            .replace(/\n/g, '<br>');
    },

    _playShotVideo(thumbnail, videoUrl) {
        if (!videoUrl) return;
        const row = thumbnail.closest('.shot-row');
        if (!row) return;
        const shotId = thumbnail.closest('.shot-row').querySelector('[id^="shot-video-"]')?.id?.replace('shot-video-', '');
        if (!shotId) return;
        const container = document.getElementById(`shot-video-${shotId}`);
        if (container) {
            container.style.display = container.style.display === 'none' ? 'block' : 'none';
        }
    },

    _stageTitle(stage) {
        return stage ? (STAGE_TITLES[stage] || stage) : '';
    },

    _agentName(agentId) {
        return AGENT_META[agentId]?.name || 'Agent';
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

    _applyAgentMonitorUpdate(data) {
        const agentId = data.agent_id;
        if (!agentId) return;
        const state = this.agentMonitorState[agentId] || {};
        if (data.prompt) state.prompt = data.prompt;
        if (data.reset_output) state.output = '';
        if (data.output_chunk) state.output = (state.output || '') + data.output_chunk;
        if (data.output_text) state.output = data.output_text;
        if (data.current_task) state.currentTask = data.current_task;
        if (data.title || data.message) state.metaText = [data.title, data.message].filter(Boolean).join(' · ');
        if (data.stage) state.stage = data.stage;
        this.agentMonitorState[agentId] = state;

        const updateText = (id, text, fallback) => {
            const el = document.getElementById(id);
            if (!el) return;
            if (id.includes('output-') && el.classList.contains('agent-monitor-text')) {
                el.innerHTML = this._formatMarkdown(text || fallback);
            } else {
                el.textContent = text || fallback;
            }
            if (id.includes('output-')) el.scrollTop = el.scrollHeight;
        };

        updateText(`monitor-prompt-${agentId}`, state.prompt, '暂无提示词');
        updateText(`monitor-output-${agentId}`, state.output, '等待输出');
        updateText(`monitor-meta-${agentId}`, state.metaText, '暂无执行反馈');
        updateText(`monitor-task-${agentId}`, state.currentTask, '等待任务');
        updateText(`monitor-sidebar-task-${agentId}`, state.currentTask, '等待任务');
        updateText(`agent-task-${agentId}`, state.currentTask, '等待任务');
        updateText(`monitor-stage-${agentId}`, this._stageTitle(state.stage), '未进入阶段');
        updateText(`monitor-prompt-preview-${agentId}`, this._monitorPreview(state.prompt, '暂无提示词'), '暂无提示词');
        updateText(`monitor-output-preview-${agentId}`, this._monitorPreview(state.output, '等待输出'), '等待输出');
        updateText(`monitor-prompt-stat-${agentId}`, this._monitorStatText(state.prompt, '暂无提示词'), '暂无提示词');
        updateText(`monitor-output-stat-${agentId}`, this._monitorStatText(state.output, '等待输出'), '等待输出');

        const outputCard = document.getElementById(`monitor-output-card-${agentId}`);
        if (outputCard && state.output) outputCard.open = true;
    },

    _renderCharacters(container, project) {
        let html = '<div class="characters-grid">';
        for (const char of project.characters) {
            const roleColors = { '\u5973\u4E3B\u89D2': '#e94560', '\u7537\u4E3B\u89D2': '#3b82f6', '\u5973\u914D\u89D2': '#8b5cf6', '\u7537\u914D\u89D2': '#10b981', '\u53CD\u6D3E': '#ef4444' };
            const color = roleColors[char.role] || '#6b7280';
            html += `
                <div class="character-card">
                    <div class="character-info">
                        <h3>${char.name}</h3>
                        <div class="character-meta">${char.age}\u5C81 \xB7 ${char.role}</div>
                        <div class="character-desc">${char.description}</div>
                    </div>
                    ${char.sheet_url
                        ? `<div class="character-sheet"><img src="${MEDIA_BASE}${char.sheet_url}" alt="${char.name} \u8BBE\u5B9A\u56FE"></div>`
                        : ''
                    }
                </div>
            `;
        }
        html += '</div>';
        container.innerHTML = html;
    },

    _renderEpisodes(container, project) {

        let html = `
            <div class="episodes-table-container">
            <table class="episodes-table">
                <thead>
                    <tr>
                        <th>\u96C6\u6570</th>
                        <th>\u6807\u9898</th>
                        <th>\u72B6\u6001</th>
                        <th>\u8FDB\u5EA6</th>
                        <th>\u65F6\u957F</th>
                        <th>\u64CD\u4F5C</th>
                    </tr>
                </thead>
                <tbody>
        `;

        for (const ep of project.episodes) {
            html += `
                <tr class="episode-row" data-epid="${ep.episode_id}">
                    <td>${ep.episode_number}</td>
                    <td>${ep.title}</td>
                    <td>
                        <span class="episode-status ${ep.status}">
                            ${EPISODE_STATUS_LABELS[ep.status] || ep.status}
                        </span>
                    </td>
                    <td>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <div class="episode-progress-bar">
                                <div class="episode-progress-fill ${ep.status === 'completed' ? 'completed' : ''}" style="width: ${ep.progress || 0}%"></div>
                            </div>
                            <span style="font-size: 12px; color: var(--text-secondary); min-width: 35px;">${ep.progress || 0}%</span>
                        </div>
                    </td>
                    <td style="color: var(--text-secondary);">${ep.duration || '-'}</td>
                    <td>
                        <button class="btn-secondary btn-sm" onclick="ProjectView.showEpisodeDetail('${ep.episode_id}')">详情</button>
                    </td>
                </tr>
            `;
        }

        html += '</tbody></table></div>';
        html += '<div id="episode-detail-panel"></div>';
        container.innerHTML = html;
    },

    async showEpisodeDetail(episodeId) {
        const panel = document.getElementById('episode-detail-panel');
        const projectId = this.currentProjectId;

        try {
            const [episode, traces] = await Promise.all([
                fetch(`http://localhost:8000/api/v1/projects/${projectId}/episodes/${episodeId}`).then(r => r.json()),
                Api.getEpisodeTraces(projectId, episodeId),
            ]);
            const episodeStatusLabel = EPISODE_STATUS_LABELS[episode.status] || episode.status;

            let html = `
                <div class="episode-detail-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                        <h3>第${episode.episode_number}集: ${episode.title}</h3>
                        <button class="btn-secondary btn-sm" onclick="document.getElementById('episode-detail-panel').innerHTML=''">关闭</button>
                    </div>

                    <div style="margin-bottom: 16px;">
                        <span class="episode-status ${episode.status}" style="font-size: 13px;">
                            ${episodeStatusLabel}
                        </span>
                    </div>
            `;

            // Stage-gated display: only show sections when their data exists

            // Outline section (available before script generation)
            if (episode.outline && Object.keys(episode.outline).length > 0) {
                const o = episode.outline;
                html += `
                    <div class="section-title" style="margin-top: 16px;">本集概要</div>
                    <div class="card" style="padding: 12px;">
                        ${o.hook ? `<div style="margin-bottom: 8px;"><strong>开场钩子：</strong><span style="color: var(--text-secondary);">${o.hook}</span></div>` : ''}
                        ${o.escalation ? `<div style="margin-bottom: 8px;"><strong>中段升级：</strong><span style="color: var(--text-secondary);">${o.escalation}</span></div>` : ''}
                        ${o.cliffhanger ? `<div style="margin-bottom: 8px;"><strong>结尾悬念：</strong><span style="color: var(--text-secondary);">${o.cliffhanger}</span></div>` : ''}
                        ${o.scenes ? `<div><strong>关键场景：</strong><span style="color: var(--text-secondary);">${o.scenes}</span></div>` : ''}
                    </div>
                `;
            }

            // Manual generation buttons
            if (episode.status !== 'completed') {
                html += `
                    <div style="margin-top: 16px; display: flex; gap: 8px; flex-wrap: wrap;">
                `;
                if (!episode.has_script) {
                    html += `<button class="btn-primary btn-sm" onclick="ProjectView.triggerGenerate('${projectId}', 'script')">生成剧本</button>`;
                }
                if (episode.has_script && !episode.has_storyboard) {
                    html += `<button class="btn-primary btn-sm" onclick="ProjectView.triggerGenerate('${projectId}', 'format')">生成分镜</button>`;
                }
                if (episode.has_storyboard && episode.status === 'rendering') {
                    html += `<button class="btn-primary btn-sm" onclick="ProjectView.triggerGenerate('${projectId}', 'shots', '${episodeId}')">生成视频</button>`;
                }
                html += `</div>`;
            }

            if (episode.has_script && episode.script) {
                html += `
                    <div class="section-title" style="margin-top: 16px;">剧本</div>
                    <div class="card" style="padding: 12px; max-height: 200px; overflow-y: auto;">
                        ${(episode.script.scenes || []).map(s => `
                            <div style="margin-bottom: 8px;">
                                <strong>场景${s.scene_number}: ${s.location}</strong> (${s.time_of_day || ''})
                                <p style="color: var(--text-secondary); font-size: 13px; margin: 4px 0;">${s.description}</p>
                                ${(s.dialogues || []).map(d => `<div style="padding-left: 12px; font-size: 13px;"><em>${d.character}</em>: ${d.line} <span style="color: var(--text-tertiary);">[${d.emotion}]</span></div>`).join('')}
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            if (episode.has_storyboard && episode.storyboard && episode.storyboard.length > 0) {
                html += `
                    <div class="section-title" style="margin-top: 16px;">分镜 (${episode.storyboard.length} 个镜头)</div>
                    <div class="storyboard-grid">
                        ${episode.storyboard.map(s => `
                            <div class="shot-card">
                                <div class="shot-number">镜头 ${s.shot_number}</div>
                                <div class="shot-desc">${s.description}</div>
                                <div class="shot-meta">${s.camera_movement} \xB7 ${s.duration}</div>
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            // Timeline from production events
            if (episode.timeline && episode.timeline.length > 0) {
                html += `
                    <div class="section-title" style="margin-top: 16px;">生产时间线</div>
                    <div class="timeline-list">
                        ${episode.timeline.map(e => {
                            const agent = AGENT_META[e.agent_id] || { icon: 'smart_toy', color: '#6b7280', name: 'Agent' };
                            return `
                                <div class="timeline-entry">
                                    <div class="timeline-icon" style="background: ${agent.color}"><span class="material-symbols-outlined">${agent.icon}</span></div>
                                    <div class="timeline-content">
                                        <div class="timeline-header">
                                            <span class="timeline-agent">${this._escapeHtml(agent.name || this._agentName(e.agent_id))}</span>
                                            <span class="timeline-title">${this._escapeHtml(e.title)}</span>
                                            <span class="timeline-time">${new Date(e.created_at).toLocaleTimeString()}</span>
                                        </div>
                                        <div class="timeline-message">${this._escapeHtml(e.message)}</div>
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                `;
            }

            // Traces
            if (traces.traces && traces.traces.length > 0) {
                html += `
                    <div class="section-title" style="margin-top: 16px;">执行追踪</div>
                    <div class="trace-list">
                        ${traces.traces.map(t => `
                            <div class="trace-entry ${t.error_reason ? 'error' : ''}">
                                <div class="trace-header">
                                    <span class="trace-stage">${this._escapeHtml(this._stageTitle(t.stage) || t.stage)}</span>
                                    <span class="trace-agent">${this._escapeHtml(this._agentName(t.agent_id) || t.agent_id || '')}</span>
                                    <span class="trace-time">${new Date(t.created_at).toLocaleTimeString()}</span>
                                    ${t.cache_hit ? '<span class="trace-badge cached">缓存命中</span>' : ''}
                                </div>
                                ${t.prompt_summary ? `<div class="trace-detail">Prompt: ${this._escapeHtml(t.prompt_summary)}</div>` : ''}
                                ${t.output_path ? `<div class="trace-detail">Output: ${this._escapeHtml(t.output_path)}</div>` : ''}
                                ${t.error_reason ? `<div class="trace-error">Error: ${t.error_reason}</div>` : ''}
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            // Shots - stage gated: only show if storyboard exists
            if (episode.shots && episode.shots.length > 0) {
                html += `
                    <div class="section-title" style="margin-top: 16px;">分镜视频</div>
                    <div class="shots-table">
                        ${episode.shots.map(s => `
                            <div class="shot-row" style="flex-wrap: wrap;">
                                <div style="display:flex; align-items:center; gap:12px; flex:1; min-width:200px;">
                                    ${s.first_frame_path ? `<img src="${MEDIA_BASE}${s.first_frame_path}" class="shot-thumbnail" onclick="ProjectView._playShotVideo(this, '${s.video_url || ''}')">` : '<div class="shot-thumbnail" style="display:flex;align-items:center;justify-content:center;color:var(--text-tertiary);font-size:11px;">无图片</div>'}
                                    <div class="shot-info">
                                        <span><strong>镜头 ${s.shot_number}</strong></span>
                                        <span class="episode-status ${s.status}" style="margin-left:8px;">${s.status}</span>
                                    </div>
                                </div>
                                <div style="font-size:12px; color:var(--text-secondary); margin-top:4px; width:100%; padding-left:0;">${s.description || ''}</div>
                                ${s.video_url ? `<a href="${MEDIA_BASE}${s.video_url}" target="_blank" class="btn-secondary btn-sm" style="flex-shrink:0;">查看视频</a>` : ''}
                            </div>
                            ${s.video_url ? `<div class="shot-video-container" id="shot-video-${s.shot_id}" style="display:none; margin-top:8px;"><video src="${MEDIA_BASE}${s.video_url}" controls style="width:100%;max-width:480px;border-radius:6px;"></video></div>` : ''}
                        `).join('')}
                    </div>
                `;
            }

            // Episode video player
            if (episode.video_url) {
                html += `
                    <div class="section-title" style="margin-top: 16px;">剧集视频</div>
                    <div style="margin-top: 8px;">
                        <video src="${MEDIA_BASE}${episode.video_url}" controls style="width:100%; max-width:640px; border-radius:8px; background:#000;"></video>
                    </div>
                `;
            }

            html += '</div>';
            panel.innerHTML = html;
        } catch (err) {
            panel.innerHTML = `<div class="error-state"><p>加载剧集详情失败: ${err.message}</p></div>`;
        }
    },

    async startProduction() {
        if (!this.currentProjectId) return;
        try {
            await Api.startProjectProduction(this.currentProjectId);
            const project = await Api.getProject(this.currentProjectId);
            if (project) {
                this._renderHeader(project);
                this._renderTab(this.currentTab, project);
            }
        } catch (err) {
            console.error('Start production failed:', err);
        }
    },

    async triggerGenerate(projectId, stage, episodeId = null) {
        try {
            const baseUrl = 'http://localhost:8000/api/v1';
            const endpoint = stage === 'script' ? `${baseUrl}/projects/${projectId}/generate-script`
                           : stage === 'format' ? `${baseUrl}/projects/${projectId}/format-script`
                           : episodeId ? `${baseUrl}/projects/${projectId}/episodes/${episodeId}/generate-shots`
                           : `${baseUrl}/projects/${projectId}/generate-shots`;
            const resp = await fetch(endpoint, { method: 'POST' });
            if (!resp.ok) {
                const err = await resp.json();
                alert(err.detail || '生成失败');
                return;
            }
            // Refresh after a short delay
            setTimeout(() => {
                const project = Api.getProject(projectId).then(p => {
                    if (p) {
                        this._renderHeader(p);
                        this._renderTab(this.currentTab, p);
                    }
                });
            }, 2000);
        } catch (err) {
            console.error('Trigger generate failed:', err);
        }
    },

    async _handleWsMessage(msg) {
        if (!this.currentProjectId) return;

        switch (msg.type) {
            case 'agent_monitor': {
                this._applyAgentMonitorUpdate(msg.data || {});
                break;
            }
            case 'progress_update':
            case 'agent_update':
            case 'episode_completed':
            case 'project_completed':
            case 'stage_update': {
                const project = await Api.getProject(this.currentProjectId);
                if (project) {
                    this._renderHeader(project);
                    this._renderTab(this.currentTab, project);
                }
                break;
            }
            case 'trace_update': {
                break;
            }
        }
    },
};
