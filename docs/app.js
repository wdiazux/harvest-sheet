const CONFIG = {
    GOOGLE_CLIENT_ID: 'YOUR_GOOGLE_CLIENT_ID',
    WORKER_URL: 'YOUR_WORKER_URL',   // injected at deploy, e.g. https://harvest-web-trigger.<acct>.workers.dev
    AVAILABLE_USERS: [] // Will be loaded from config.json
};

let currentUser = null;

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
        from_date: document.getElementById('fromDate').value,
        to_date: document.getElementById('toDate').value,
        user_prefix: document.getElementById('userSelect').value,
        upload_to_sheets: document.getElementById('uploadToSheets').checked,
        include_advanced_fields: document.getElementById('includeAdvancedFields').checked
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
    runButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Triggering workflow...';
    try {
        const res = await fetch(`${CONFIG.WORKER_URL}/trigger`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                google_id_token: currentUser.token,           // Google ID token (response.credential)
                from_date: params.from_date,
                to_date: params.to_date,
                user_prefix: params.user_prefix,
                upload_to_sheets: params.upload_to_sheets,
                include_advanced_fields: params.include_advanced_fields,
            }),
        });
        if (res.status === 202) {
            showJobStatus('✅ Workflow triggered. Check the Actions tab for progress.', 'success');
        } else if (res.status === 401) {
            showJobStatus('❌ Sign-in could not be verified. Please sign in again.', 'error');
        } else if (res.status === 403) {
            showJobStatus('❌ Your account is not authorized.', 'error');
        } else {
            showJobStatus('❌ Could not start the job. Please try again later.', 'error');
        }
    } catch (e) {
        showJobStatus('❌ Network error. Please try again.', 'error');
    } finally {
        runButton.disabled = false;
        runButton.innerHTML = '<i class="fas fa-play"></i> Generate Report';
    }
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
            document.getElementById('downloadButton').href = 'https://github.com/wdiazux/harvest-sheet/actions';
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