/**
 * Project detail view - linear pipeline stepper with 5 Agent identities.
 */

const AGENT_META = {
    agent_director: {
        icon: 'assignment',
        description: '',
        color: '#6c5ce7',
        get name() { return I18n.t('project.agent.director'); },
    },
    agent_chief_director: {
        icon: 'movie_creation',
        description: '',
        color: '#e17055',
        get name() { return I18n.t('project.agent.chief_director'); },
    },
    agent_visual: {
        icon: 'palette',
        description: '',
        color: '#00b894',
        get name() { return I18n.t('project.agent.visual'); },
    },
    agent_prompt: {
        icon: 'edit_note',
        description: '',
        color: '#fdcb6e',
        get name() { return I18n.t('project.agent.prompt'); },
    },
    agent_editor: {
        icon: 'video_library',
        description: '',
        color: '#74b9ff',
        get name() { return I18n.t('project.agent.editor'); },
    },
};
const AGENT_ORDER = Object.keys(AGENT_META);

// Pipeline stages for the linear stepper
const PIPELINE_STAGES = [
    { stage: 'requirements_confirmed', get label() { return I18n.t('project.stage.requirements_confirmed'); }, agent: 'agent_director' },
    { stage: 'script_completed', get label() { return I18n.t('project.stage.script_completed'); }, agent: 'agent_chief_director' },
    { stage: 'format_completed', get label() { return I18n.t('project.stage.format_completed'); }, agent: 'agent_prompt' },
    { stage: 'assets_completed', get label() { return I18n.t('project.stage.assets_completed'); }, agent: 'agent_visual' },
    { stage: 'shots_completed', get label() { return I18n.t('project.stage.shots_completed'); }, agent: 'agent_visual' },
    { stage: 'project_completed', get label() { return I18n.t('project.stage.project_completed'); }, agent: 'agent_editor' },
];

const STAGE_TITLES = {
    requirements_confirmed: () => I18n.t('project.stage.requirements_confirmed'),
    script_generating: () => I18n.t('project.stage.script_generating'),
    script_completed: () => I18n.t('project.stage.script_completed'),
    format_generating: () => I18n.t('project.stage.format_generating'),
    format_completed: () => I18n.t('project.stage.format_completed'),
    assets_generating: () => I18n.t('project.stage.assets_generating'),
    assets_completed: () => I18n.t('project.stage.assets_completed'),
    shots_generating: () => I18n.t('project.stage.shots_generating'),
    shots_completed: () => I18n.t('project.stage.shots_completed'),
    episode_composing: () => I18n.t('project.stage.episode_composing'),
    episode_completed: () => I18n.t('project.stage.episode_completed'),
    project_completed: () => I18n.t('project.stage.project_completed'),
};

const EPISODE_STATUS_LABELS = {
    completed: () => I18n.t('project.epStatus.completed'),
    editing: () => I18n.t('project.epStatus.editing'),
    rendering: () => I18n.t('project.epStatus.rendering'),
    asset_generating: () => I18n.t('project.epStatus.asset_generating'),
    storyboarding: () => I18n.t('project.epStatus.storyboarding'),
    scripting: () => I18n.t('project.epStatus.scripting'),
    pending: () => I18n.t('project.epStatus.pending'),
    qc_checking: () => I18n.t('project.epStatus.qc_checking'),
    failed: () => I18n.t('project.epStatus.failed'),
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
    _lastProjectSnapshot: '',
    async show(projectId) {
        this.currentProjectId = projectId;
        this.currentTab = 'overview';
        this.agentMonitorState = {};
        this._userScrolling = false;

        if (this._refreshTimer) {
            clearInterval(this._refreshTimer);
            this._refreshTimer = null;
        }

        if (window.VideoView && VideoView._timer) {
            clearInterval(VideoView._timer);
            VideoView._timer = null;
        }

        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }

        document.getElementById('view-new-project').classList.add('hidden');
        document.getElementById('view-settings').classList.add('hidden');
        document.getElementById('view-video').classList.add('hidden');
        document.getElementById('view-dubbing').classList.add('hidden');
        document.getElementById('view-project-detail').classList.remove('hidden');

        document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
        document.querySelectorAll('.project-nav-item').forEach(el => el.classList.remove('active'));
        const navItem = document.querySelector(`.project-nav-item[data-pid="${projectId}"]`);
        if (navItem) navItem.classList.add('active');

        this._setupScrollListener();

        const project = await Api.getProject(projectId);
        if (!project) return;

        this._lastProjectSnapshot = JSON.stringify(project);
        this._renderHeader(project);
        this._renderContent(project);

        this.ws = Api.connectWebSocket(projectId, (msg) => this._handleWsMessage(msg));
        this._refreshTimer = setInterval(() => this.refresh(), 5000);
    },

    async refresh() {
        if (!this.currentProjectId || document.getElementById('view-project-detail').classList.contains('hidden')) return;
        const project = await Api.getProject(this.currentProjectId);
        if (!project) return;
        const snapshot = JSON.stringify(project);
        if (snapshot === this._lastProjectSnapshot) return;
        this._lastProjectSnapshot = snapshot;
        this._renderHeader(project);
        this._renderTab(this.currentTab, project);
        App.refreshProjectList();
    },

    _renderHeader(project) {
        const header = document.getElementById('project-detail-header');
        const statusLabels = {
            pending: I18n.t('project.status.pending'),
            in_progress: I18n.t('project.status.in_progress'),
            completed: I18n.t('project.status.completed'),
            paused: I18n.t('project.status.paused'),
            failed: I18n.t('project.status.failed'),
        };

        header.innerHTML = `
            <div class="project-header-bar">
                <div class="project-title-area">
                    <h1>${project.title}</h1>
                    <span class="project-badge ${project.status}">${statusLabels[project.status] || project.status}</span>
                </div>
                <div class="project-actions">
                    ${project.status === 'pending' ? `
                        <button class="btn-primary" onclick="ProjectView.startProduction()">${I18n.t('project.startProduction')}</button>
                    ` : ''}
                    <button class="btn-secondary" onclick="navigateTo('new-project')">${I18n.t('project.newProject')}</button>
                </div>
            </div>
        `;
    },

    _renderContent(project) {
        const content = document.getElementById('project-detail-content');
        content.innerHTML = `
            <div class="tabs">
                <button class="tab-btn active" onclick="ProjectView.switchTab('overview')">${I18n.t('project.tab.overview')}</button>
                <button class="tab-btn" onclick="ProjectView.switchTab('monitor')">${I18n.t('project.tab.monitor')}</button>
                <button class="tab-btn" onclick="ProjectView.switchTab('pipeline')">${I18n.t('project.tab.pipeline')}</button>
                <button class="tab-btn" onclick="ProjectView.switchTab('characters')">${I18n.t('project.tab.characters')}</button>
                <button class="tab-btn" onclick="ProjectView.switchTab('episodes')">${I18n.t('project.tab.episodes')}</button>
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
            overview: I18n.t('project.tab.overview'),
            monitor: I18n.t('project.tab.monitor'),
            pipeline: I18n.t('project.tab.pipeline'),
            characters: I18n.t('project.tab.characters'),
            episodes: I18n.t('project.tab.episodes'),
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
        container.innerHTML = `
            <div class="pipeline-container">
                <div class="section-title">${I18n.t('project.pipeline.title')}</div>
                <div id="pipeline-timeline"><div style="color: var(--text-tertiary); text-align: center; padding: 24px;">${I18n.t('project.pipeline.loading')}</div></div>
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
                timelineEl.innerHTML = `<div style="color: var(--text-tertiary); text-align: center; padding: 24px;">${I18n.t('project.pipeline.noEvents')}</div>`;
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
                                <span class="timeline-title">${this._escapeHtml(e.title)}</span>
                                <span class="timeline-time">${new Date(e.created_at).toLocaleTimeString(I18n.getLocale())}</span>
                            </div>
                            <div class="timeline-message">${this._escapeHtml(e.message)}</div>
                        </div>
                    </div>
                `;
            }
            html += '</div>';
            timelineEl.innerHTML = html;
        } catch (err) {
            const timelineEl = document.getElementById('pipeline-timeline');
            if (timelineEl) timelineEl.innerHTML = `<div style="color: var(--text-tertiary); text-align: center;">${I18n.t('project.pipeline.loadFailed')}</div>`;
        }
    },

    _renderOverview(container, project) {
        const completed = project.episodes.filter(e => e.status === 'completed').length;
        const inProgress = project.episodes.filter(e => e.status !== 'completed' && e.status !== 'pending').length;
        const pending = project.episodes.filter(e => e.status === 'pending').length;

        container.innerHTML = `
            <div class="progress-overview">
                <div class="stat-card">
                    <div class="stat-card-label">${I18n.t('project.overallProgress')}</div>
                    <div class="stat-card-value">${project.progress}%</div>
                    <div class="progress-bar-wrapper">
                        <div class="progress-bar-track">
                            <div class="progress-bar-fill success" style="width: ${project.progress}%"></div>
                        </div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-label">${I18n.t('project.completed')}</div>
                    <div class="stat-card-value">${completed}</div>
                    <div class="stat-card-sub">${I18n.t('project.episodesTotal', { n: project.episodes.length })}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-label">${I18n.t('project.inProgress')}</div>
                    <div class="stat-card-value">${inProgress}</div>
                    <div class="stat-card-sub">${I18n.t('project.inProgressSub')}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-label">${I18n.t('project.pending')}</div>
                    <div class="stat-card-value">${pending}</div>
                    <div class="stat-card-sub">${I18n.t('project.pendingSub')}</div>
                </div>
            </div>

            <div class="section-title">${I18n.t('project.currentStage')}</div>
            <div id="overview-agents"></div>
        `;

        this._renderAgentsMini(document.getElementById('overview-agents'), project);
    },

    _agentStatusText(status) {
        return status === 'working' ? I18n.t('project.agentStatus.working') : status === 'error' ? I18n.t('project.agentStatus.error') : I18n.t('project.agentStatus.idle');
    },

    async _renderAgentsMini(container, project) {
        const agentsData = await Api.getAgents(project.project_id);
        let html = '<div class="agents-grid">';
        for (const agent of this._orderedAgents(agentsData.agents || [])) {
            const meta = AGENT_META[agent.agent_id] || { icon: 'smart_toy', description: '', color: '#6b7280' };
            const progress = agent.total_tasks > 0 ? Math.round(agent.completed_tasks / agent.total_tasks * 100) : 0;
            const showTaskTotal = agent.agent_id !== 'agent_editor';
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
                    <div class="agent-task">${this._escapeHtml(agent.current_task || I18n.t('project.waitingTask'))}</div>
                    ${showTaskTotal ? `
                    <div class="agent-progress">
                        <span>${agent.completed_tasks} / ${agent.total_tasks}</span>
                        <span>${progress}%</span>
                    </div>
                    <div class="progress-bar-track">
                        <div class="progress-bar-fill" style="width: ${progress}%; background: ${meta.color}"></div>
                    </div>
                    ` : ''}
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
        const currentStageLabel = this._stageTitle(project.current_stage) || I18n.t('project.monitor.notStarted');

        let html = `
            <section class="monitor-hero">
                <div class="monitor-hero-main">
                    <div class="monitor-hero-heading">
                        <div>
                            <div class="section-title" style="margin: 0;">${I18n.t('project.monitor.title')}</div>
                        </div>
                        <div class="monitor-stage-badge ${project.status}">${this._escapeHtml(currentStageLabel)}</div>
                    </div>
                    <div class="monitor-hero-task">${active ? this._escapeHtml(active.agent.current_task || active.monitor.currentTask || I18n.t('project.waitingTask')) : I18n.t('project.monitor.noActiveTask')}</div>
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
                                        <div class="monitor-stage-chip-meta">${this._escapeHtml(stageAgent?.name || I18n.t('project.monitor.toBeAssigned'))}</div>
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
                <div class="monitor-kpi-grid">
                    <div class="monitor-kpi-card primary">
                        <div class="monitor-kpi-label">${I18n.t('project.monitor.currentStage')}</div>
                        <div class="monitor-kpi-value small">${this._escapeHtml(currentStageLabel)}</div>
                        <div class="monitor-kpi-sub">${I18n.t('project.monitor.projectStatus', { status: this._escapeHtml(project.status) })}</div>
                    </div>
                    <div class="monitor-kpi-card">
                        <div class="monitor-kpi-label">${I18n.t('project.monitor.activeAgents')}</div>
                        <div class="monitor-kpi-value">${workingAgents}</div>
                        <div class="monitor-kpi-sub">${I18n.t('project.monitor.seatsOnline', { n: orderedAgents.length })}</div>
                    </div>
                    <div class="monitor-kpi-card">
                        <div class="monitor-kpi-label">${I18n.t('project.monitor.overallProgress')}</div>
                        <div class="monitor-kpi-value">${project.progress}%</div>
                        <div class="monitor-kpi-sub">${project.episodes?.length || 0} ${I18n.t('project.monitor.episodes')}</div>
                    </div>
                </div>
            </section>
        `;

        for (const { agent, events, monitor } of agentDetails) {
            const meta = AGENT_META[agent.agent_id] || { icon: 'smart_toy', description: '', color: '#6b7280' };
            const stageLabel = this._stageTitle(monitor.stage) || I18n.t('project.monitor.notInStage');
            const progress = agent.total_tasks > 0 ? Math.round((agent.completed_tasks / agent.total_tasks) * 100) : 0;
            const showTaskTotal = agent.agent_id !== 'agent_editor';
            const noPrompt = I18n.t('project.monitor.noPrompt');
            const waitOut = I18n.t('project.monitor.waitingOutput');
            html += `
                <section class="monitor-panel ${agent.status}">
                    <div class="monitor-panel-header">
                        <div class="monitor-panel-title" style="color: ${meta.color};display:flex;align-items:center;gap:6px;"><span class="material-symbols-outlined" style="font-size:20px;">${meta.icon}</span> ${agent.name}</div>
                        <div class="monitor-panel-badges">
                            <span class="monitor-pill stage" id="monitor-stage-${agent.agent_id}">${this._escapeHtml(stageLabel)}</span>
                            <span class="monitor-pill status ${agent.status}">${this._agentStatusText(agent.status)}</span>
                        </div>
                    </div>
                    <div class="agent-task" id="monitor-task-${agent.agent_id}">${this._escapeHtml(agent.current_task || monitor.currentTask || I18n.t('project.waitingTask'))}</div>
                    ${showTaskTotal ? `
                    <div class="monitor-mini-stats">
                        <div class="monitor-mini-stat">
                            <span>${I18n.t('project.monitor.tasks')}</span>
                            <strong>${agent.completed_tasks} / ${agent.total_tasks}</strong>
                        </div>
                        <div class="monitor-mini-stat">
                            <span>${I18n.t('project.monitor.progress')}</span>
                            <strong>${progress}%</strong>
                        </div>
                    </div>
                    ` : ''}
                    <div class="monitor-stream-grid">
                        <details class="monitor-stream-card prompt" id="monitor-prompt-card-${agent.agent_id}">
                            <summary class="monitor-stream-summary">
                                <div class="monitor-stream-copy">
                                    <div class="agent-monitor-label">${I18n.t('project.monitor.latestPrompt')}</div>
                                    <div class="monitor-stream-preview" id="monitor-prompt-preview-${agent.agent_id}">${this._escapeHtml(this._monitorPreview(monitor.prompt, noPrompt))}</div>
                                </div>
                                <div class="monitor-stream-meta" id="monitor-prompt-stat-${agent.agent_id}">${this._escapeHtml(this._monitorStatText(monitor.prompt, noPrompt))}</div>
                            </summary>
                            <pre class="agent-monitor-text prompt" id="monitor-prompt-${agent.agent_id}">${this._escapeHtml(monitor.prompt || noPrompt)}</pre>
                        </details>
                        <details class="monitor-stream-card output" id="monitor-output-card-${agent.agent_id}" ${(monitor.output || agent.status === 'working') ? 'open' : ''}>
                            <summary class="monitor-stream-summary">
                                <div class="monitor-stream-copy">
                                    <div class="agent-monitor-label">${I18n.t('project.monitor.realtimeFeedback')}</div>
                                    <div class="monitor-stream-preview" id="monitor-output-preview-${agent.agent_id}">${this._escapeHtml(this._monitorPreview(monitor.output, waitOut))}</div>
                                </div>
                                <div class="monitor-stream-meta" id="monitor-output-stat-${agent.agent_id}">${this._escapeHtml(this._monitorStatText(monitor.output, waitOut))}</div>
                            </summary>
                            <div class="agent-monitor-text output" id="monitor-output-${agent.agent_id}">${this._formatMarkdown(monitor.output || waitOut)}</div>
                        </details>
                    </div>
                </section>
            `;
        }

        container.innerHTML = html;
        this._scrollToActiveAgent(active);
    },

    _scrollToActiveAgent(active) {
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
            }, 3000);
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
        return stage ? (STAGE_TITLES[stage] ? STAGE_TITLES[stage]() : stage) : '';
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
        return I18n.t('project.monitor.lineChar', { lines: lineCount, chars: normalized.length });
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

        const noPrompt = I18n.t('project.monitor.noPrompt');
        const waitOut = I18n.t('project.monitor.waitingOutput');

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

        updateText(`monitor-prompt-${agentId}`, state.prompt, noPrompt);
        updateText(`monitor-output-${agentId}`, state.output, waitOut);
        updateText(`monitor-meta-${agentId}`, state.metaText, I18n.t('project.monitor.noFeedback'));
        updateText(`monitor-task-${agentId}`, state.currentTask, I18n.t('project.waitingTask'));
        updateText(`monitor-sidebar-task-${agentId}`, state.currentTask, I18n.t('project.waitingTask'));
        updateText(`agent-task-${agentId}`, state.currentTask, I18n.t('project.waitingTask'));
        updateText(`monitor-stage-${agentId}`, this._stageTitle(state.stage), I18n.t('project.monitor.notInStage'));
        updateText(`monitor-prompt-preview-${agentId}`, this._monitorPreview(state.prompt, noPrompt), noPrompt);
        updateText(`monitor-output-preview-${agentId}`, this._monitorPreview(state.output, waitOut), waitOut);
        updateText(`monitor-prompt-stat-${agentId}`, this._monitorStatText(state.prompt, noPrompt), noPrompt);
        updateText(`monitor-output-stat-${agentId}`, this._monitorStatText(state.output, waitOut), waitOut);

        const outputCard = document.getElementById(`monitor-output-card-${agentId}`);
        if (outputCard && state.output) outputCard.open = true;
    },

    _renderCharacters(container, project) {
        let html = '';

        // Characters section
        html += `<h3 class="section-title" style="margin-bottom: 12px;">${I18n.t('project.tab.characters')}</h3>`;
        html += '<div class="characters-grid">';
        for (const char of project.characters) {
            const roleColors = { '\u5973\u4E3B\u89D2': '#e94560', '\u7537\u4E3B\u89D2': '#3b82f6', '\u5973\u914D\u89D2': '#8b5cf6', '\u7537\u914D\u89D2': '#10b981', '\u53CD\u6D3E': '#ef4444' };
            const color = roleColors[char.role] || '#6b7280';
            html += `
                <div class="character-card">
                    <div class="character-info">
                        <h3>${char.name}</h3>
                        <div class="character-meta">${I18n.t('project.characters.ageUnit', { age: char.age })} \xB7 ${char.role}</div>
                        <div class="character-desc">${char.description}</div>
                    </div>
                    ${char.sheet_url
                        ? `<div class="character-sheet"><img src="${MEDIA_BASE}${char.sheet_url}" alt="${I18n.t('project.characters.sheetAlt', { name: char.name })}"></div>`
                        : ''
                    }
                </div>
            `;
        }
        html += '</div>';

        // Other assets section (scenes, props, etc.)
        const assets = project.assets || [];
        if (assets.length > 0) {
            const assetTypeLabels = {
                scene: I18n.t('project.assets.scene'),
                prop: I18n.t('project.assets.prop'),
                location: I18n.t('project.assets.location'),
                style: I18n.t('project.assets.style'),
            };
            html += `<h3 class="section-title" style="margin: 24px 0 12px;">${I18n.t('project.assets.title')}</h3>`;
            html += '<div class="characters-grid">';
            for (const asset of assets) {
                const typeLabel = assetTypeLabels[asset.type] || asset.type;
                html += `
                    <div class="character-card">
                        ${asset.image_path
                            ? `<div class="character-sheet"><img src="${MEDIA_BASE}${this._escapeAttr(asset.image_path)}" alt="${this._escape(asset.name || typeLabel)}"></div>`
                            : ''
                        }
                        <div class="character-info">
                            <h3>${this._escape(asset.name || typeLabel)}</h3>
                            <div class="character-meta">${typeLabel}</div>
                            ${asset.description ? `<div class="character-desc">${this._escape(asset.description)}</div>` : ''}
                            ${asset.prompt ? `<details style="margin-top:8px;"><summary style="font-size:12px;color:var(--text-secondary);cursor:pointer;">Prompt</summary><pre style="font-size:11px;white-space:pre-wrap;color:var(--text-secondary);margin-top:4px;">${this._escape(asset.prompt)}</pre></details>` : ''}
                        </div>
                    </div>
                `;
            }
            html += '</div>';
        }

        container.innerHTML = html;
    },

    _renderEpisodes(container, project) {
        let html = `
            <div class="episodes-table-container">
            <table class="episodes-table">
                <thead>
                    <tr>
                        <th>${I18n.t('project.episodes.header.ep')}</th>
                        <th>${I18n.t('project.episodes.header.title')}</th>
                        <th>${I18n.t('project.episodes.header.status')}</th>
                        <th>${I18n.t('project.episodes.header.progress')}</th>
                        <th>${I18n.t('project.episodes.header.duration')}</th>
                        <th>${I18n.t('project.episodes.header.actions')}</th>
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
                            ${EPISODE_STATUS_LABELS[ep.status] ? EPISODE_STATUS_LABELS[ep.status]() : ep.status}
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
                        <button class="btn-secondary btn-sm" onclick="ProjectView.showEpisodeDetail('${ep.episode_id}')">${I18n.t('project.episodes.detail')}</button>
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
            const episodeStatusLabel = EPISODE_STATUS_LABELS[episode.status] ? EPISODE_STATUS_LABELS[episode.status]() : episode.status;

            let html = `
                <div class="episode-detail-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                        <h3>${I18n.t('project.epDetail.episodeTitle', { n: episode.episode_number, title: episode.title })}</h3>
                        <button class="btn-secondary btn-sm" onclick="document.getElementById('episode-detail-panel').innerHTML=''">${I18n.t('project.epDetail.close')}</button>
                    </div>

                    <div style="margin-bottom: 16px;">
                        <span class="episode-status ${episode.status}" style="font-size: 13px;">
                            ${episodeStatusLabel}
                        </span>
                    </div>
            `;

            if (episode.outline && Object.keys(episode.outline).length > 0) {
                const o = episode.outline;
                html += `
                    <div class="section-title" style="margin-top: 16px;">${I18n.t('project.epDetail.summary')}</div>
                    <div class="card" style="padding: 12px;">
                        ${o.hook ? `<div style="margin-bottom: 8px;"><strong>${I18n.t('project.epDetail.hook')}</strong><span style="color: var(--text-secondary);">${o.hook}</span></div>` : ''}
                        ${o.escalation ? `<div style="margin-bottom: 8px;"><strong>${I18n.t('project.epDetail.escalation')}</strong><span style="color: var(--text-secondary);">${o.escalation}</span></div>` : ''}
                        ${o.cliffhanger ? `<div style="margin-bottom: 8px;"><strong>${I18n.t('project.epDetail.cliffhanger')}</strong><span style="color: var(--text-secondary);">${o.cliffhanger}</span></div>` : ''}
                        ${o.scenes ? `<div><strong>${I18n.t('project.epDetail.keyScenes')}</strong><span style="color: var(--text-secondary);">${o.scenes}</span></div>` : ''}
                    </div>
                `;
            }

            html += `
                <div style="margin-top: 16px; display: flex; gap: 8px; flex-wrap: wrap;">
                    ${!episode.has_script ? `<button class="btn-primary btn-sm" onclick="ProjectView.triggerGenerate('${projectId}', 'script')">${I18n.t('project.epDetail.generateScript')}</button>` : ''}
                    ${episode.has_script && !episode.has_storyboard ? `<button class="btn-primary btn-sm" onclick="ProjectView.triggerGenerate('${projectId}', 'format')">${I18n.t('project.epDetail.generateStoryboard')}</button>` : ''}
                    ${episode.has_storyboard ? `<button class="btn-primary btn-sm" onclick="ProjectView.triggerGenerate('${projectId}', 'shots', '${episodeId}')">${I18n.t('project.epDetail.generateShots')}</button>` : ''}
                    ${episode.has_storyboard ? `<button class="btn-secondary btn-sm" onclick="ProjectView.triggerGenerate('${projectId}', 'compose', '${episodeId}')">${I18n.t('project.epDetail.compose')}</button>` : ''}
                </div>
            `;

            if (episode.has_script && episode.script) {
                html += `
                    <div class="section-title" style="margin-top: 16px;">${I18n.t('project.epDetail.script')}</div>
                    <div class="card" style="padding: 12px; max-height: 200px; overflow-y: auto;">
                        ${(episode.script.scenes || []).map(s => `
                            <div style="margin-bottom: 8px;">
                                <strong>${I18n.t('project.epDetail.scene', { n: s.scene_number, location: s.location })}</strong> (${s.time_of_day || ''})
                                <p style="color: var(--text-secondary); font-size: 13px; margin: 4px 0;">${s.description}</p>
                                ${(s.dialogues || []).map(d => `<div style="padding-left: 12px; font-size: 13px;"><em>${d.character}</em>: ${d.line} <span style="color: var(--text-tertiary);">[${d.emotion}]</span></div>`).join('')}
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            if (episode.has_storyboard && episode.storyboard && episode.storyboard.length > 0) {
                html += `
                    <div class="section-title" style="margin-top: 16px;">${I18n.t('project.epDetail.storyboard', { n: episode.storyboard.length })}</div>
                    <div class="storyboard-grid">
                        ${episode.storyboard.map(s => `
                            <div class="shot-card">
                                <div class="shot-number">${I18n.t('project.epDetail.shot', { n: s.shot_number })}</div>
                                <div class="shot-desc">${s.description}</div>
                                <div class="shot-meta">${s.camera_movement} \xB7 ${s.duration}</div>
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            if (episode.timeline && episode.timeline.length > 0) {
                html += `
                    <div class="section-title" style="margin-top: 16px;">${I18n.t('project.epDetail.timeline')}</div>
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
                                            <span class="timeline-time">${new Date(e.created_at).toLocaleTimeString(I18n.getLocale())}</span>
                                        </div>
                                        <div class="timeline-message">${this._escapeHtml(e.message)}</div>
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                `;
            }

            if (traces.traces && traces.traces.length > 0) {
                html += `
                    <div class="section-title" style="margin-top: 16px;">${I18n.t('project.epDetail.traces')}</div>
                    <div class="trace-list">
                        ${traces.traces.map(t => `
                            <div class="trace-entry ${t.error_reason ? 'error' : ''}">
                                <div class="trace-header">
                                    <span class="trace-stage">${this._escapeHtml(this._stageTitle(t.stage) || t.stage)}</span>
                                    <span class="trace-agent">${this._escapeHtml(this._agentName(t.agent_id) || t.agent_id || '')}</span>
                                    <span class="trace-time">${new Date(t.created_at).toLocaleTimeString(I18n.getLocale())}</span>
                                    ${t.cache_hit ? `<span class="trace-badge cached">${I18n.t('project.epDetail.cacheHit')}</span>` : ''}
                                </div>
                                ${t.prompt_summary ? `<div class="trace-detail">Prompt: ${this._escapeHtml(t.prompt_summary)}</div>` : ''}
                                ${t.output_path ? `<div class="trace-detail">Output: ${this._escapeHtml(t.output_path)}</div>` : ''}
                                ${t.error_reason ? `<div class="trace-error">Error: ${t.error_reason}</div>` : ''}
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            if (episode.shots && episode.shots.length > 0) {
                html += `
                    <div class="section-title" style="margin-top: 16px;">${I18n.t('project.epDetail.shotVideos')}</div>
                    <div class="shots-table">
                        ${episode.shots.map(s => `
                            <div class="shot-row" style="flex-wrap: wrap;">
                                <div style="display:flex; align-items:center; gap:12px; flex:1; min-width:200px;">
                                    ${s.first_frame_path ? `<img src="${MEDIA_BASE}${s.first_frame_path}" class="shot-thumbnail" onclick="ProjectView._playShotVideo(this, '${s.video_url || ''}')">` : `<div class="shot-thumbnail" style="display:flex;align-items:center;justify-content:center;color:var(--text-tertiary);font-size:11px;">${I18n.t('project.epDetail.noImage')}</div>`}
                                    <div class="shot-info">
                                        <span><strong>${I18n.t('project.epDetail.shot', { n: s.shot_number })}</strong></span>
                                        <span class="episode-status ${s.status}" style="margin-left:8px;">${s.status}</span>
                                    </div>
                                </div>
                                <div style="font-size:12px; color:var(--text-secondary); margin-top:4px; width:100%; padding-left:0;">${s.description || ''}</div>
                                <div style="display:flex; gap:8px; flex-shrink:0;">
                                    <button class="btn-primary btn-sm" onclick="ProjectView.generateShot('${projectId}', '${episodeId}', '${s.shot_id}')">${I18n.t('project.epDetail.generate')}</button>
                                    ${s.video_url ? `<a href="${MEDIA_BASE}${s.video_url}" target="_blank" class="btn-secondary btn-sm">${I18n.t('project.epDetail.viewVideo')}</a>` : ''}
                                </div>
                            </div>
                            ${s.video_url ? `<div class="shot-video-container" id="shot-video-${s.shot_id}" style="display:none; margin-top:8px;"><video src="${MEDIA_BASE}${s.video_url}" controls style="width:100%;max-width:480px;border-radius:6px;"></video></div>` : ''}
                        `).join('')}
                    </div>
                `;
            }

            if (episode.video_url) {
                html += `
                    <div class="section-title" style="margin-top: 16px;">${I18n.t('project.epDetail.episodeVideo')}</div>
                    <div style="margin-top: 8px;">
                        <video src="${MEDIA_BASE}${episode.video_url}" controls style="width:100%; max-width:640px; border-radius:8px; background:#000;"></video>
                    </div>
                `;
            }

            html += '</div>';
            panel.innerHTML = html;
        } catch (err) {
            panel.innerHTML = `<div class="error-state"><p>${I18n.t('project.epDetail.loadFailed', { msg: err.message })}</p></div>`;
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
                           : stage === 'compose' && episodeId ? `${baseUrl}/projects/${projectId}/episodes/${episodeId}/compose`
                           : episodeId ? `${baseUrl}/projects/${projectId}/episodes/${episodeId}/generate-shots`
                           : `${baseUrl}/projects/${projectId}/generate-shots`;
            const resp = await fetch(endpoint, { method: 'POST' });
            if (!resp.ok) {
                const err = await resp.json();
                alert(err.detail || I18n.t('project.epDetail.genFailed'));
                return;
            }
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

    async generateShot(projectId, episodeId, shotId) {
        try {
            const res = await Api.generateShot(projectId, episodeId, shotId);
            if (res.detail) {
                alert(res.detail);
                return;
            }
            setTimeout(() => this.showEpisodeDetail(episodeId), 1000);
        } catch (err) {
            console.error('Generate shot failed:', err);
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
