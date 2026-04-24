/**
 * Settings module - model configuration UI
 */

const Settings = {
    currentConfig: null,

    async init() {
        await this.loadSettings();
        this.bindEvents();
    },

    async loadSettings() {
        try {
            const res = await fetch('http://localhost:8000/api/v1/settings/models');
            this.currentConfig = await res.json();
            this.render();
        } catch (err) {
            console.error('Failed to load settings:', err);
            this.showError('无法加载设置，请确保后端服务正在运行');
        }
    },

    render() {
        const container = document.getElementById('settings-content');
        if (!container) return;

        const llm = this.currentConfig?.llm || {};
        const image = this.currentConfig?.image || {};
        const video = this.currentConfig?.video || {};
        const google = this.currentConfig?.google || {};
        const mode = this.currentConfig?.video_generation_mode || 'manual';

        container.innerHTML = `
            <div class="settings-columns">
                ${this._renderLLMSection(llm)}
                ${this._renderImageSection(image)}
                ${this._renderVideoSection(video, mode)}
            </div>
            <div id="google-config-section" style="display: none; max-width: 1400px; margin: 0 auto;">
                ${this._renderGoogleSection(google)}
            </div>
            <div class="settings-bottom-bar">
                <button class="btn-primary" onclick="Settings.saveSettings()">保存设置</button>
                <span id="settings-status" class="status-message"></span>
            </div>
        `;

        this.updateProviderUI();
    },

    _renderLLMSection(llm) {
        const isGoogle = llm.provider === 'google_genai';
        return `
            <div class="settings-section">
                <div class="settings-section-header">
                    <div class="settings-section-icon material-symbols-outlined" style="background: rgba(108, 92, 231, 0.15); color: #6c5ce7;">smart_toy</div>
                    <div>
                        <h3>LLM 模型</h3>
                        <p class="settings-desc">剧本生成、分镜设计等文本任务</p>
                    </div>
                </div>

                <div class="form-group">
                    <label>Provider</label>
                    <select id="llm-provider">
                        <option value="openai" ${llm.provider === 'openai' ? 'selected' : ''}>OpenAI</option>
                        <option value="google_genai" ${llm.provider === 'google_genai' ? 'selected' : ''}>Google Gen AI</option>
                        <option value="azure" ${llm.provider === 'azure' ? 'selected' : ''}>Azure OpenAI</option>
                        <option value="anthropic" ${llm.provider === 'anthropic' ? 'selected' : ''}>Anthropic</option>
                        <option value="custom" ${llm.provider === 'custom' ? 'selected' : ''}>自定义</option>
                    </select>
                </div>

                <div class="form-group" id="llm-base-url-group">
                    <label>Base URL</label>
                    <input type="text" id="llm-base-url" value="${llm.base_url || ''}"
                           placeholder="https://api.openai.com/v1">
                </div>

                <div class="form-group" id="llm-api-key-group">
                    <label>API Key</label>
                    <div class="input-with-button">
                        <input type="password" id="llm-api-key"
                               placeholder="${llm.has_api_key ? '已配置' : '输入 API Key'}">
                        <button class="btn-secondary btn-sm" onclick="Settings.testConnection('llm')">测试</button>
                    </div>
                </div>

                <div class="form-group">
                    <label>Model</label>
                    <input type="text" id="llm-model" value="${llm.model || 'gpt-4o'}"
                           placeholder="gpt-4o">
                    <p class="form-hint">Google: gemini-2.5-flash, gemini-2.5-pro</p>
                </div>

                <div class="form-group" id="llm-google-test-row" style="display: ${isGoogle ? 'block' : 'none'};">
                    <label>Google Gen AI 连接</label>
                    <div class="settings-inline-actions">
                        <button class="btn-secondary btn-sm" onclick="Settings.testConnection('llm')">测试 Google Gen AI</button>
                    </div>
                    <p class="form-hint">使用当前 Project / Location 与 ADC 凭证测试 Vertex AI 连接。</p>
                </div>
            </div>
        `;
    },

    _renderImageSection(image) {
        const isGoogle = image.provider === 'google_genai';
        const isSiliconFlow = image.provider === 'siliconflow';
        const showAdvanced = isSiliconFlow;
        const imageDemoMode = this.currentConfig?.image_demo_mode || false;
        return `
            <div class="settings-section">
                <div class="settings-section-header">
                    <div class="settings-section-icon material-symbols-outlined" style="background: rgba(16, 185, 129, 0.15); color: #10b981;">palette</div>
                    <div>
                        <h3>图片生成</h3>
                        <p class="settings-desc">角色立绘、场景图、分镜参考图</p>
                    </div>
                </div>

                <div class="form-group">
                    <label>图片 Demo 测试模式</label>
                    <label class="toggle-switch">
                        <input type="checkbox" id="image-demo-mode" ${imageDemoMode ? 'checked' : ''}>
                        <span class="toggle-slider"></span>
                    </label>
                    <p class="form-hint">启用后使用占位图替代真实生成，无需 API 密钥</p>
                </div>

                <div class="form-group">
                    <label>Provider</label>
                    <select id="image-provider">
                        <option value="siliconflow" ${image.provider === 'siliconflow' ? 'selected' : ''}>SiliconFlow</option>
                        <option value="openai" ${image.provider === 'openai' ? 'selected' : ''}>OpenAI (DALL-E)</option>
                        <option value="google_genai" ${image.provider === 'google_genai' ? 'selected' : ''}>Google Imagen</option>
                        <option value="stability" ${image.provider === 'stability' ? 'selected' : ''}>Stability AI</option>
                        <option value="custom" ${image.provider === 'custom' ? 'selected' : ''}>自定义</option>
                    </select>
                </div>

                <div class="form-group" id="image-base-url-group">
                    <label>Base URL</label>
                    <input type="text" id="image-base-url" value="${image.base_url || ''}"
                           placeholder="https://api.siliconflow.cn/v1">
                </div>

                <div class="form-group" id="image-api-key-group">
                    <label>API Key</label>
                    <div class="input-with-button">
                        <input type="password" id="image-api-key"
                               placeholder="${image.has_api_key ? '已配置' : '输入 API Key'}">
                        <button class="btn-secondary btn-sm" onclick="Settings.testConnection('image')">测试</button>
                    </div>
                </div>

                <div class="form-group">
                    <label>Model</label>
                    <input type="text" id="image-model" value="${image.model || 'Kwai-Kolors/Kolors'}"
                           placeholder="Kwai-Kolors/Kolors">
                    <p class="form-hint">SiliconFlow: Kwai-Kolors/Kolors, stabilityai/stable-diffusion-3-5-large</p>
                </div>

                <div class="form-group" id="image-size-group" style="display: ${showAdvanced || !isGoogle ? 'block' : 'none'};">
                    <label>Image Size</label>
                    <select id="image-size">
                        <option value="1024x1024" ${image.image_size === '1024x1024' ? 'selected' : ''}>1024 x 1024</option>
                        <option value="1024x768" ${image.image_size === '1024x768' ? 'selected' : ''}>1024 x 768</option>
                        <option value="768x1024" ${image.image_size === '768x1024' ? 'selected' : ''}>768 x 1024</option>
                        <option value="768x768" ${image.image_size === '768x768' ? 'selected' : ''}>768 x 768</option>
                        <option value="512x512" ${image.image_size === '512x512' ? 'selected' : ''}>512 x 512</option>
                    </select>
                </div>

                <div class="form-group" id="image-advanced-group" style="display: ${showAdvanced ? 'block' : 'none'};">
                    <label style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                        <span>
                            Inference Steps
                            <input type="number" id="image-inference-steps" value="${image.num_inference_steps || 20}" min="1" max="100" style="margin-top:6px;">
                        </span>
                        <span>
                            Guidance Scale
                            <input type="number" id="image-guidance-scale" value="${image.guidance_scale || 7.5}" min="1" max="20" step="0.5" style="margin-top:6px;">
                        </span>
                    </label>
                </div>

                <div class="form-group" id="image-google-test-row" style="display: ${isGoogle ? 'block' : 'none'};">
                    <label>Google Imagen 连接</label>
                    <div class="settings-inline-actions">
                        <button class="btn-secondary btn-sm" onclick="Settings.testConnection('image')">测试 Google Imagen</button>
                    </div>
                    <p class="form-hint">使用当前 Project / Location 与 ADC 凭证测试 Imagen 连接。</p>
                </div>
            </div>
        `;
    },

    _renderVideoSection(video, mode) {
        const demoMode = this.currentConfig?.video_demo_mode || false;
        return `
            <div class="settings-section">
                <div class="settings-section-header">
                    <div class="settings-section-icon material-symbols-outlined" style="background: rgba(233, 69, 96, 0.15); color: #e94560;">movie</div>
                    <div>
                        <h3>视频生成</h3>
                        <p class="settings-desc">分镜视频、成片渲染</p>
                    </div>
                </div>

                <div class="form-group">
                    <label>Demo 测试模式</label>
                    <label class="toggle-switch">
                        <input type="checkbox" id="video-demo-mode" ${demoMode ? 'checked' : ''}>
                        <span class="toggle-slider"></span>
                    </label>
                    <p class="form-hint">启用后使用空白视频替代真实生成，无需填写 API 密钥</p>
                </div>

                <div id="video-real-config" style="${demoMode ? 'opacity: 0.4; pointer-events: none;' : ''}">
                    <div class="form-group">
                        <label>Provider</label>
                        <select id="video-provider">
                            <option value="seedance" ${video.provider === 'seedance' ? 'selected' : ''}>Seedance</option>
                            <option value="runway" ${video.provider === 'runway' ? 'selected' : ''}>Runway</option>
                            <option value="pika" ${video.provider === 'pika' ? 'selected' : ''}>Pika</option>
                            <option value="custom" ${video.provider === 'custom' ? 'selected' : ''}>自定义</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label>Base URL</label>
                        <input type="text" id="video-base-url" value="${video.base_url || ''}"
                               placeholder="https://api.seedance.com/v1">
                    </div>

                    <div class="form-group">
                        <label>API Key</label>
                        <div class="input-with-button">
                            <input type="password" id="video-api-key"
                                   placeholder="${video.has_api_key ? '已配置' : '输入 API Key'}">
                            <button class="btn-secondary btn-sm" onclick="Settings.testConnection('video')">测试</button>
                        </div>
                    </div>

                    <div class="form-group">
                        <label>Model</label>
                        <input type="text" id="video-model" value="${video.model || 'seedance-2.0'}"
                               placeholder="seedance-2.0">
                    </div>
                </div>

                <div class="form-group">
                    <label>生成模式</label>
                    <select id="video-generation-mode">
                        <option value="manual" ${mode === 'manual' ? 'selected' : ''}>手动触发</option>
                        <option value="auto" ${mode === 'auto' ? 'selected' : ''}>自动执行</option>
                    </select>
                    <p class="form-hint">手动模式避免意外产生费用</p>
                </div>
            </div>
        `;
    },

    _renderGoogleSection(google) {
        return `
            <div class="settings-section" style="margin-top: var(--space-lg);">
                <div class="settings-section-header">
                    <div class="settings-section-icon material-symbols-outlined" style="background: rgba(66, 133, 244, 0.15); color: #4285f4;">cloud</div>
                    <div>
                        <h3>Google Cloud 配置</h3>
                        <p class="settings-desc">Vertex AI 认证使用 Application Default Credentials (ADC)，无需 API Key</p>
                    </div>
                </div>

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                    <div class="form-group">
                        <label>GCP Project ID</label>
                        <input type="text" id="google-project" value="${google.project || ''}"
                               placeholder="my-gcp-project">
                        <p class="form-hint">留空则使用环境变量 GOOGLE_CLOUD_PROJECT</p>
                    </div>
                    <div class="form-group">
                        <label>Location</label>
                        <input type="text" id="google-location" value="${google.location || 'us-central1'}"
                               placeholder="us-central1">
                        <p class="form-hint">留空则使用环境变量 GOOGLE_CLOUD_LOCATION</p>
                    </div>
                </div>

                <p class="form-hint" style="margin-top: 4px;">
                    认证方式: 请确保已通过 <code>gcloud auth application-default login</code> 登录，
                    或设置了 <code>GOOGLE_APPLICATION_CREDENTIALS</code> 环境变量。
                </p>
            </div>
        `;
    },

    bindEvents() {
        document.getElementById('settings-content')?.addEventListener('change', (e) => {
            if (e.target.id === 'llm-provider') {
                this.handleLLMProviderChange(e.target.value);
            } else if (e.target.id === 'image-provider') {
                this.handleImageProviderChange(e.target.value);
            } else if (e.target.id === 'video-demo-mode') {
                this.handleVideoDemoModeChange(e.target.checked);
            }
        });
    },

    handleVideoDemoModeChange(enabled) {
        const realConfig = document.getElementById('video-real-config');
        if (realConfig) {
            realConfig.style.opacity = enabled ? '0.4' : '1';
            realConfig.style.pointerEvents = enabled ? 'none' : '';
        }
    },

    handleLLMProviderChange(provider) {
        const baseInput = document.getElementById('llm-base-url');
        const modelInput = document.getElementById('llm-model');
        const baseUrlGroup = document.getElementById('llm-base-url-group');
        const apiKeyGroup = document.getElementById('llm-api-key-group');
        const googleSection = document.getElementById('google-config-section');
        const googleTestRow = document.getElementById('llm-google-test-row');

        const isGoogle = provider === 'google_genai';

        baseUrlGroup.style.display = isGoogle ? 'none' : 'block';
        apiKeyGroup.style.display = isGoogle ? 'none' : 'block';
        if (googleTestRow) googleTestRow.style.display = isGoogle ? 'block' : 'none';

        if (isGoogle) {
            modelInput.placeholder = 'gemini-2.5-flash';
            googleSection.style.display = 'block';
        } else {
            googleSection.style.display = this._shouldShowGoogle() ? 'block' : 'none';
            const configs = {
                openai: { url: 'https://api.openai.com/v1', model: 'gpt-4o' },
                azure: { url: 'https://YOUR_RESOURCE.openai.azure.com', model: 'gpt-4o' },
                anthropic: { url: 'https://api.anthropic.com', model: 'claude-3-opus-20240229' },
            };
            const cfg = configs[provider] || { url: '', model: '' };
            baseInput.placeholder = cfg.url || 'Base URL';
            modelInput.placeholder = cfg.model;
        }
    },

    handleImageProviderChange(provider) {
        const baseInput = document.getElementById('image-base-url');
        const modelInput = document.getElementById('image-model');
        const baseUrlGroup = document.getElementById('image-base-url-group');
        const apiKeyGroup = document.getElementById('image-api-key-group');
        const googleSection = document.getElementById('google-config-section');
        const googleTestRow = document.getElementById('image-google-test-row');
        const sizeGroup = document.getElementById('image-size-group');
        const advancedGroup = document.getElementById('image-advanced-group');

        const isGoogle = provider === 'google_genai';
        const isSiliconFlow = provider === 'siliconflow';

        baseUrlGroup.style.display = isGoogle ? 'none' : 'block';
        apiKeyGroup.style.display = isGoogle ? 'none' : 'block';
        if (googleTestRow) googleTestRow.style.display = isGoogle ? 'block' : 'none';
        if (sizeGroup) sizeGroup.style.display = isGoogle ? 'none' : 'block';
        if (advancedGroup) advancedGroup.style.display = isSiliconFlow ? 'block' : 'none';

        const configs = {
            siliconflow: { url: 'https://api.siliconflow.cn/v1', model: 'Kwai-Kolors/Kolors' },
            openai: { url: 'https://api.openai.com/v1', model: 'dall-e-3' },
            stability: { url: 'https://api.stability.ai/v1', model: 'stable-diffusion-xl-1024-v1-0' },
        };

        if (isGoogle) {
            modelInput.placeholder = 'imagen-4.0-generate-001';
            googleSection.style.display = 'block';
        } else {
            googleSection.style.display = this._shouldShowGoogle() ? 'block' : 'none';
            const cfg = configs[provider] || { url: '', model: '' };
            baseInput.placeholder = cfg.url || 'Base URL';
            modelInput.placeholder = cfg.model;
        }
    },
    _shouldShowGoogle() {
        const llmProvider = document.getElementById('llm-provider')?.value;
        const imageProvider = document.getElementById('image-provider')?.value;
        return llmProvider === 'google_genai' || imageProvider === 'google_genai';
    },

    updateProviderUI() {
        const llmProvider = document.getElementById('llm-provider')?.value;
        const imageProvider = document.getElementById('image-provider')?.value;
        if (llmProvider) this.handleLLMProviderChange(llmProvider);
        if (imageProvider) this.handleImageProviderChange(imageProvider);
    },

    async saveSettings() {
        const statusEl = document.getElementById('settings-status');
        statusEl.textContent = '保存中...';
        statusEl.className = 'status-message';

        const config = {
            llm: {
                provider: document.getElementById('llm-provider')?.value || 'openai',
                base_url: document.getElementById('llm-base-url')?.value || '',
                api_key: document.getElementById('llm-api-key')?.value || '',
                model: document.getElementById('llm-model')?.value || 'gpt-4o',
            },
            image: {
                provider: document.getElementById('image-provider')?.value || 'openai',
                base_url: document.getElementById('image-base-url')?.value || '',
                api_key: document.getElementById('image-api-key')?.value || '',
                model: document.getElementById('image-model')?.value || 'Kwai-Kolors/Kolors',
                image_size: document.getElementById('image-size')?.value || '1024x1024',
                num_inference_steps: parseInt(document.getElementById('image-inference-steps')?.value || '20'),
                guidance_scale: parseFloat(document.getElementById('image-guidance-scale')?.value || '7.5'),
            },
            video: {
                provider: document.getElementById('video-provider')?.value || 'seedance',
                base_url: document.getElementById('video-base-url')?.value || '',
                api_key: document.getElementById('video-api-key')?.value || '',
                model: document.getElementById('video-model')?.value || 'seedance-2.0',
            },
            google: {
                project: document.getElementById('google-project')?.value || '',
                location: document.getElementById('google-location')?.value || 'us-central1',
            },
            video_generation_mode: document.getElementById('video-generation-mode')?.value || 'manual',
            video_demo_mode: document.getElementById('video-demo-mode')?.checked || false,
            image_demo_mode: document.getElementById('image-demo-mode')?.checked || false,
        };

        try {
            const res = await fetch('http://localhost:8000/api/v1/settings/models', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config),
            });

            if (res.ok) {
                statusEl.textContent = '\u2713 \u5DF2\u4FDD\u5B58';
                statusEl.className = 'status-message success';
                // Clear API key inputs so placeholder updates on next render
                const llmKey = document.getElementById('llm-api-key');
                const imgKey = document.getElementById('image-api-key');
                const vidKey = document.getElementById('video-api-key');
                if (llmKey) { llmKey.value = ''; llmKey.placeholder = '\u5DF2\u914D\u7F6E'; }
                if (imgKey) { imgKey.value = ''; imgKey.placeholder = '\u5DF2\u914D\u7F6E'; }
                if (vidKey) { vidKey.value = ''; vidKey.placeholder = '\u5DF2\u914D\u7F6E'; }
            } else {
                const err = await res.json();
                statusEl.textContent = `保存失败: ${err.detail || res.statusText}`;
                statusEl.className = 'status-message error';
            }
        } catch (err) {
            statusEl.textContent = `保存失败: ${err.message}`;
            statusEl.className = 'status-message error';
        }
    },

    async testConnection(type) {
        const labels = { llm: 'LLM', image: '图片', video: '视频' };

        // Save first — this re-renders the entire settings UI,
        // so we must re-query the status element afterward.
        await this.saveSettings();

        const statusEl = document.getElementById('settings-status');
        if (!statusEl) return;
        statusEl.textContent = `测试${labels[type]}连接...`;
        statusEl.className = 'status-message';

        try {
            const res = await fetch('http://localhost:8000/api/v1/settings/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider_type: type }),
            });

            const result = await res.json();
            // Re-query in case saveSettings triggered another render
            const el = document.getElementById('settings-status') || statusEl;
            el.textContent = result.success ? `\u2713 ${result.message}` : `\u2717 ${result.message}`;
            el.className = `status-message ${result.success ? 'success' : 'error'}`;
        } catch (err) {
            const el = document.getElementById('settings-status') || statusEl;
            el.textContent = `测试失败: ${err.message}`;
            el.className = 'status-message error';
        }
    },

    showError(message) {
        const container = document.getElementById('settings-content');
        if (container) {
            container.innerHTML = `
                <div class="error-state">
                    <div class="error-icon material-symbols-outlined">warning</div>
                    <p>${message}</p>
                    <button class="btn-secondary" onclick="Settings.loadSettings()">重试</button>
                </div>
            `;
        }
    },
};
