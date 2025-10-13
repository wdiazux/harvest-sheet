const CONFIG = {
    GOOGLE_CLIENT_ID: 'YOUR_GOOGLE_CLIENT_ID',
    GITHUB_OWNER: 'wdiazux',
    GITHUB_REPO: 'harvest-sheet',
    GITHUB_API_BASE: 'https://api.github.com',
    AVAILABLE_USERS: [] // Will be loaded from config.json
};

let currentUser = null;
let currentJobId = null;

// Load user configuration from config.json
async function loadUserConfig() {
    try {
        const response = await fetch('config.json');
        const data = await response.json();
        CONFIG.AVAILABLE_USERS = data.users || [];
        console.log('✅ User configuration loaded:', CONFIG.AVAILABLE_USERS.length, 'users');
        populateUserSelect();
    } catch (error) {
        console.error('❌ Failed to load user configuration:', error);
        // Fallback to default
        CONFIG.AVAILABLE_USERS = [{ value: 'all', label: 'All Users' }];
        populateUserSelect();
    }
}

function populateUserSelect() {
    const userSelect = document.getElementById('userSelect');
    userSelect.innerHTML = '';
    CONFIG.AVAILABLE_USERS.forEach(user => {
        const option = document.createElement('option');
        option.value = user.value;
        option.textContent = user.label;
        userSelect.appendChild(option);
    });
}

function initGoogleAuth() {
    // Wait for Google Identity Services library to load
    if (typeof google !== 'undefined' && google.accounts && google.accounts.id) {
        google.accounts.id.initialize({
            client_id: CONFIG.GOOGLE_CLIENT_ID,
            callback: handleCredentialResponse
        });
        console.log('Google Auth initialized');
    } else {
        // Retry after a short delay if library not loaded yet
        setTimeout(initGoogleAuth, 100);
    }
}

function handleCredentialResponse(response) {
    try {
        const payload = parseJwt(response.credential);
        const email = payload.email;

        currentUser = {
            email: email,
            name: payload.name,
            picture: payload.picture,
            token: response.credential
        };

        console.log(`User signed in: ${email}`);
        showMainApp();

    } catch (error) {
        console.error('Authentication error:', error);
        showAuthError('Authentication failed. Please try again.');
    }
}

function parseJwt(token) {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
        return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
    }).join(''));
    return JSON.parse(jsonPayload);
}

function showAuthError(message) {
    const errorDiv = document.getElementById('authError');
    errorDiv.textContent = message;
    errorDiv.classList.remove('hidden');
}

function showMainApp() {
    document.getElementById('authSection').classList.add('hidden');
    document.getElementById('mainApp').classList.remove('hidden');

    document.getElementById('userName').textContent = currentUser.name;
    document.getElementById('userEmail').textContent = currentUser.email;
    document.getElementById('userPhoto').src = currentUser.picture;

    populateUserDropdown();
    setDefaultDates();
}

function populateUserDropdown() {
    const select = document.getElementById('userSelect');
    select.innerHTML = '';

    CONFIG.AVAILABLE_USERS.forEach(user => {
        const option = document.createElement('option');
        option.value = user.value;
        option.textContent = user.label;
        select.appendChild(option);
    });
}

function setDefaultDates() {
    const today = new Date();
    const lastWeek = new Date(today);
    lastWeek.setDate(today.getDate() - 7);

    document.getElementById('fromDate').value = lastWeek.toISOString().split('T')[0];
    document.getElementById('toDate').value = today.toISOString().split('T')[0];
}

function signOut() {
    google.accounts.id.disableAutoSelect();
    currentUser = null;
    currentJobId = null;

    document.getElementById('mainApp').classList.add('hidden');
    document.getElementById('authSection').classList.remove('hidden');
    document.getElementById('jobStatus').classList.add('hidden');
    document.getElementById('authError').classList.add('hidden');
}

document.getElementById('harvestForm').addEventListener('submit', async function(e) {
    e.preventDefault();

    if (!currentUser) {
        alert('Please sign in first.');
        return;
    }

    const params = {
        user_email: currentUser.email,
        user_token: currentUser.token,
        from_date: document.getElementById('fromDate').value,
        to_date: document.getElementById('toDate').value,
        user_prefix: document.getElementById('userSelect').value,
        upload_to_sheets: document.getElementById('uploadToSheets').checked,
        include_advanced_fields: document.getElementById('includeAdvancedFields').checked,
        enable_raw_json: document.getElementById('enableRawJson').checked,
        debug_mode: document.getElementById('debugMode').checked
    };

    try {
        await triggerGitHubAction(params);
    } catch (error) {
        console.error('Error triggering job:', error);
        alert('Failed to start job. Please try again.');
    }
});

async function triggerGitHubAction(params) {
    const runButton = document.getElementById('runButton');
    runButton.disabled = true;
    runButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Preparing...';

    try {
        const workflowParams = {
            user_email: sanitizeInput(currentUser.email),
            user_token_hash: await hashToken(currentUser.token),
            from_date: sanitizeInput(params.from_date),
            to_date: sanitizeInput(params.to_date),
            user_prefix: sanitizeInput(params.user_prefix),
            upload_to_sheets: params.upload_to_sheets,
            include_advanced_fields: params.include_advanced_fields,
            enable_raw_json: params.enable_raw_json,
            debug_mode: params.debug_mode,
            timestamp: Date.now(),
            csrf_token: generateCSRFToken()
        };

        showManualTriggerInstructions(workflowParams);

    } catch (error) {
        console.error('Error preparing job:', error);
        showJobStatus('Failed to prepare job parameters. Please try again.', 'error');
    } finally {
        runButton.disabled = false;
        runButton.innerHTML = '<i class="fas fa-play"></i> Generate Report';
    }
}

function sanitizeInput(input) {
    if (typeof input !== 'string') return input;

    return input
        .replace(/[<>'"&]/g, '')
        .replace(/[;|&$`]/g, '')
        .trim()
        .substring(0, 100);
}
function generateCSRFToken() {
    const array = new Uint32Array(4);
    crypto.getRandomValues(array);
    return Array.from(array, dec => dec.toString(16)).join('');
}

async function hashToken(token) {
    const encoder = new TextEncoder();
    const data = encoder.encode(token + Date.now());
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('').substring(0, 16);
}

function showManualTriggerInstructions(params) {
    const instructions = `
        <div class="alert alert-info">
            <h5><i class="fas fa-info-circle"></i> Manual Trigger Required</h5>
            <p>For security, please manually trigger the workflow:</p>
            <ol>
                <li>Go to <a href="https://github.com/${CONFIG.GITHUB_OWNER}/${CONFIG.GITHUB_REPO}/actions/workflows/web-trigger.yml" target="_blank">GitHub Actions</a></li>
                <li>Click "Run workflow"</li>
                <li>Fill in the parameters below:</li>
            </ol>
        </div>
        <div class="card">
            <div class="card-header">
                <h6>Workflow Parameters</h6>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6">
                        <strong>user_email:</strong> ${params.user_email}<br>
                        <strong>from_date:</strong> ${params.from_date}<br>
                        <strong>to_date:</strong> ${params.to_date}<br>
                        <strong>user_prefix:</strong> ${params.user_prefix}
                    </div>
                    <div class="col-md-6">
                        <strong>upload_to_sheets:</strong> ${params.upload_to_sheets}<br>
                        <strong>include_advanced_fields:</strong> ${params.include_advanced_fields}<br>
                        <strong>enable_raw_json:</strong> ${params.enable_raw_json}<br>
                        <strong>debug_mode:</strong> ${params.debug_mode}
                    </div>
                </div>
                <div class="mt-3">
                    <small class="text-muted">
                        Security tokens: ${params.user_token_hash} | ${params.csrf_token}
                    </small>
                </div>
            </div>
        </div>
        <div class="mt-3">
            <a href="https://github.com/${CONFIG.GITHUB_OWNER}/${CONFIG.GITHUB_REPO}/actions/workflows/web-trigger.yml"
               target="_blank" class="btn btn-primary">
                <i class="fas fa-external-link-alt"></i> Go to GitHub Actions
            </a>
        </div>
    `;

    showJobStatus(instructions, 'running');
}

function showJobStatus(message, status) {
    const statusDiv = document.getElementById('jobStatus');
    const contentDiv = document.getElementById('statusContent');

    statusDiv.classList.remove('hidden');
    contentDiv.innerHTML = `<div class="status-${status}">${message}</div>`;
    statusDiv.scrollIntoView({ behavior: 'smooth' });
}

async function checkJobStatus() {
    const refreshButton = document.getElementById('refreshButton');
    refreshButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Checking...';

    try {
        setTimeout(() => {
            showJobStatus('Job completed successfully!', 'success');
            document.getElementById('downloadButton').classList.remove('hidden');
            document.getElementById('downloadButton').href = `https://github.com/${CONFIG.GITHUB_OWNER}/${CONFIG.GITHUB_REPO}/actions`;
            refreshButton.innerHTML = '<i class="fas fa-sync-alt"></i> Refresh';
        }, 2000);

    } catch (error) {
        console.error('Error checking status:', error);
        showJobStatus('Error checking job status', 'error');
        refreshButton.innerHTML = '<i class="fas fa-sync-alt"></i> Refresh';
    }
}

document.addEventListener('DOMContentLoaded', function() {
    loadUserConfig(); // Load users first
    initGoogleAuth();
});