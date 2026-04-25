/**
 * API 层 - 支持真实后端和 Mock 两种模式
 */

const API_BASE = 'http://localhost:8000/api/v1';
const MEDIA_BASE = 'http://localhost:8000';
const USE_MOCK = false; // 切换为 false 连接真实后端

const Api = {
    // ========== 会话管理 ==========

    async createConversation(initialIdea) {
        if (USE_MOCK) return MockApi.createConversation(initialIdea);
        const res = await fetch(`${API_BASE}/conversations`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initial_idea: initialIdea })
        });
        return res.json();
    },

    async sendMessage(conversationId, message) {
        if (USE_MOCK) return MockApi.sendMessage(conversationId, message);
        const res = await fetch(`${API_BASE}/conversations/${conversationId}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });
        return res.json();
    },

    async _streamPost(url, body, onChunk, onDone, onError) {
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            if (!response.body) {
                throw new Error('流式响应不可用');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            const emitEvent = (rawEvent) => {
                const dataLines = rawEvent
                    .split(/\r?\n/)
                    .filter(line => line.startsWith('data:'))
                    .map(line => line.slice(5).trimStart());
                if (!dataLines.length) return false;

                try {
                    const data = JSON.parse(dataLines.join('\n'));
                    if (data.error) {
                        onError?.(data.error);
                    } else if (data.done) {
                        onDone?.(data);
                    } else {
                        onChunk?.(data);
                    }
                    return true;
                } catch (error) {
                    return false;
                }
            };

            while (true) {
                const { done, value } = await reader.read();
                buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

                let separatorIndex = buffer.search(/\r?\n\r?\n/);
                while (separatorIndex !== -1) {
                    const separatorMatch = buffer.match(/\r?\n\r?\n/);
                    const separatorLength = separatorMatch ? separatorMatch[0].length : 2;
                    const eventBlock = buffer.slice(0, separatorIndex);
                    buffer = buffer.slice(separatorIndex + separatorLength);
                    emitEvent(eventBlock);
                    separatorIndex = buffer.search(/\r?\n\r?\n/);
                }

                if (done) {
                    const trimmed = buffer.trim();
                    if (trimmed) {
                        if (!emitEvent(trimmed)) {
                            try {
                                onDone?.(JSON.parse(trimmed));
                            } catch (error) {
                                throw new Error(trimmed.slice(0, 120));
                            }
                        }
                    }
                    break;
                }
            }
        } catch (err) {
            onError?.(err.message || String(err));
        }
    },

    streamMessage(conversationId, message, onChunk, onDone, onError) {
        return this._streamPost(
            `${API_BASE}/conversations/${conversationId}/messages/stream`,
            { message },
            onChunk,
            onDone,
            onError
        );
    },

    streamCreateConversation(initialIdea, onChunk, onDone, onError) {
        return this._streamPost(
            `${API_BASE}/conversations/stream`,
            { message: initialIdea },
            onChunk,
            onDone,
            onError
        );
    },

    generateOutline(conversationId, onChunk, onDone, onError) {
        return this._streamPost(
            `${API_BASE}/conversations/${conversationId}/generate-outline`,
            {},
            onChunk,
            onDone,
            onError
        );
    },

    async confirmOutline(conversationId) {
        if (USE_MOCK) return MockApi.confirmOutline(conversationId);
        const res = await fetch(`${API_BASE}/conversations/${conversationId}/confirm`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirmed: true })
        });
        return res.json();
    },

    async startProduction(conversationId) {
        if (USE_MOCK) return MockApi.startProduction(conversationId);
        const res = await fetch(`${API_BASE}/conversations/${conversationId}/start-production`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirmed: true })
        });
        return res.json();
    },

    // ========== 项目管理 ==========

    async getProjects() {
        if (USE_MOCK) return MockApi.getProjects();
        const res = await fetch(`${API_BASE}/projects`);
        return res.json();
    },

    async getProject(projectId) {
        if (USE_MOCK) return MockApi.getProject(projectId);
        const res = await fetch(`${API_BASE}/projects/${projectId}`);
        return res.json();
    },

    async deleteProject(projectId) {
        const res = await fetch(`${API_BASE}/projects/${projectId}`, {
            method: 'DELETE'
        });
        return res.json();
    },

    async continueProject(projectId) {
        const res = await fetch(`${API_BASE}/projects/${projectId}/continue`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        return res.json();
    },

    // ========== 智能体 ==========

    async getAgents(projectId) {
        if (USE_MOCK) return MockApi.getAgents(projectId);
        const res = await fetch(`${API_BASE}/projects/${projectId}/agents`);
        return res.json();
    },

    async getAgentLogs(projectId, agentId) {
        if (USE_MOCK) return MockApi.getAgentLogs(projectId, agentId);
        const res = await fetch(`${API_BASE}/projects/${projectId}/agents/${agentId}/logs`);
        return res.json();
    },

    // ========== WebSocket ==========

    connectWebSocket(projectId, onMessage) {
        const wsUrl = `ws://localhost:8000/ws/${projectId}`;
        const ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            console.log('WebSocket connected');
        };
        
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                onMessage(data);
            } catch (e) {
                console.error('WebSocket message parse error:', e);
            }
        };
        
        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
        
        ws.onclose = () => {
            console.log('WebSocket disconnected');
        };
        
        return ws;
    },

    startSimulation(projectId, ws) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'start_simulation' }));
        }
    },

    // ========== Settings ==========

    async getSettings() {
        const res = await fetch(`${API_BASE}/settings/models`);
        return res.json();
    },

    async updateSettings(config) {
        const res = await fetch(`${API_BASE}/settings/models`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        return res.json();
    },

    async testConnection(providerType) {
        const res = await fetch(`${API_BASE}/settings/test`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider_type: providerType })
        });
        return res.json();
    },

    // ========== Execution Control ==========

    async runProject(projectId) {
        const res = await fetch(`${API_BASE}/projects/${projectId}/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        return res.json();
    },

    async runEpisode(projectId, episodeId) {
        const res = await fetch(`${API_BASE}/projects/${projectId}/episodes/${episodeId}/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        return res.json();
    },

    async runShot(projectId, episodeId, shotId) {
        const res = await fetch(`${API_BASE}/projects/${projectId}/episodes/${episodeId}/shots/${shotId}/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        return res.json();
    },

    async generateShot(projectId, episodeId, shotId) {
        const res = await fetch(`${API_BASE}/projects/${projectId}/episodes/${episodeId}/shots/${shotId}/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        return res.json();
    },

    async getVideoTasks() {
        const res = await fetch(`${API_BASE}/video/tasks`);
        return res.json();
    },

    async getEpisodeTraces(projectId, episodeId) {
        const res = await fetch(`${API_BASE}/projects/${projectId}/episodes/${episodeId}/traces`);
        return res.json();
    },

    // ========== Linear Production Pipeline ==========

    async startProjectProduction(projectId) {
        const res = await fetch(`${API_BASE}/projects/${projectId}/start-production`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        return res.json();
    },

    async getProjectStages(projectId) {
        const res = await fetch(`${API_BASE}/projects/${projectId}/stages`);
        return res.json();
    },

    async getProjectTimeline(projectId) {
        const res = await fetch(`${API_BASE}/projects/${projectId}/timeline`);
        return res.json();
    },

    async getAgentEvents(projectId, agentId) {
        const res = await fetch(`${API_BASE}/projects/${projectId}/agents/${agentId}/events`);
        return res.json();
    }
};

// ========== Mock API 实现 ==========

const MockApi = {
    _conversationId: null,
    _phase: -1,
    _collectedInfo: {},
    _selectedGenre: null,
    _projects: {},
    _projectIdCounter: 0,

    createConversation(initialIdea) {
        this._conversationId = 'conv_' + Date.now();
        this._phase = 0;
        this._collectedInfo = { initial_idea: initialIdea };
        this._selectedGenre = null;

        // 自动检测类型
        for (const genre of Object.keys(MOCK.scriptTemplates)) {
            if (initialIdea.includes(genre)) {
                this._selectedGenre = genre;
                break;
            }
        }

        const phase = MOCK.conversationPhases[0];
        return {
            conversation_id: this._conversationId,
            message: {
                role: "assistant",
                content: phase.assistantMsg,
                questions: phase.questions
            },
            state: "collecting_requirements"
        };
    },

    sendMessage(conversationId, message) {
        this._phase++;

        // 提取信息
        if (this._phase === 1) {
            for (const genre of Object.keys(MOCK.scriptTemplates)) {
                if (message.includes(genre)) {
                    this._selectedGenre = genre;
                    this._collectedInfo.genre = genre;
                    break;
                }
            }
            if (!this._collectedInfo.genre) {
                this._collectedInfo.genre = this._selectedGenre || "都市爱情";
            }
        } else if (this._phase === 2) {
            const nums = message.match(/\d+/g);
            if (nums) this._collectedInfo.episode_count = parseInt(nums[0]);
            else this._collectedInfo.episode_count = 20;
        } else if (this._phase === 3) {
            this._collectedInfo.story_background = message;
            this._collectedInfo.style_tone = message;
        }

        // 还有更多问题
        if (this._phase < MOCK.conversationPhases.length) {
            const phase = MOCK.conversationPhases[this._phase];
            return {
                conversation_id: conversationId,
                message: {
                    role: "assistant",
                    content: phase.assistantMsg,
                    questions: phase.questions
                },
                state: "collecting_requirements"
            };
        }

        // 生成剧本大纲
        const genre = this._collectedInfo.genre || "都市爱情";
        const template = MOCK.scriptTemplates[genre] || MOCK.scriptTemplates["都市爱情"];
        this._currentTemplate = template;

        const charsText = template.characters.map(c =>
            `- ${c.name}：${c.age}岁，${c.role}，${c.description}`
        ).join('\n');
        const epsText = template.episodes_summary.map(e =>
            `- 第${e.range}集：${e.theme}`
        ).join('\n');

        const content = `根据您的需求，我已生成以下剧本大纲：\n\n## 《${template.title}》\n\n**故事梗概**：${template.synopsis}\n\n**主要角色**：\n${charsText}\n\n**分集概要**：\n${epsText}\n\n请确认这个剧本大纲，确认后将进入全自动制片流程。`;

        return {
            conversation_id: conversationId,
            message: {
                role: "assistant",
                content
            },
            state: "awaiting_final_confirmation",
            script_outline: {
                title: template.title,
                synopsis: template.synopsis,
                characters: template.characters,
                episodes_summary: template.episodes_summary
            }
        };
    },

    confirmOutline(conversationId) {
        const template = this._currentTemplate || MOCK.scriptTemplates["都市爱情"];
        return {
            conversation_id: conversationId,
            project_id: "proj_" + (++this._projectIdCounter),
            message: {
                role: "assistant",
                content: `剧本大纲已确认！《${template.title}》的制片项目即将启动。\n\n确认后将进入全自动制片流程，包括：\n- 角色三视图自动生成\n- 分集剧本编写\n- 分镜设计与视频生成\n- 自动剪辑与合成\n\n请点击"启动制片"按钮开始。`
            },
            script_outline: {
                title: template.title,
                synopsis: template.synopsis,
                characters: template.characters,
                episodes_summary: template.episodes_summary
            },
            state: "confirmed"
        };
    },

    startProduction(conversationId) {
        const template = this._currentTemplate || MOCK.scriptTemplates["都市爱情"];
        const projectId = "proj_" + this._projectIdCounter;
        const episodeCount = this._collectedInfo.episode_count || 20;

        // 创建项目数据
        this._projects[projectId] = this._createProjectData(projectId, template, episodeCount);

        return {
            project_id: projectId,
            status: "production_started",
            message: "制片工作流已启动！您可以在项目面板中查看实时进度。",
            estimated_completion_time: new Date(Date.now() + 3600000).toISOString()
        };
    },

    getProjects() {
        const projects = Object.values(this._projects).map(p => ({
            project_id: p.project_id,
            title: p.title,
            status: p.status,
            progress: p.progress,
            created_at: p.created_at,
            episode_count: p.episodes.length,
            completed_episodes: p.episodes.filter(e => e.status === "completed").length
        }));
        return { projects, total: projects.length };
    },

    getProject(projectId) {
        return this._projects[projectId] || null;
    },

    getAgents(projectId) {
        const statuses = ["working", "working", "idle", "working", "working"];
        const tasks = [
            "监控全局进度",
            "编写第8集剧本",
            null,
            "优化第6集镜头提示词",
            "剪辑第5集"
        ];

        return {
            agents: MOCK.agents.map((a, i) => ({
                ...a,
                status: statuses[i],
                current_task: tasks[i],
                completed_tasks: Math.floor(Math.random() * a.tasks_total * 0.6),
                total_tasks: a.tasks_total
            }))
        };
    },

    getAgentLogs(projectId, agentId) {
        return {
            agent_id: agentId,
            logs: (MOCK.agentLogs[agentId] || []).map((log, i) => ({
                timestamp: new Date(Date.now() - (i + 1) * 30000).toISOString(),
                level: log.level,
                message: log.message
            }))
        };
    },

    _createProjectData(projectId, template, episodeCount) {
        const episodeStatuses = [
            "completed", "completed", "editing", "rendering", "asset_generating",
            "storyboarding", "scripting", "pending", "pending", "pending"
        ];
        const progressMap = {
            completed: 100, editing: 75, rendering: 55,
            asset_generating: 35, storyboarding: 20, scripting: 10, pending: 0
        };

        const episodes = [];
        for (let i = 0; i < episodeCount; i++) {
            const status = episodeStatuses[i] || "pending";
            episodes.push({
                episode_id: `ep_${String(i + 1).padStart(3, '0')}`,
                episode_number: i + 1,
                title: i < MOCK.episodeTitles.length ? MOCK.episodeTitles[i] : `第${i + 1}集`,
                status,
                progress: progressMap[status] || 0,
                duration: status === "completed" ? "4:32" : null,
                video_url: status === "completed" ? `/videos/ep_${String(i + 1).padStart(3, '0')}.mp4` : null
            });
        }

        const completed = episodes.filter(e => e.status === "completed").length;
        const overallProgress = Math.round((completed / episodeCount) * 100);

        return {
            project_id: projectId,
            title: template.title,
            status: "in_progress",
            progress: overallProgress,
            created_at: new Date().toISOString(),
            config: {
                episode_count: episodeCount,
                episode_duration: "3-5分钟",
                genre: this._collectedInfo.genre || "都市爱情",
                style: "轻松幽默"
            },
            characters: template.characters.map((c, i) => ({
                character_id: `char_${String(i + 1).padStart(3, '0')}`,
                name: c.name,
                age: c.age,
                role: c.role,
                description: c.description
            })),
            episodes
        };
    }
};
