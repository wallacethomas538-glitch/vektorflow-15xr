<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    <title>VektorFlow 15xr | Voice AI Command Center</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #f0f2f5; font-family: 'Inter', system-ui, sans-serif; color: #1a1a2e; }
        
        .stat-card { background: white; border-radius: 20px; padding: 1rem; box-shadow: 0 2px 8px rgba(0,0,0,0.05); border: 1px solid #e9ecef; }
        .stat-value { font-size: 2rem; font-weight: 700; color: #7c3aed; }
        
        .auth-card { background: white; border-radius: 28px; border: 1px solid #e9ecef; padding: 2rem; max-width: 420px; width: 100%; margin: 2rem auto; box-shadow: 0 10px 40px rgba(0,0,0,0.1); }
        
        .dashboard-container { display: none; min-height: 100vh; flex-direction: column; background: #f0f2f5; }
        .top-bar { background: white; border-bottom: 1px solid #e9ecef; padding: 0.75rem 1.5rem; position: sticky; top: 0; z-index: 100; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }
        .bottom-nav { position: fixed; bottom: 0; left: 0; right: 0; background: white; border-top: 1px solid #e9ecef; display: flex; justify-content: space-around; padding: 0.6rem 1rem; z-index: 100; }
        .nav-tab { background: transparent; border: none; color: #888; font-size: 0.75rem; display: flex; flex-direction: column; align-items: center; gap: 0.25rem; padding: 0.4rem 0.8rem; border-radius: 12px; transition: all 0.2s; }
        .nav-tab i { font-size: 1.2rem; }
        .nav-tab.active { color: #7c3aed; background: rgba(124,58,237,0.1); }
        .main-content { padding: 1rem 1rem 5rem 1rem; max-width: 1200px; margin: 0 auto; width: 100%; }
        .page-section { display: none; }
        .page-section.active-page { display: block; }
        
        .form-control, .form-select { background: white; border: 1px solid #ddd; color: #1a1a2e; border-radius: 12px; }
        .btn-primary-custom { background: #7c3aed; border: none; border-radius: 12px; padding: 0.5rem 1.2rem; font-weight: 500; color: white; }
        .btn-primary-custom:hover { background: #6d28d9; }
        
        /* Task Results Section */
        .task-results { background: white; border-radius: 16px; padding: 1rem; margin-top: 1rem; border: 1px solid #e9ecef; max-height: 400px; overflow-y: auto; }
        .task-card { background: #f8f9fa; border-radius: 12px; padding: 1rem; margin-bottom: 1rem; border-left: 4px solid #7c3aed; }
        .task-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; }
        .task-title { font-weight: 600; color: #7c3aed; }
        .task-time { font-size: 0.7rem; color: #888; }
        .task-content { color: #1a1a2e; font-size: 0.85rem; line-height: 1.5; white-space: pre-wrap; }
        .task-badge { background: #e9ecef; padding: 0.2rem 0.5rem; border-radius: 12px; font-size: 0.65rem; }
        
        .status-badge { background: #e9ecef; color: #1a1a2e; padding: 0.2rem 0.7rem; border-radius: 20px; font-size: 0.7rem; }
        
        /* Mic Button */
        .mic-container { text-align: center; padding: 1.5rem; }
        .mic-btn { background: #7c3aed; border: none; width: 70px; height: 70px; border-radius: 35px; color: white; font-size: 1.8rem; transition: all 0.2s; box-shadow: 0 4px 12px rgba(124,58,237,0.3); }
        .mic-btn.listening { background: #10b981; animation: pulse 1.5s infinite; }
        @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(16,185,129,0.7); } 70% { box-shadow: 0 0 0 20px rgba(16,185,129,0); } 100% { box-shadow: 0 0 0 0 rgba(16,185,129,0); } }
        
        .listening-indicator { text-align: center; margin-top: 0.5rem; font-size: 0.8rem; color: #6c757d; }
        
        .api-key-section { background: #f8f9fa; border: 1px solid #e9ecef; }
        .legal-footer { text-align: center; font-size: 0.65rem; color: #888; padding: 1rem; border-top: 1px solid #e9ecef; margin-top: 2rem; background: white; }
        .legal-footer a { color: #7c3aed; text-decoration: none; }
        
        .text-muted { color: #6c757d !important; }
        h1, h2, h3, h4, h5, .fw-bold { color: #1a1a2e; }
    </style>
</head>
<body>

<!-- LOGIN PAGE -->
<div id="authPage" style="min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 1rem; background: #f0f2f5;">
    <div class="auth-card">
        <div class="text-center mb-4">
            <i class="fas fa-bolt fs-1" style="color: #7c3aed;"></i>
            <h2 class="mt-2">VektorFlow 15xr</h2>
            <p class="text-muted">Voice AI Command Center</p>
        </div>
        <input type="email" id="loginEmail" class="form-control mb-2" placeholder="your@email.com">
        <input type="password" id="loginPassword" class="form-control mb-3" placeholder="Password (min 6 chars)">
        <button id="signupBtn" class="btn btn-primary-custom w-100 mb-2">📝 Sign Up (Free Trial)</button>
        <button id="loginBtn" class="btn btn-primary-custom w-100 mb-3" style="background: #3b82f6;">🔓 Sign In</button>
        <div id="authMessage" class="mt-3 small text-center text-muted"></div>
    </div>
</div>

<!-- MAIN DASHBOARD -->
<div id="dashboardContainer" class="dashboard-container">
    <div class="top-bar">
        <div class="d-flex align-items-center gap-2">
            <i class="fas fa-bolt fs-5" style="color: #7c3aed;"></i>
            <span class="fw-bold">VektorFlow 15xr</span>
            <span class="status-badge ms-2" id="statusBadge">● ONLINE</span>
        </div>
        <div class="d-flex align-items-center gap-3">
            <span id="userEmailDisplay" class="small text-muted"></span>
            <button id="logoutBtn" class="btn btn-sm btn-outline-danger"><i class="fas fa-sign-out-alt"></i></button>
        </div>
    </div>

    <div class="main-content">
        <!-- HOME PAGE -->
        <div id="homePage" class="page-section active-page">
            <!-- Stats Row -->
            <div class="row g-3 mb-4">
                <div class="col-6 col-md-3"><div class="stat-card"><div class="text-muted small">Products</div><div class="stat-value" id="statProducts">0</div></div></div>
                <div class="col-6 col-md-3"><div class="stat-card"><div class="text-muted small">Campaigns</div><div class="stat-value" id="statCampaigns">2</div></div></div>
                <div class="col-6 col-md-3"><div class="stat-card"><div class="text-muted small">Agents</div><div class="stat-value" id="statAgents">15</div></div></div>
                <div class="col-6 col-md-3"><div class="stat-card"><div class="text-muted small">Memories</div><div class="stat-value" id="statMemories">0</div></div></div>
            </div>

            <!-- API KEYS -->
            <div class="stat-card api-key-section mb-4 p-3">
                <h5><i class="fas fa-key me-2"></i>🔐 API Key</h5>
                <div class="mb-2">
                    <label class="small">Groq API Key</label>
                    <input type="password" id="userGroqKey" class="form-control" placeholder="gsk_...">
                </div>
                <button id="saveKeysBtn" class="btn btn-outline-secondary btn-sm">💾 Save Key</button>
                <div id="keysMessage" class="mt-2 small"></div>
            </div>

            <!-- AI MODEL -->
            <h5 class="mb-3"><i class="fas fa-microchip me-2"></i>AI Model</h5>
            <div class="stat-card mb-4 p-3">
                <select id="dynamicModelSelect" class="form-select">
                    <option value="llama-3.3-70b-versatile">Llama 3.3 70B</option>
                    <option value="openai/gpt-oss-120b">GPT OSS 120B</option>
                </select>
            </div>

            <!-- TASK INPUT (Type or Voice) -->
            <div class="stat-card mb-4 p-3">
                <h5><i class="fas fa-tasks me-2"></i>Assign Task to AI</h5>
                <textarea id="taskInput" rows="2" class="form-control mb-2" placeholder="Describe the task... e.g., Find top 5 trending products on TikTok right now, or Analyze my catalog for best-selling items"></textarea>
                <div class="d-flex gap-2">
                    <button id="submitTaskBtn" class="btn btn-primary-custom flex-grow-1">🚀 Run Task</button>
                    <button id="voiceTaskBtn" class="mic-btn" style="width: 50px; height: 50px; font-size: 1.2rem;"><i class="fas fa-microphone"></i></button>
                </div>
                <div id="taskStatus" class="small text-muted mt-2"></div>
            </div>

            <!-- TASK RESULTS SECTION - Shows what the AI found -->
            <h5 class="mb-3"><i class="fas fa-clipboard-list me-2"></i>Task Results</h5>
            <div id="taskResultsContainer" class="task-results">
                <div class="text-muted small text-center py-3">Tasks you run will appear here with full results</div>
            </div>
        </div>

        <!-- CATALOG PAGE -->
        <div id="catalogPage" class="page-section"><div class="stat-card p-3 mb-3"><h5><i class="fas fa-upload me-2"></i>Upload Product Catalog</h5><input type="file" id="catalogFile" class="form-control mb-2" accept=".json"><input type="text" id="storeId" class="form-control mb-2" placeholder="Store ID" value="test-store"><button id="uploadCatalogBtn" class="btn btn-primary-custom w-100">Upload</button><div id="uploadResult" class="mt-3"></div></div></div>

        <!-- AGENTS PAGE -->
        <div id="agentsPage" class="page-section"><div class="stat-card p-3"><h5><i class="fas fa-robot me-2"></i>AI Agents Status</h5><div id="agentsList" class="mt-2"><div class="d-flex justify-content-between p-2 border-bottom"><span>Market Research Agent</span><span class="badge bg-success">Idle</span></div><div class="d-flex justify-content-between p-2 border-bottom"><span>Trend Analysis Agent</span><span class="badge bg-success">Idle</span></div><div class="d-flex justify-content-between p-2 border-bottom"><span>Content Writer Agent</span><span class="badge bg-success">Idle</span></div><div class="d-flex justify-content-between p-2 border-bottom"><span>Campaign Optimizer</span><span class="badge bg-success">Idle</span></div><div class="d-flex justify-content-between p-2 border-bottom"><span>Data Analyst Agent</span><span class="badge bg-success">Idle</span></div></div></div></div>

        <!-- CAMPAIGNS PAGE -->
        <div id="campaignsPage" class="page-section"><div class="stat-card p-3"><h5><i class="fas fa-fire me-2"></i>Trending Products</h5><button id="getTrendsBtn" class="btn btn-primary-custom w-100 mb-3">🔥 Get Trends</button><div id="trendsResult"></div></div><div class="stat-card p-3 mt-3"><h5><i class="fas fa-chart-line me-2"></i>Generate Campaign</h5><input type="text" id="campaignProductName" class="form-control mb-2" placeholder="Product name"><button id="generateCampaignBtn" class="btn btn-primary-custom w-100">Generate Campaign</button><div id="campaignResult" class="mt-3"></div></div></div>

        <!-- LEGAL FOOTER -->
        <div class="legal-footer">
            <span>⚠️ AI outputs are machine-generated.</span><br>
            <a href="/static/legal.html">Privacy Policy</a> | <a href="mailto:commander@vektorflow.com">Contact</a>
        </div>
    </div>

    <!-- BOTTOM NAVIGATION -->
    <div class="bottom-nav">
        <button class="nav-tab active" data-page="home"><i class="fas fa-home"></i><span>Home</span></button>
        <button class="nav-tab" data-page="catalog"><i class="fas fa-box"></i><span>Catalog</span></button>
        <button class="nav-tab" data-page="agents"><i class="fas fa-robot"></i><span>Agents</span></button>
        <button class="nav-tab" data-page="campaigns"><i class="fas fa-chart-line"></i><span>Campaigns</span></button>
    </div>
</div>

<script>
    const BASE = window.location.origin;
    let authToken = localStorage.getItem('authToken');
    let selectedModel = localStorage.getItem('selectedModel') || 'llama-3.3-70b-versatile';
    let recognition = null;
    let isListening = false;
    let synth = window.speechSynthesis;
    let currentTaskMode = 'text';

    // Speech Recognition
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'en-US';
        
        recognition.onstart = () => {
            isListening = true;
            document.getElementById('voiceTaskBtn').classList.add('listening');
            document.getElementById('voiceTaskBtn').innerHTML = '<i class="fas fa-stop"></i>';
            document.getElementById('taskStatus').innerHTML = '🎙️ Listening... Speak your task';
        };
        
        recognition.onend = () => {
            isListening = false;
            document.getElementById('voiceTaskBtn').classList.remove('listening');
            document.getElementById('voiceTaskBtn').innerHTML = '<i class="fas fa-microphone"></i>';
            if (document.getElementById('taskStatus').innerHTML === '🎙️ Listening... Speak your task') {
                document.getElementById('taskStatus').innerHTML = '';
            }
        };
        
        recognition.onresult = async (event) => {
            const transcript = event.results[0][0].transcript;
            document.getElementById('taskInput').value = transcript;
            document.getElementById('taskStatus').innerHTML = '⏳ Running task...';
            await runTask(transcript);
        };
        
        recognition.onerror = () => {
            document.getElementById('taskStatus').innerHTML = '❌ Voice error. Try typing.';
            recognition.stop();
        };
    }

    // Run a task and display results
    async function runTask(task) {
        const taskInputField = document.getElementById('taskInput');
        const statusDiv = document.getElementById('taskStatus');
        
        statusDiv.innerHTML = '⏳ AI is working on your task...';
        
        try {
            const { res, data } = await callApi('/llm/call', 'POST', { 
                prompt: task, 
                model: selectedModel 
            });
            
            if (res.ok && data.success) {
                const response = data.response;
                // Display result in task results section
                addTaskResult(task, response);
                // Speak the result summary
                speakText(`Task completed. ${response.substring(0, 200)}`);
                statusDiv.innerHTML = '✅ Task completed. See results below.';
                setTimeout(() => { if (statusDiv.innerHTML === '✅ Task completed. See results below.') statusDiv.innerHTML = ''; }, 4000);
            } else {
                addTaskResult(task, `Error: ${data.error || 'Request failed'}`);
                speakText(`Task failed. ${data.error || 'Request failed'}`);
                statusDiv.innerHTML = `❌ ${data.error || 'Request failed'}`;
            }
        } catch (err) {
            addTaskResult(task, `Error: ${err.message}`);
            speakText(`Task failed. ${err.message}`);
            statusDiv.innerHTML = `❌ ${err.message}`;
        }
    }

    // Add task result to the results container
    function addTaskResult(task, result) {
        const container = document.getElementById('taskResultsContainer');
        if (container.innerHTML.includes('Tasks you run will appear here')) {
            container.innerHTML = '';
        }
        
        const now = new Date();
        const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        
        const taskCard = document.createElement('div');
        taskCard.className = 'task-card';
        taskCard.innerHTML = `
            <div class="task-header">
                <span class="task-title"><i class="fas fa-robot me-1"></i> Task</span>
                <span class="task-time">${timeStr}</span>
            </div>
            <div class="task-content mb-2" style="background: #e9ecef; padding: 0.5rem; border-radius: 8px;">
                <strong>📝 Request:</strong> ${task}
            </div>
            <div class="task-content">
                <strong>📊 Result:</strong><br>${result}
            </div>
        `;
        
        container.prepend(taskCard);
        
        // Keep only last 10 tasks
        while (container.children.length > 10) {
            container.removeChild(container.lastChild);
        }
    }

    function speakText(text) {
        if (!synth) return;
        synth.cancel();
        // Shorten very long responses for speech
        let speakText = text;
        if (speakText.length > 300) {
            speakText = speakText.substring(0, 300) + "... (full results in dashboard)";
        }
        const utterance = new SpeechSynthesisUtterance(speakText);
        utterance.rate = 0.9;
        synth.speak(utterance);
    }

    // Voice button for task input
    document.getElementById('voiceTaskBtn')?.addEventListener('click', () => {
        if (!authToken) {
            speakText('Please log in first');
            return;
        }
        if (recognition && !isListening) {
            document.getElementById('taskInput').value = '';
            recognition.start();
        } else if (recognition && isListening) {
            recognition.stop();
        }
    });

    // Submit task button
    document.getElementById('submitTaskBtn')?.addEventListener('click', async () => {
        const task = document.getElementById('taskInput').value;
        if (!task) {
            speakText('Please describe a task first');
            return;
        }
        await runTask(task);
    });

    async function callApi(endpoint, method = 'GET', body = null) {
        const headers = { 'Content-Type': 'application/json' };
        if (authToken) headers['api-key'] = authToken;
        const res = await fetch(`${BASE}${endpoint}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
        const data = await res.json();
        return { res, data };
    }

    async function saveUserKeys() {
        const groqKey = document.getElementById('userGroqKey').value;
        const { res, data } = await callApi('/user/keys', 'POST', { groq_api_key: groqKey, gemini_api_key: "", hf_api_key: "" });
        const msgDiv = document.getElementById('keysMessage');
        if (res.ok) {
            msgDiv.innerHTML = '<span class="text-success">✅ Key saved!</span>';
            setTimeout(() => msgDiv.innerHTML = '', 3000);
            speakText('API key saved');
        } else {
            msgDiv.innerHTML = `<span class="text-danger">❌ ${data.detail || 'Failed'}</span>`;
        }
    }

    async function loadUserKeys() {
        const { res, data } = await callApi('/user/keys', 'GET');
        if (res.ok && data && data.groq_key) {
            document.getElementById('userGroqKey').value = data.groq_key;
        }
    }

    async function login(email, password) {
        const res = await fetch(`${BASE}/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) });
        const data = await res.json();
        if (res.ok) {
            authToken = data.access_token;
            localStorage.setItem('authToken', authToken);
            document.getElementById('authPage').style.display = 'none';
            document.getElementById('dashboardContainer').style.display = 'flex';
            document.getElementById('userEmailDisplay').innerText = email;
            await loadUserKeys();
            speakText('Welcome back Commander. Type or speak a task to get started.');
        } else { throw new Error(data.detail || 'Login failed'); }
    }

    async function signup(email, password) {
        const res = await fetch(`${BASE}/auth/signup`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password, store_name: email.split('@')[0] }) });
        const data = await res.json();
        if (res.ok) { await login(email, password); } else { throw new Error(data.detail || 'Signup failed'); }
    }

    function switchPage(pageId) {
        document.querySelectorAll('.page-section').forEach(s => s.classList.remove('active-page'));
        document.getElementById(`${pageId}Page`).classList.add('active-page');
        document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
        document.querySelector(`.nav-tab[data-page="${pageId}"]`).classList.add('active');
    }

    document.getElementById('signupBtn')?.addEventListener('click', async () => {
        const email = document.getElementById('loginEmail').value, pwd = document.getElementById('loginPassword').value;
        if (!email || pwd.length < 6) { document.getElementById('authMessage').innerText = 'Valid email and password (min 6 chars)'; return; }
        try { await signup(email, pwd); document.getElementById('authMessage').innerText = '✅ Signed up!'; setTimeout(() => location.reload(), 1000); } catch(err) { document.getElementById('authMessage').innerText = err.message; }
    });
    document.getElementById('loginBtn')?.addEventListener('click', async () => {
        const email = document.getElementById('loginEmail').value, pwd = document.getElementById('loginPassword').value;
        if (!email || !pwd) { document.getElementById('authMessage').innerText = 'Enter email and password'; return; }
        try { await login(email, pwd); document.getElementById('authMessage').innerText = '✅ Logged in!'; setTimeout(() => location.reload(), 1000); } catch(err) { document.getElementById('authMessage').innerText = err.message; }
    });
    document.getElementById('logoutBtn')?.addEventListener('click', () => { authToken = null; localStorage.removeItem('authToken'); document.getElementById('authPage').style.display = 'flex'; document.getElementById('dashboardContainer').style.display = 'none'; });
    document.getElementById('saveKeysBtn')?.addEventListener('click', saveUserKeys);
    document.getElementById('uploadCatalogBtn')?.addEventListener('click', async () => {
        const file = document.getElementById('catalogFile').files[0];
        if (!file) { document.getElementById('uploadResult').innerHTML = '<pre class="text-danger">Select a JSON file</pre>'; return; }
        const text = await file.text(); const products = JSON.parse(text); const storeId = document.getElementById('storeId').value;
        const { data } = await callApi('/ecommerce/catalog', 'POST', { store_id: storeId, products });
        document.getElementById('uploadResult').innerHTML = `<pre>✅ ${JSON.stringify(data, null, 2)}</pre>`;
        document.getElementById('statProducts').innerText = products.length;
        speakText(`${products.length} products uploaded`);
    });
    document.getElementById('getTrendsBtn')?.addEventListener('click', async () => {
        const storeId = document.getElementById('storeId')?.value || 'test-store';
        const { data } = await callApi(`/ecommerce/trends/${storeId}`, 'GET');
        document.getElementById('trendsResult').innerHTML = `<pre>${JSON.stringify(data, null, 2)}</pre>`;
        addTaskResult("Get trending products", JSON.stringify(data, null, 2));
        speakText(`Found ${data.matches?.length || 0} trending products`);
    });
    document.getElementById('generateCampaignBtn')?.addEventListener('click', async () => {
        const product = document.getElementById('campaignProductName').value;
        if (!product) { speakText('Please enter a product name'); return; }
        const storeId = document.getElementById('storeId')?.value || 'test-store';
        const { data } = await callApi(`/ecommerce/campaign/${storeId}/${encodeURIComponent(product)}`, 'GET');
        document.getElementById('campaignResult').innerHTML = `<pre>${JSON.stringify(data, null, 2)}</pre>`;
        addTaskResult(`Generate campaign for ${product}`, JSON.stringify(data, null, 2));
        speakText(`Campaign generated for ${product}`);
    });
    document.querySelectorAll('.nav-tab').forEach(tab => { tab.addEventListener('click', () => switchPage(tab.dataset.page)); });
    document.getElementById('dynamicModelSelect')?.addEventListener('change', (e) => { selectedModel = e.target.value; localStorage.setItem('selectedModel', selectedModel); });

    if (authToken) {
        document.getElementById('authPage').style.display = 'none';
        document.getElementById('dashboardContainer').style.display = 'flex';
        document.getElementById('userEmailDisplay').innerText = 'commander@vektorflow.com';
        loadUserKeys();
    }
</script>
</body>
</html>
