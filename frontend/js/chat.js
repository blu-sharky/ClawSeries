/**
 * 聊天模块 - 处理对话流程，支持五大 Agent 身份
 */

const AGENT_IDENTITIES = {
    agent_director: { icon: 'assignment', getName: () => I18n.t('agent.director'), color: '#6c5ce7' },
    agent_chief_director: { icon: 'movie_creation', getName: () => I18n.t('agent.chief_director'), color: '#e17055' },
    agent_prompt: { icon: 'edit_note', getName: () => I18n.t('agent.prompt'), color: '#fdcb6e' },
    agent_visual: { icon: 'palette', getName: () => I18n.t('agent.visual'), color: '#00b894' },
    agent_editor: { icon: 'video_library', getName: () => I18n.t('agent.editor'), color: '#74b9ff' },
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
        if (!agentId) return { icon: 'assignment', getName: () => I18n.t('agent.director'), color: '#6c5ce7' };
        return AGENT_IDENTITIES[agentId] || { icon: 'smart_toy', getName: () => 'Agent', color: '#6b7280' };
    },

    _renderAvatar(agentId) {
        const agent = this._getAgentInfo(agentId);
        const name = agent.getName();
        return `<div class="message-avatar material-symbols-outlined" style="background: ${agent.color}" title="${name}">${agent.icon}</div>`;
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
            this._addMessage('assistant', I18n.t('chat.errorRetry'));
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
            const name = agent.getName();
            streamingDiv = document.createElement('div');
            streamingDiv.className = 'message assistant';
            streamingDiv.innerHTML = `
                ${this._renderAvatar(resolvedAgentId)}
                <div class="message-body">
                    <div class="agent-label" style="color: ${agent.color}; font-size: 12px; font-weight: 600; margin-bottom: 4px;">${name}</div>
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

                if (data.loading) {
                    if (!streamingDiv) startStreamingUI(data.agent_id || 'agent_director');
                    return;
                }

                if (!data.content) return;

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
                this._addMessage('assistant', I18n.t('chat.errorRetry'));
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
                <div class="message-avatar user-avatar">${I18n.t('chat.userLabel')}</div>
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
        const name = agent.getName();

        let extra = '';
        if (message.questions?.length) {
            extra = this._renderQuestions(message.questions);
        }

        if (state === 'collecting_requirements') {
            extra += `
                <div class="action-bar">
                    <button class="btn-skip" onclick="Chat.skipToOutline()">${I18n.t('chat.skipToOutline')}</button>
                </div>`;
        }

        if (state === 'ready_for_outline') {
            extra = `
                <div class="action-bar">
                    <button class="btn-primary" onclick="Chat.generateOutline()">${I18n.t('chat.generateOutline')}</button>
                </div>`;
        }

        if (state === 'awaiting_final_confirmation') {
            extra = `
                <div class="action-bar">
                    <button class="btn-primary" onclick="Chat.confirmOutline()">${I18n.t('chat.confirmOutline')}</button>
                    <button class="btn-secondary" onclick="Chat.requestRevision()">${I18n.t('chat.revise')}</button>
                </div>`;
        }

        if (state === 'confirmed') {
            extra = `
                <div class="action-bar">
                    <button class="btn-start-production" onclick="Chat.startProduction()">${I18n.t('chat.startProduction')}</button>
                </div>`;
        }

        div.innerHTML = `
            ${this._renderAvatar(agentId)}
            <div class="message-body">
                <div class="agent-label" style="color: ${agent.color}; font-size: 12px; font-weight: 600; margin-bottom: 4px;">${name}</div>
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
                html += `<input class="question-text-input" type="text" placeholder="${I18n.t('chat.otherAnswer')}" data-role="other">`;
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
                <button type="button" class="btn-primary" onclick="Chat.submitQuestions(this)">${I18n.t('chat.submitAnswers')}</button>
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
                if (otherValue) parts.push(I18n.t('chat.otherPrefix') + otherValue);
                value = parts.join(I18n.t('chat.answerSeparator'));
            }

            if (value) {
                answers.push(I18n.t('chat.answerFormat', { label, value }));
            }
        }

        return answers.join('\n');
    },

    async confirmOutline() {
        if (!this.conversationId) return;

        this._addMessage('user', I18n.t('chat.confirmOutlineMsg'));
        this.isTyping = true;
        this._showTyping();

        try {
            const response = await Api.confirmOutline(this.conversationId);
            this.state = response.state;
            this._hideTyping();
            this._addAssistantMessage(response.message, response.state);
        } catch (err) {
            this._hideTyping();
            this._addMessage('assistant', I18n.t('chat.confirmFailed'));
            this._setMainInputVisible(true);
        }

        this.isTyping = false;
    },

    async startProduction() {
        if (!this.conversationId) return;

        this._addMessage('user', I18n.t('chat.startProductionMsg'));
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
            this._addMessage('assistant', I18n.t('chat.startFailed'));
            this._setMainInputVisible(true);
        }

        this.isTyping = false;
    },

    skipToOutline() {
        this.generateOutline();
    },

    async generateOutline() {
        if (!this.conversationId) return;

        this._addMessage('user', I18n.t('chat.generateOutlineMsg'));
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
            const name = agent.getName();
            streamingDiv = document.createElement('div');
            streamingDiv.className = 'message assistant';
            streamingDiv.innerHTML = `
                ${this._renderAvatar(agentId)}
                <div class="message-body">
                    <div class="agent-label" style="color: ${agent.color}; font-size: 12px; font-weight: 600; margin-bottom: 4px;">${name}</div>
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
                this._addMessage('assistant', I18n.t('chat.outlineFailed'));
                this._setMainInputVisible(true);
                this.isTyping = false;
            }
        );
    },

    requestRevision() {
        const input = document.getElementById('chat-input');
        input.value = '';
        input.placeholder = I18n.t('chat.revisionPlaceholder');
        this._setMainInputVisible(true);
        input.focus();
    },

    _showTyping(agentId = 'agent_director') {
        const container = document.getElementById('chat-messages');
        const div = document.createElement('div');
        const agent = this._getAgentInfo(agentId);
        const name = agent.getName();
        div.className = 'message assistant';
        div.id = 'typing-indicator';
        div.innerHTML = `
            ${this._renderAvatar(agentId)}
            <div class="message-body">
                <div class="agent-label" style="color: ${agent.color}; font-size: 12px; font-weight: 600; margin-bottom: 4px;">${name}</div>
                ${this._renderThinkingPanel(agentId)}
            </div>
        `;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    },

    _thinkingTextForAgent(agentId) {
        if (agentId === 'agent_chief_director') {
            return I18n.t('chat.thinking.chief_director');
        }
        return I18n.t('chat.thinking.director');
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
        input.placeholder = I18n.t('chat.placeholder');
        input.style.height = 'auto';
        this._setMainInputVisible(true);

        const container = document.getElementById('chat-messages');
        container.innerHTML = `
            <div class="chat-welcome">
                <div class="welcome-icon">CS</div>
                <h2>${I18n.t('welcome.title')}</h2>
                <p>${I18n.t('welcome.desc')}</p>
                <div class="quick-starters">
                    <button class="quick-btn" onclick="Chat.sendQuickStart('我想做一部都市爱情短剧，重点是极限拉扯和身份反转')">${I18n.t('welcome.quick1')}</button>
                    <button class="quick-btn" onclick="Chat.sendQuickStart('做一个悬疑推理系列，类似隐秘的角落那种风格')">${I18n.t('welcome.quick2')}</button>
                    <button class="quick-btn" onclick="Chat.sendQuickStart('古风仙侠短剧，要有修炼升级和爱情线')">${I18n.t('welcome.quick3')}</button>
                    <button class="quick-btn" onclick="Chat.sendQuickStart('职场商战题材，讲一个年轻人逆袭的故事')">${I18n.t('welcome.quick4')}</button>
                </div>
            </div>`;
    }
};

function sendQuickStart(text) { Chat.sendQuickStart(text); }
function sendMessage() { Chat.sendMessage(); }

function handleInputKeydown(e) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        sendMessage();
    }
}
