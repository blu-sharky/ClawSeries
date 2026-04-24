/**
 * 聊天模块 - 处理对话流程，支持五大 Agent 身份
 */

// Agent identity map matching README five agents
const AGENT_IDENTITIES = {
    agent_director: { icon: 'assignment', name: '\u9879\u76EE\u603B\u76D1', color: '#6c5ce7' },
    agent_chief_director: { icon: 'movie_creation', name: '\u603B\u5BFC\u6F14', color: '#e17055' },
    agent_prompt: { icon: 'edit_note', name: '\u63D0\u793A\u8BCD\u67B6\u6784\u5E08', color: '#fdcb6e' },
    agent_visual: { icon: 'palette', name: '\u89C6\u89C9\u603B\u76D1', color: '#00b894' },
    agent_editor: { icon: 'video_library', name: '\u81EA\u52A8\u5316\u526A\u8F91\u5E08', color: '#74b9ff' },
};

const Chat = {
    conversationId: null,
    state: null,
    messages: [],
    isTyping: false,

    init() {
        const input = document.getElementById('chat-input');
        input.addEventListener('input', () => this._autoResize(input));
        this._setMainInputVisible(true);
    },

    _autoResize(el) {
        el.style.height = 'auto';
        el.style.height = Math.min(el.scrollHeight, 120) + 'px';
    },

    _setMainInputVisible(visible) {
        const inputArea = document.querySelector('.chat-input-area');
        if (!inputArea) return;
        inputArea.classList.toggle('hidden', !visible);
    },

    _hasOptionQuestions(questions = []) {
        return questions.some(q => q.type === 'select' || q.type === 'multiselect');
    },

    _getAgentInfo(agentId) {
        if (!agentId) return { icon: 'assignment', name: '\u9879\u76EE\u603B\u76D1', color: '#6c5ce7' };
        return AGENT_IDENTITIES[agentId] || { icon: 'smart_toy', name: 'Agent', color: '#6b7280' };
    },

    _renderAvatar(agentId) {
        const agent = this._getAgentInfo(agentId);
        return `<div class="message-avatar material-symbols-outlined" style="background: ${agent.color}" title="${agent.name}">${agent.icon}</div>`;
    },

    async sendQuickStart(text) {
        document.getElementById('chat-input').value = text;
        await this.sendMessage();
    },

    async sendMessage() {
        const input = document.getElementById('chat-input');
        const text = input.value.trim();
        if (!text || this.isTyping) return;

        input.value = '';
        input.style.height = 'auto';

        await this._submitUserReply(text);
    },

    async submitQuestions(button) {
        if (this.isTyping) return;

        const messageEl = button.closest('.message.assistant');
        const text = this._collectQuestionAnswers(messageEl);
        if (!text) return;

        await this._submitUserReply(text);
    },

    async _submitUserReply(text) {
        const welcome = document.querySelector('.chat-welcome');
        if (welcome) welcome.style.display = 'none';

        this._addMessage('user', text);
        this.isTyping = true;
        this._showTyping();

        try {
            if (!this.conversationId) {
                this._streamAssistantResponse((onChunk, onDone, onError) =>
                    Api.streamCreateConversation(text, onChunk, onDone, onError)
                );
            } else {
                this._streamAssistantResponse((onChunk, onDone, onError) =>
                    Api.streamMessage(this.conversationId, text, onChunk, onDone, onError)
                );
            }
        } catch (err) {
            this._hideTyping();
            this._addMessage('assistant', '抱歉，出了点问题，请重试。');
            this._setMainInputVisible(true);
            this.isTyping = false;
        }
    },

    _streamAssistantResponse(startStream) {
        let fullContent = '';
        let streamingDiv = null;
        let contentEl = null;
        let thinkingEl = null;
        const latest = {
            conversationId: null,
            state: null,
            message: null,
            questions: null,
            agentId: null
        };

        const startStreamingUI = (agentId) => {
            this._hideTyping();
            const resolvedAgentId = agentId || 'agent_director';
            const agent = this._getAgentInfo(resolvedAgentId);
            streamingDiv = document.createElement('div');
            streamingDiv.className = 'message assistant';
            streamingDiv.innerHTML = `
                ${this._renderAvatar(resolvedAgentId)}
                <div class="message-body">
                    <div class="agent-label" style="color: ${agent.color}; font-size: 12px; font-weight: 600; margin-bottom: 4px;">${agent.name}</div>
                    ${this._renderThinkingPanel(resolvedAgentId)}
                    <div class="message-content streaming" style="display: none;"><span class="streaming-cursor"></span></div>
                </div>
            `;
            const container = document.getElementById('chat-messages');
            container.appendChild(streamingDiv);
            thinkingEl = streamingDiv.querySelector('.thinking-panel');
            contentEl = streamingDiv.querySelector('.message-content');
            container.scrollTop = container.scrollHeight;
        };

        const mergeMeta = (data) => {
            if (data.conversation_id) {
                latest.conversationId = data.conversation_id;
                this.conversationId = data.conversation_id;
            }
            if (data.state) latest.state = data.state;
            if (data.message) latest.message = data.message;
            if (data.questions) latest.questions = data.questions;
            if (data.agent_id) latest.agentId = data.agent_id;
            if (data.message?.agent_id) latest.agentId = data.message.agent_id;
        };

        startStream(
            (data) => {
                mergeMeta(data);

                // Handle loading indicator
                if (data.loading) {
                    if (!streamingDiv) startStreamingUI(data.agent_id || 'agent_director');
                    return;
                }

                if (!data.content) return;

                // Type only the user-facing opening line, never raw JSON fragments.
                if (!streamingDiv) startStreamingUI(data.agent_id || data.message?.agent_id);
                fullContent += data.content;
                if (contentEl) {
                    const visibleText = this._extractStreamingOpeningRemark(fullContent);
                    if (visibleText && thinkingEl) {
                        thinkingEl.remove();
                        thinkingEl = null;
                        contentEl.style.display = 'block';
                    }
                    if (visibleText) {
                        contentEl.innerHTML = `${this._formatContent(visibleText)}<span class="streaming-cursor"></span>`;
                    }
                    const container = document.getElementById('chat-messages');
                    container.scrollTop = container.scrollHeight;
                }
            },
            (data) => {
                mergeMeta(data);

                const finalState = latest.state || this.state;
                if (finalState) this.state = finalState;

                const finalMessage = latest.message || {
                    content: fullContent,
                    questions: latest.questions || [],
                    agent_id: latest.agentId || 'agent_director'
                };
                if (!finalMessage.content && fullContent) {
                    finalMessage.content = this._extractStreamingOpeningRemark(fullContent);
                }

                if (streamingDiv) {
                    streamingDiv.remove();
                }

                this._addAssistantMessage(finalMessage, finalState);
                this.isTyping = false;
            },
            (error) => {
                if (streamingDiv) streamingDiv.remove();
                this._addMessage('assistant', '抱歉，出了点问题，请重试。');
                this._setMainInputVisible(true);
                this.isTyping = false;
            }
        );
    },

    _addMessage(role, content, agentId) {
        const container = document.getElementById('chat-messages');
        const div = document.createElement('div');
        div.className = `message ${role}`;

        if (role === 'user') {
            div.innerHTML = `
                <div class="message-avatar user-avatar">\u4F60</div>
                <div class="message-body">
                    <div class="message-content">${this._formatContent(content)}</div>
                </div>
            `;
        } else {
            div.innerHTML = `
                ${this._renderAvatar(agentId)}
                <div class="message-body">
                    <div class="message-content">${this._formatContent(content)}</div>
                </div>
            `;
        }

        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
        this.messages.push({ role, content });
    },

    _addAssistantMessage(message, state) {
        const container = document.getElementById('chat-messages');
        const div = document.createElement('div');
        div.className = 'message assistant';

        const agentId = message.agent_id || 'agent_director';
        const agent = this._getAgentInfo(agentId);

        let extra = '';
        if (message.questions?.length) {
            extra = this._renderQuestions(message.questions);
        }

        // Show skip-to-outline button during question rounds
        if (state === 'collecting_requirements') {
            extra += `
                <div class="action-bar">
                    <button class="btn-skip" onclick="Chat.skipToOutline()">跳过追问，直接生成大纲</button>
                </div>`;
        }

        if (state === 'ready_for_outline') {
            extra = `
                <div class="action-bar">
                    <button class="btn-primary" onclick="Chat.generateOutline()">生成大纲</button>
                </div>`;
        }

        if (state === 'awaiting_final_confirmation') {
            extra = `
                <div class="action-bar">
                    <button class="btn-primary" onclick="Chat.confirmOutline()">确认大纲</button>
                    <button class="btn-secondary" onclick="Chat.requestRevision()">修改要求</button>
                </div>`;
        }

        if (state === 'confirmed') {
            extra = `
                <div class="action-bar">
                    <button class="btn-start-production" onclick="Chat.startProduction()">启动制片</button>
                </div>`;
        }

        div.innerHTML = `
            ${this._renderAvatar(agentId)}
            <div class="message-body">
                <div class="agent-label" style="color: ${agent.color}; font-size: 12px; font-weight: 600; margin-bottom: 4px;">${agent.name}</div>
                <div class="message-content">${this._formatContent(message.content)}</div>
                ${extra}
            </div>
        `;

        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
        this._setMainInputVisible(!this._hasOptionQuestions(message.questions || []));
    },

    _renderQuestions(questions) {
        let html = '<div class="message-questions">';

        for (const q of questions) {
            html += `<div class="question-group" data-qid="${this._escapeAttr(q.id)}" data-qtype="${this._escapeAttr(q.type)}">`;
            html += `<div class="question-label">${q.question}</div>`;

            if (q.type === 'select' || q.type === 'multiselect') {
                html += '<div class="question-options">';
                for (const opt of q.options || []) {
                    html += `
                        <button
                            type="button"
                            class="option-btn"
                            data-value="${this._escapeAttr(opt)}"
                            onclick="Chat.selectOption(this)"
                        >${opt}</button>`;
                }
                html += '</div>';
                html += '<input class="question-text-input" type="text" placeholder="其他答案（可选）" data-role="other">';
            } else {
                html += `
                    <input
                        class="question-text-input"
                        type="text"
                        placeholder="${this._escapeAttr(q.placeholder || '')}"
                        data-role="primary"
                    >`;
            }

            html += '</div>';
        }

        html += `
            <div class="action-bar">
                <button type="button" class="btn-primary" onclick="Chat.submitQuestions(this)">提交回答</button>
            </div>`;
        html += '</div>';
        return html;
    },

    _escapeAttr(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    },

    selectOption(btn) {
        const group = btn.closest('.question-group');
        const type = group?.dataset.qtype;
        if (!group) return;

        if (type === 'multiselect') {
            btn.classList.toggle('selected');
            return;
        }

        const siblings = group.querySelectorAll('.option-btn');
        const wasSelected = btn.classList.contains('selected');
        siblings.forEach(s => s.classList.remove('selected'));
        if (!wasSelected) {
            btn.classList.add('selected');
        }
    },

    _collectQuestionAnswers(messageEl) {
        if (!messageEl) return '';

        const groups = messageEl.querySelectorAll('.question-group');
        const answers = [];

        for (const group of groups) {
            const label = group.querySelector('.question-label')?.textContent?.trim() || group.dataset.qid;
            const type = group.dataset.qtype;
            const selected = [...group.querySelectorAll('.option-btn.selected')].map(btn => btn.dataset.value?.trim()).filter(Boolean);
            const primaryInput = group.querySelector('[data-role="primary"]');
            const otherInput = group.querySelector('[data-role="other"]');
            const primaryValue = primaryInput?.value?.trim() || '';
            const otherValue = otherInput?.value?.trim() || '';

            let value = '';
            if (type === 'text') {
                value = primaryValue;
            } else {
                const parts = [...selected];
                if (otherValue) parts.push(`其他：${otherValue}`);
                value = parts.join('、');
            }

            if (value) {
                answers.push(`${label}：${value}`);
            }
        }

        return answers.join('\n');
    },

    async confirmOutline() {
        if (!this.conversationId) return;

        this._addMessage('user', '确认大纲');
        this.isTyping = true;
        this._showTyping();

        try {
            const response = await Api.confirmOutline(this.conversationId);
            this.state = response.state;
            this._hideTyping();
            this._addAssistantMessage(response.message, response.state);
        } catch (err) {
            this._hideTyping();
            this._addMessage('assistant', '确认失败，请重试。');
            this._setMainInputVisible(true);
        }

        this.isTyping = false;
    },

    async startProduction() {
        if (!this.conversationId) return;

        this._addMessage('user', '启动制片');
        this.isTyping = true;
        this._showTyping();

        try {
            const response = await Api.startProduction(this.conversationId);
            this._hideTyping();
            this._addMessage('assistant', response.message);

            setTimeout(() => {
                ProjectView.show(response.project_id);
                App.refreshProjectList();
            }, 1500);
        } catch (err) {
            this._hideTyping();
            this._addMessage('assistant', '启动失败，请重试。');
            this._setMainInputVisible(true);
        }

        this.isTyping = false;
    },

    skipToOutline() {
        // User skips remaining questions, go directly to outline
        this.generateOutline();
    },

    async generateOutline() {
        if (!this.conversationId) return;

        this._addMessage('user', '直接生成大纲');
        this.isTyping = true;
        this._setMainInputVisible(false);
        this._showTyping('agent_chief_director');

        this._streamOutlineResponse((onChunk, onDone, onError) =>
            Api.generateOutline(this.conversationId, onChunk, onDone, onError)
        );
    },

    _streamOutlineResponse(startStream) {
        let fullContent = '';
        let streamingDiv = null;
        let contentEl = null;
        let thinkingEl = null;

        const startStreamingUI = () => {
            this._hideTyping();
            const agentId = 'agent_chief_director';
            const agent = this._getAgentInfo(agentId);
            streamingDiv = document.createElement('div');
            streamingDiv.className = 'message assistant';
            streamingDiv.innerHTML = `
                ${this._renderAvatar(agentId)}
                <div class="message-body">
                    <div class="agent-label" style="color: ${agent.color}; font-size: 12px; font-weight: 600; margin-bottom: 4px;">${agent.name}</div>
                    ${this._renderThinkingPanel(agentId)}
                    <div class="message-content streaming" style="display: none;"><span class="streaming-cursor"></span></div>
                </div>
            `;
            const container = document.getElementById('chat-messages');
            container.appendChild(streamingDiv);
            thinkingEl = streamingDiv.querySelector('.thinking-panel');
            contentEl = streamingDiv.querySelector('.message-content');
            container.scrollTop = container.scrollHeight;
        };

        startStream(
            (data) => {
                if (!data.content) return;
                if (!streamingDiv) startStreamingUI();
                fullContent += data.content;
                if (contentEl) {
                    if (thinkingEl) {
                        thinkingEl.remove();
                        thinkingEl = null;
                        contentEl.style.display = 'block';
                    }
                    contentEl.innerHTML = this._formatContent(fullContent) + '<span class="streaming-cursor"></span>';
                    const container = document.getElementById('chat-messages');
                    container.scrollTop = container.scrollHeight;
                }
            },
            (data) => {
                this.state = data.state || this.state;

                if (streamingDiv) streamingDiv.remove();

                const msg = data.message || { content: fullContent, agent_id: 'agent_chief_director' };
                this._addAssistantMessage(msg, this.state);
                this.isTyping = false;
            },
            (error) => {
                if (streamingDiv) streamingDiv.remove();
                this._addMessage('assistant', '大纲生成失败，请重试。');
                this._setMainInputVisible(true);
                this.isTyping = false;
            }
        );
    },

    requestRevision() {
        const input = document.getElementById('chat-input');
        input.value = '';
        input.placeholder = '请告诉我您想修改的内容...';
        this._setMainInputVisible(true);
        input.focus();
    },

    _showTyping(agentId = 'agent_director') {
        const container = document.getElementById('chat-messages');
        const div = document.createElement('div');
        const agent = this._getAgentInfo(agentId);
        div.className = 'message assistant';
        div.id = 'typing-indicator';
        div.innerHTML = `
            ${this._renderAvatar(agentId)}
            <div class="message-body">
                <div class="agent-label" style="color: ${agent.color}; font-size: 12px; font-weight: 600; margin-bottom: 4px;">${agent.name}</div>
                ${this._renderThinkingPanel(agentId)}
            </div>
        `;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    },

    _thinkingTextForAgent(agentId) {
        if (agentId === 'agent_chief_director') {
            return '正在梳理故事骨架、节奏和分集结构';
        }
        return '正在分析题材、冲突、人物关系和爆点';
    },

    _renderThinkingPanel(agentId) {
        const thinkingText = this._thinkingTextForAgent(agentId);
        return `
            <div class="thinking-panel">
                <div class="thinking-label">Thinking</div>
                <div class="thinking-text">${thinkingText}<span class="streaming-cursor"></span></div>
            </div>
        `;
    },

    _hideTyping() {
        const el = document.getElementById('typing-indicator');
        if (el) el.remove();
    },

    _extractStreamingOpeningRemark(raw) {
        const openingMatch = raw.match(/"开场白"\s*:\s*"/);
        if (!openingMatch) {
            const trimmed = raw.trimStart();
            const looksStructured = trimmed.startsWith('{') || trimmed.startsWith('<response>') || trimmed.startsWith('```');
            return looksStructured ? '' : raw;
        }

        const start = openingMatch.index + openingMatch[0].length;
        let fragment = '';
        let isEscaped = false;

        for (let i = start; i < raw.length; i += 1) {
            const ch = raw[i];
            if (isEscaped) {
                fragment += `\\${ch}`;
                isEscaped = false;
                continue;
            }
            if (ch === '\\') {
                isEscaped = true;
                continue;
            }
            if (ch === '"') break;
            fragment += ch;
        }

        return this._decodeJsonStringFragment(fragment);
    },

    _decodeJsonStringFragment(fragment) {
        return fragment
            .replace(/\\u([0-9a-fA-F]{4})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)))
            .replace(/\\n/g, '\n')
            .replace(/\\r/g, '')
            .replace(/\\t/g, '\t')
            .replace(/\\"/g, '"')
            .replace(/\\\\/g, '\\');
    },

    _formatContent(text) {
        return text
            .replace(/## (.+)/g, '<h2>$1</h2>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/^- (.+)$/gm, '<li>$1</li>')
            .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
            .replace(/\n/g, '<br>');
    },

    reset() {
        this.conversationId = null;
        this.state = null;
        this.messages = [];
        this.isTyping = false;

        const input = document.getElementById('chat-input');
        input.value = '';
        input.placeholder = '描述您想制作的短剧...';
        input.style.height = 'auto';
        this._setMainInputVisible(true);

        const container = document.getElementById('chat-messages');
        container.innerHTML = `
            <div class="chat-welcome">
                <div class="welcome-icon">CS</div>
                <h2>欢迎使用 ClawSeries</h2>
                <p>描述您想制作的短剧，AI 将引导您完成从剧本到成片的全流程。</p>
                <div class="quick-starters">
                    <button class="quick-btn" onclick="Chat.sendQuickStart('我想做一部都市爱情短剧，重点是极限拉扯和身份反转')">都市爱情短剧</button>
                    <button class="quick-btn" onclick="Chat.sendQuickStart('做一个悬疑推理系列，类似隐秘的角落那种风格')">悬疑推理系列</button>
                    <button class="quick-btn" onclick="Chat.sendQuickStart('古风仙侠短剧，要有修炼升级和爱情线')">古风仙侠</button>
                    <button class="quick-btn" onclick="Chat.sendQuickStart('职场商战题材，讲一个年轻人逆袭的故事')">职场逆袭</button>
                </div>
            </div>`;
    }
};

// 全局快捷方法
function sendQuickStart(text) { Chat.sendQuickStart(text); }
function sendMessage() { Chat.sendMessage(); }

function handleInputKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}
