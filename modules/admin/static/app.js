/**
 * SeenSlide Admin Application
 * Handles authentication, session management, and server controls
 */

class AdminApp {
    constructor() {
        this.authenticated = false;
        this.currentUser = null;
        this.sessions = [];
        this.currentSessionId = null;
        this.talks = [];
        this.statusInterval = null;
        this.cloudEnabled = false;
        this.cloudSessionId = null;
        this.cloudApiUrl = null;
        this._loginListenerAdded = false;
        this._dashboardListenersAdded = false;

        this.init();
    }

    async init() {
        // Check if already authenticated
        try {
            const response = await fetch('/api/auth/me', {
                credentials: 'include'
            });
            if (response.ok) {
                const user = await response.json();
                this.authenticated = true;
                this.currentUser = user;
                this.showDashboard();                
            } else {
                this.showLogin();
            }
        } catch (error) {
            this.showLogin();
        }
    }

    showLogin() {
        document.getElementById('loginScreen').style.display = 'flex';
        document.getElementById('dashboard').style.display = 'none';

        // Only add event listener once
        if (!this._loginListenerAdded) {
            const form = document.getElementById('loginForm');
            form.addEventListener('submit', (e) => this.handleLogin(e));
            this._loginListenerAdded = true;
        }
    }

    showDashboard() {
        document.getElementById('loginScreen').style.display = 'none';
        document.getElementById('dashboard').style.display = 'block';

        // Set user info
        document.getElementById('userInfo').textContent = `Welcome, ${this.currentUser.username}`;

        // Setup event listeners
        this.setupEventListeners();

        // Load initial data
        this.loadPersistentSession();
        this.loadSessions();
        this.updateStatus();
        this.loadTalks();

        // Start status polling
        this.statusInterval = setInterval(() => this.updateStatus(), 5000);
    }

    setupEventListeners() {
        // Only add event listeners once to prevent duplicates on re-login
        if (this._dashboardListenersAdded) {
            return;
        }

        document.getElementById('logoutBtn').addEventListener('click', () => this.handleLogout());
        document.getElementById('resetSessionBtn').addEventListener('click', () => this.resetPersistentSession());
        document.getElementById('editSessionNameBtn').addEventListener('click', () => this.editSessionName());
        document.getElementById('startViewerBtn').addEventListener('click', () => this.startViewer());
        document.getElementById('stopViewerBtn').addEventListener('click', () => this.stopViewer());
        document.getElementById('startCaptureBtn').addEventListener('click', () => this.startCapture());
        document.getElementById('stopCaptureBtn').addEventListener('click', () => this.stopCapture());

        // Cleanup on page unload
        window.addEventListener('beforeunload', () => this.cleanup());

        // Session switcher
        document.getElementById('sessionSwitcher').addEventListener('change', (e) => this.switchSession(e.target.value));

        // Refresh talks
        document.getElementById('refreshTalksBtn').addEventListener('click', () => this.loadTalks());

        // Tolerance slider
        const toleranceSlider = document.getElementById('dedupTolerance');
        const toleranceValue = document.getElementById('toleranceValue');
        toleranceSlider.addEventListener('input', (e) => {
            toleranceValue.textContent = e.target.value;
        });

        this._dashboardListenersAdded = true;
    }

    async handleLogin(e) {
        e.preventDefault();

        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;
        const errorEl = document.getElementById('loginError');

        errorEl.textContent = '';
        this.showLoading();

        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username, password})
            });

            const data = await response.json();

            if (data.success) {
                this.authenticated = true;
                this.currentUser = data.user;
                this.showDashboard();
            } else {
                errorEl.textContent = data.message || 'Login failed';
            }
        } catch (error) {
            errorEl.textContent = 'Login failed. Please try again.';
        } finally {
            this.hideLoading();
        }
    }

    async handleLogout() {
        try {
            await fetch('/api/auth/logout', {
                method: 'POST',
                credentials: 'include'
            });
            this.authenticated = false;
            this.currentUser = null;
            clearInterval(this.statusInterval);
            this.showLogin();
        } catch (error) {
            console.error('Logout error:', error);
        }
    }

    async loadPersistentSession() {
        try {
            const response = await fetch('/api/persistent-session', {
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error(`Failed to load persistent session: ${response.status} ${response.statusText}`);
            }

            const data = await response.json();

            document.getElementById('persistentSessionId').textContent = data.session_id;
            document.getElementById('persistentSessionName').textContent = data.session_name;

            // Store current session ID for API operations
            this.currentSessionId = data.session_id;

            // Store cloud session info
            this.cloudEnabled = data.cloud_enabled || false;
            this.cloudSessionId = data.cloud_session_id || null;
            this.cloudApiUrl = data.cloud_api_url || null;

            if (data.cloud_enabled) {
                if (data.cloud_session_id) {
                    document.getElementById('cloudStatus').innerHTML =
                        `<span style="color: #10b981;">✅ Connected</span> - <a href="${data.cloud_viewer_url}" target="_blank">${data.cloud_session_id}</a>`;
                } else {
                    document.getElementById('cloudStatus').innerHTML = '<span style="color: #f59e0b;">⏳ Initializing...</span>';
                }
            } else {
                document.getElementById('cloudStatus').innerHTML = '<span style="color: #6b7280;">Disabled</span>';
            }

            // Load QR code and viewer URL (always available now)
            this.loadViewerInfo();
        } catch (error) {
            console.error('Error loading persistent session:', error);
            document.getElementById('persistentSessionId').textContent = 'Error loading session';
            document.getElementById('persistentSessionName').textContent = error.message || 'Unknown error';
            document.getElementById('cloudStatus').innerHTML = '<span style="color: #ef4444;">❌ Error loading session</span>';
            this.showNotification('Failed to load persistent session: ' + (error.message || 'Unknown error'), 'error');
        }
    }

    resetPersistentSession() {
        this.showConfirm(
            'Start New Session',
            'This will generate a new QR code and viewers will need the new link. Continue?',
            () => this.doResetPersistentSession(),
            'Create New Session',
            'btn-primary'
        );
    }

    async doResetPersistentSession() {
        this.showLoading();
        try {
            const response = await fetch('/api/persistent-session/reset', {
                method: 'POST',
                credentials: 'include'
            });
            const data = await response.json();

            if (data.success) {
                this.showNotification('New session created! QR code updated.', 'success');
                await this.loadPersistentSession();
                await this.loadSessions();
            } else {
                this.showNotification(data.message || 'Failed to create new session', 'error');
            }
        } catch (error) {
            console.error('Reset session error:', error);
            this.showNotification('Failed to create new session', 'error');
        } finally {
            this.hideLoading();
        }
    }

    editSessionName() {
        const currentName = document.getElementById('persistentSessionName').textContent;

        this.showPrompt(
            'Edit Session Name',
            'Enter a new name for this session:',
            currentName,
            (newName) => this.updateSessionName(newName)
        );
    }

    async updateSessionName(newName) {
        const currentName = document.getElementById('persistentSessionName').textContent;
        if (newName === currentName) {
            return; // No change
        }

        this.showLoading();
        try {
            const response = await fetch(`/api/sessions/${this.currentSessionId}`, {
                method: 'PATCH',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: `name=${encodeURIComponent(newName)}`,
                credentials: 'include'
            });

            const data = await response.json();

            if (data.success) {
                this.showNotification('Session name updated successfully!', 'success');
                document.getElementById('persistentSessionName').textContent = newName;
            } else {
                this.showNotification(data.detail || 'Failed to update session name', 'error');
            }
        } catch (error) {
            console.error('Edit session name error:', error);
            this.showNotification('Failed to update session name', 'error');
        } finally {
            this.hideLoading();
        }
    }

    async updateStatus() {
        try {
            // Get capture status
            const captureResp = await fetch('/api/sessions/status', {
                credentials: 'include'
            });
            const captureData = await captureResp.json();

            const captureStatusEl = document.getElementById('captureStatus');
            const captureInfoEl = document.getElementById('captureInfo');

            if (captureData.active) {
                captureStatusEl.textContent = 'Active';
                captureStatusEl.className = 'status-badge active';
                captureInfoEl.innerHTML = `
                    <strong>Session ID:</strong> ${captureData.session_id}<br>
                    <strong>Frames:</strong> ${captureData.stats?.capture?.captures_count || 0}<br>
                    <strong>Slides:</strong> ${captureData.stats?.storage?.slides_stored || 0}
                `;
                document.getElementById('startCaptureBtn').disabled = true;
                document.getElementById('stopCaptureBtn').disabled = false;
            } else {
                captureStatusEl.textContent = 'Inactive';
                captureStatusEl.className = 'status-badge inactive';
                captureInfoEl.textContent = 'No active talk';
                document.getElementById('startCaptureBtn').disabled = false;
                document.getElementById('stopCaptureBtn').disabled = true;
            }

            // Get viewer status
            const viewerResp = await fetch('/api/viewer/status', {
                credentials: 'include'
            });
            const viewerData = await viewerResp.json();

            const viewerStatusEl = document.getElementById('viewerStatus');
            const viewerInfoEl = document.getElementById('viewerInfo');

            if (viewerData.running) {
                viewerStatusEl.textContent = 'Running';
                viewerStatusEl.className = 'status-badge active';
                viewerInfoEl.textContent = `Port: ${viewerData.port}`;
                document.getElementById('startViewerBtn').disabled = true;
                document.getElementById('stopViewerBtn').disabled = false;
            } else {
                viewerStatusEl.textContent = 'Stopped';
                viewerStatusEl.className = 'status-badge inactive';
                viewerInfoEl.textContent = 'Viewer server is not running';
                document.getElementById('startViewerBtn').disabled = false;
                document.getElementById('stopViewerBtn').disabled = true;
            }

            // Note: QR code and viewer URL are now shown in the persistent session section
            // and loaded once on page load, not in the status update loop

        } catch (error) {
            console.error('Status update error:', error);
        }
    }

    async loadViewerInfo() {
        try {
            const urlResp = await fetch('/api/viewer-url', {
                credentials: 'include'
            });
            const urlData = await urlResp.json();

            // Show cloud URL if available, otherwise local URL
            const viewerUrlEl = document.getElementById('viewerUrl');
            if (urlData.cloud_url) {
                viewerUrlEl.innerHTML = `<strong>🌐 Cloud Viewer:</strong> <a href="${urlData.cloud_url}" target="_blank">${urlData.cloud_url}</a><br>` +
                    `<small style="color: #6b7280;">Session ID: ${urlData.cloud_session_id}</small>`;
            } else {
                viewerUrlEl.innerHTML = `<strong>📡 Local Viewer:</strong> ${urlData.local_url}`;
            }

            // Load QR code (points to cloud URL if available, otherwise local)
            const qrImg = document.getElementById('qrCode');
            qrImg.src = '/api/qr?' + new Date().getTime();
            qrImg.style.display = 'block';
            qrImg.onerror = function() {
                console.error('Failed to load QR code');
                this.style.display = 'none';
            };
        } catch (error) {
            console.error('Error loading viewer info:', error);
        }
    }

    async startViewer() {
        this.showLoading();
        try {
            const response = await fetch('/api/viewer/start', {
                method: 'POST',
                credentials: 'include'
            });
            const data = await response.json();

            if (data.success) {
                await this.updateStatus();
                this.showNotification('Viewer server started successfully', 'success');
            } else {
                this.showNotification(data.message || 'Failed to start viewer', 'error');
            }
        } catch (error) {
            this.showNotification('Failed to start viewer server', 'error');
        } finally {
            this.hideLoading();
        }
    }

    stopViewer() {
        this.showConfirm(
            'Stop Viewer Server',
            'Are you sure you want to stop the viewer server? Viewers will lose connection.',
            () => this.doStopViewer(),
            'Stop Server'
        );
    }

    async doStopViewer() {
        this.showLoading();
        try {
            const response = await fetch('/api/viewer/stop', {
                method: 'POST',
                credentials: 'include'
            });
            const data = await response.json();

            if (data.success) {
                await this.updateStatus();
                this.showNotification('Viewer server stopped', 'success');
            } else {
                this.showNotification(data.message || 'Failed to stop viewer', 'error');
            }
        } catch (error) {
            this.showNotification('Failed to stop viewer server', 'error');
        } finally {
            this.hideLoading();
        }
    }

    async startCapture() {
        const name = document.getElementById('talkTitle').value.trim();
        if (!name) {
            this.showNotification('Please enter a talk title', 'error');
            return;
        }

        const presenter = document.getElementById('presenterName').value.trim();
        const description = document.getElementById('talkDescription').value.trim();
        const monitorId = parseInt(document.getElementById('monitorId').value);

        // Convert tolerance to perceptual threshold
        // High tolerance (100) = lenient = low threshold (0.00)
        // Low tolerance (0) = strict = high threshold (1.00)
        const toleranceValue = parseInt(document.getElementById('dedupTolerance').value);
        const dedupTolerance = (100 - toleranceValue) / 100;

        this.showLoading();
        try {
            const response = await fetch('/api/sessions/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name,
                    presenter_name: presenter,
                    description,
                    monitor_id: monitorId,
                    dedup_tolerance: dedupTolerance
                }),
                credentials: 'include'
            });

            if (!response.ok) {
                const errorText = await response.text();
                console.error('Start capture error:', errorText);
                this.showNotification('Failed to start capture: ' + (errorText || 'Unknown error'), 'error');
                return;
            }

            const data = await response.json();

            if (data.success) {
                // Wait a moment for capture to initialize
                await new Promise(resolve => setTimeout(resolve, 1000));
                await this.updateStatus();
                await this.loadSessions();

                // Start cloud talk if cloud enabled
                if (this.cloudEnabled && this.cloudSessionId && this.cloudApiUrl) {
                    try {
                        const cloudResponse = await fetch(`${this.cloudApiUrl}/api/cloud/session/${this.cloudSessionId}/start-talk`, {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({
                                title: name,
                                description: description
                            })
                        });

                        if (cloudResponse.ok) {
                            const cloudData = await cloudResponse.json();
                            console.log('Cloud talk started:', cloudData.talk.talk_id);
                            this.showNotification('Capture and cloud talk started successfully', 'success');
                        } else {
                            console.error('Failed to start cloud talk:', await cloudResponse.text());
                            this.showNotification('Capture started (cloud talk failed)', 'warning');
                        }
                    } catch (cloudError) {
                        console.error('Cloud talk start error:', cloudError);
                        this.showNotification('Capture started (cloud talk error)', 'warning');
                    }
                } else {
                    this.showNotification('Capture session started successfully', 'success');
                }

                // Clear form
                document.getElementById('talkTitle').value = '';
                document.getElementById('presenterName').value = '';
                document.getElementById('talkDescription').value = '';
            } else {
                this.showNotification(data.message || 'Failed to start capture', 'error');
            }
        } catch (error) {
            console.error('Start capture exception:', error);
            // Still check status in case it actually started
            await this.updateStatus();
            this.showNotification('Capture may have started - check status above', 'error');
        } finally {
            this.hideLoading();
        }
    }

    stopCapture() {
        this.showConfirm(
            'Stop Talk',
            'Are you sure you want to stop recording the current talk?',
            () => this.doStopCapture(),
            'Stop Talk'
        );
    }

    async doStopCapture() {
        this.showLoading();
        try {
            const response = await fetch('/api/sessions/stop', {
                method: 'POST',
                credentials: 'include'
            });

            if (!response.ok) {
                const errorText = await response.text();
                console.error('Stop capture error:', errorText);
                this.showNotification('Failed to stop capture: ' + (errorText || 'Unknown error'), 'error');
                return;
            }

            const data = await response.json();

            if (data.success) {
                // End cloud talk if cloud enabled
                if (this.cloudEnabled && this.cloudSessionId && this.cloudApiUrl) {
                    try {
                        const cloudResponse = await fetch(`${this.cloudApiUrl}/api/cloud/session/${this.cloudSessionId}/end-talk`, {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'}
                        });

                        if (cloudResponse.ok) {
                            console.log('Cloud talk ended successfully');
                            this.showNotification('Capture and cloud talk stopped successfully', 'success');
                        } else {
                            console.error('Failed to end cloud talk:', await cloudResponse.text());
                            this.showNotification('Capture stopped (cloud talk end failed)', 'warning');
                        }
                    } catch (cloudError) {
                        console.error('Cloud talk end error:', cloudError);
                        this.showNotification('Capture stopped (cloud talk error)', 'warning');
                    }
                } else {
                    this.showNotification('Capture session stopped successfully', 'success');
                }

                // Wait a moment for cleanup
                await new Promise(resolve => setTimeout(resolve, 500));
                await this.updateStatus();
                await this.loadSessions();
            } else {
                this.showNotification(data.message || 'Failed to stop capture', 'error');
            }
        } catch (error) {
            console.error('Stop capture exception:', error);
            // Still check status
            await this.updateStatus();
            this.showNotification('Error stopping capture - check status above', 'error');
        } finally {
            this.hideLoading();
        }
    }

    async loadSessions() {
        try {
            const response = await fetch('/api/sessions', {
                credentials: 'include'
            });
            this.sessions = await response.json();

            this.populateSessionSwitcher();
        } catch (error) {
            console.error('Error loading sessions:', error);
            this.populateSessionSwitcher();  // Still update switcher even on error
        }
    }

    populateSessionSwitcher() {
        const switcher = document.getElementById('sessionSwitcher');
        const displayEl = document.getElementById('currentSessionDisplay');

        // Update current session display
        // Note: currentSessionId is the persistent session ID, which may not be in the local sessions list
        const currentSession = this.sessions.find(s => s.session_id === this.currentSessionId);
        if (currentSession) {
            displayEl.textContent = `Currently viewing: ${currentSession.name}`;
        } else if (this.currentSessionId) {
            // Show persistent session name if available (when no local sessions match)
            const persistentName = document.getElementById('persistentSessionName').textContent;
            if (persistentName && persistentName !== 'Loading...') {
                displayEl.textContent = `Currently viewing: ${persistentName}`;
            } else {
                displayEl.textContent = 'Current session loaded';
            }
        } else {
            displayEl.textContent = 'No session loaded';
        }

        // Filter out current session - only show other sessions
        const otherSessions = this.sessions.filter(s => s.session_id !== this.currentSessionId);

        if (otherSessions.length === 0) {
            switcher.innerHTML = '<option value="">No other sessions available</option>';
            return;
        }

        // Add "Back to current" option at the top, then other sessions
        const currentName = currentSession ? currentSession.name : 'Current Session';
        switcher.innerHTML = `<option value="${this.currentSessionId}">← Back to ${currentName}</option>` +
            otherSessions.map(session => `
                <option value="${session.session_id}">${session.name}</option>
            `).join('');

        switcher.value = this.currentSessionId;  // Default to current
    }

    async switchSession(sessionId) {
        if (!sessionId) {
            return;
        }

        // Update display
        const session = this.sessions.find(s => s.session_id === sessionId);
        const sessionName = session?.name || sessionId;
        document.getElementById('currentSessionDisplay').textContent = `Currently viewing: ${sessionName}`;

        // Load talks for this session (temporarily switch context)
        const previousSessionId = this.currentSessionId;
        this.currentSessionId = sessionId;
        await this.loadTalks();

        // Update switcher to show "Back to" option for original session
        this.populateSessionSwitcher();
    }

    async loadTalks() {
        if (!this.currentSessionId) {
            return;
        }

        // Show loading state
        const container = document.getElementById('talksList');
        container.innerHTML = '<p class="talks-loading"><span class="spinner-small"></span> Loading talks...</p>';

        try {
            const cloudTalks = await this.loadCloudTalks();
            const localTalks = await this.loadLocalTalks();

            // Union cloud and local talks
            this.talks = this.unionTalks(cloudTalks, localTalks);

            this.renderTalks();
        } catch (error) {
            console.error('Error loading talks:', error);
            container.innerHTML = '<p class="talks-error">Failed to load talks. <button class="btn btn-small btn-secondary" onclick="app.loadTalks()">Retry</button></p>';
            this.showNotification('Error loading talks', 'error');
        }
    }

    async loadCloudTalks() {
        if (!this.cloudApiUrl || !this.currentSessionId) {
            return [];
        }

        try {
            const response = await fetch(`${this.cloudApiUrl}/api/cloud/session/${this.currentSessionId}/talks`);
            if (response.ok) {
                const data = await response.json();
                return data.talks || [];
            }
        } catch (error) {
            console.error('Error loading cloud talks:', error);
        }
        return [];
    }

    async loadLocalTalks() {
        if (!this.currentSessionId) {
            return [];
        }

        try {
            const response = await fetch(`/api/sessions/${this.currentSessionId}/talks`, {
                credentials: 'include'
            });
            if (response.ok) {
                const data = await response.json();
                return (data.talks || []).map(talk => ({
                    ...talk,
                    source: 'local'
                }));
            }
        } catch (error) {
            console.error('Error loading local talks:', error);
        }
        return [];
    }

    unionTalks(cloudTalks, localTalks) {
        const talkMap = new Map();

        // Add cloud talks
        cloudTalks.forEach(talk => {
            const key = talk.title;  // Use title as key for matching
            talkMap.set(key, {
                ...talk,
                source: 'cloud',
                cloudTalkId: talk.talk_id
            });
        });

        // Add or merge local talks
        localTalks.forEach(talk => {
            const key = talk.title;
            if (talkMap.has(key)) {
                // Exists in both - merge them
                const existing = talkMap.get(key);
                existing.source = 'both';
                existing.localTalkId = talk.talk_id;
                // Keep cloud_talk_id from cloud version, add local_talk_id
            } else {
                // Local only
                talkMap.set(key, {
                    ...talk,
                    source: 'local',
                    localTalkId: talk.talk_id
                });
            }
        });

        return Array.from(talkMap.values());
    }

    renderTalks() {
        const container = document.getElementById('talksList');

        if (this.talks.length === 0) {
            container.innerHTML = '<p style="color: #6b7280; text-align: center;">No talks found for this session</p>';
            return;
        }

        container.innerHTML = this.talks.map(talk => {
            const deleteButtons = this.getDeleteButtons(talk);
            return `
                <div class="session-card">
                    <div class="session-header">
                        <div class="session-title">${talk.title}</div>
                        <span class="status-badge" style="background: ${
                            talk.source === 'both' ? '#10b981' :
                            talk.source === 'cloud' ? '#3b82f6' :
                            '#f59e0b'
                        };">${talk.source === 'both' ? 'Both' : talk.source === 'cloud' ? 'Cloud' : 'Local'}</span>
                    </div>
                    <div class="session-meta">
                        <div><strong>Presenter:</strong> ${talk.presenter_name || 'N/A'}</div>
                        <div><strong>Slides:</strong> ${talk.slide_count || 0}</div>
                        ${talk.description ? `<div><strong>Description:</strong> ${talk.description}</div>` : ''}
                    </div>
                    <div class="session-actions">
                        ${deleteButtons}
                    </div>
                </div>
            `;
        }).join('');
    }

    getDeleteButtons(talk) {
        if (talk.source === 'both') {
            return `
                <button class="btn btn-danger btn-small" onclick="app.deleteTalk('local', '${talk.localTalkId}')">Delete from Local</button>
                <button class="btn btn-danger btn-small" onclick="app.deleteTalk('cloud', '${talk.cloudTalkId}')" style="background: #dc2626;">Delete from Cloud</button>
                <button class="btn btn-danger btn-small" onclick="app.deleteTalk('both', '${talk.localTalkId}', '${talk.cloudTalkId}')" style="background: #991b1b;">Delete from Both</button>
            `;
        } else if (talk.source === 'cloud') {
            return `
                <button class="btn btn-danger btn-small" onclick="app.deleteTalk('cloud', '${talk.cloudTalkId}')">Delete from Cloud</button>
            `;
        } else {
            return `
                <button class="btn btn-danger btn-small" onclick="app.deleteTalk('local', '${talk.localTalkId}')">Delete from Local</button>
            `;
        }
    }

    deleteTalk(source, localTalkId, cloudTalkId) {
        const talk = this.talks.find(t => (source === 'local' || source === 'both') ? t.localTalkId === localTalkId : t.cloudTalkId === cloudTalkId);
        if (!talk) return;

        const sourceLabel = source === 'both' ? 'local and cloud storage' : source === 'cloud' ? 'cloud storage' : 'local storage';
        this.showConfirm(
            'Delete Talk',
            `Are you sure you want to delete "${talk.title}" from ${sourceLabel}?`,
            () => this.doDeleteTalk(source, localTalkId, cloudTalkId),
            'Delete'
        );
    }

    async doDeleteTalk(source, localTalkId, cloudTalkId) {
        this.showLoading();
        try {
            const promises = [];

            if (source === 'local' || source === 'both') {
                promises.push(fetch(`/api/sessions/${this.currentSessionId}/talks/${localTalkId}`, {
                    method: 'DELETE',
                    credentials: 'include'
                }));
            }

            if (source === 'cloud' || source === 'both') {
                if (this.cloudApiUrl && cloudTalkId) {
                    promises.push(fetch(`${this.cloudApiUrl}/api/cloud/talk/${cloudTalkId}`, {method: 'DELETE'}));
                }
            }

            await Promise.all(promises);
            await this.loadTalks();
            this.showNotification(`Talk deleted from ${source} successfully`, 'success');
        } catch (error) {
            console.error('Error deleting talk:', error);
            this.showNotification('Error deleting talk', 'error');
        } finally {
            this.hideLoading();
        }
    }

    deleteSession(sessionId) {
        this.showConfirm(
            'Delete Session',
            'Are you sure you want to delete this session? All slides will be permanently deleted.',
            () => this.doDeleteSession(sessionId),
            'Delete Session'
        );
    }

    async doDeleteSession(sessionId) {
        this.showLoading();
        try {
            const response = await fetch(`/api/sessions/${sessionId}`, {
                method: 'DELETE',
                credentials: 'include'
            });
            const data = await response.json();

            if (data.success) {
                await this.loadSessions();
                this.showNotification('Session deleted successfully', 'success');
            } else {
                this.showNotification(data.message || 'Failed to delete session', 'error');
            }
        } catch (error) {
            this.showNotification('Failed to delete session', 'error');
        } finally {
            this.hideLoading();
        }
    }

    deleteCloudSession(sessionId) {
        if (!this.cloudApiUrl) {
            this.showNotification('Cloud API not configured', 'error');
            return;
        }

        this.showConfirm(
            'Delete from Cloud',
            'Are you sure you want to delete this session from the cloud? All slides will be permanently deleted from cloud storage.',
            () => this.doDeleteCloudSession(sessionId),
            'Delete from Cloud'
        );
    }

    async doDeleteCloudSession(sessionId) {
        this.showLoading();
        try {
            const response = await fetch(`${this.cloudApiUrl}/api/cloud/session/${sessionId}`, {
                method: 'DELETE'
            });
            const data = await response.json();

            if (data.success) {
                this.showNotification('Cloud session deleted successfully', 'success');
            } else {
                this.showNotification(data.message || 'Failed to delete cloud session', 'error');
            }
        } catch (error) {
            console.error('Cloud deletion error:', error);
            this.showNotification('Failed to delete cloud session: ' + error.message, 'error');
        } finally {
            this.hideLoading();
        }
    }

    cleanup() {
        // Stop status polling
        if (this.statusInterval) {
            clearInterval(this.statusInterval);
            this.statusInterval = null;
        }
    }

    // Modal methods
    showModal(title, content, actions) {
        const overlay = document.getElementById('modalOverlay');
        document.getElementById('modalTitle').textContent = title;
        document.getElementById('modalContent').innerHTML = content;
        document.getElementById('modalActions').innerHTML = actions;
        overlay.classList.add('active');
    }

    hideModal() {
        document.getElementById('modalOverlay').classList.remove('active');
        this._modalCallback = null;
        this._promptCallback = null;
    }

    showConfirm(title, message, onConfirm, confirmText = 'Confirm', confirmClass = 'btn-danger') {
        // Store callback for later execution
        this._modalCallback = onConfirm;

        const content = `<p>${message}</p>`;
        const actions = `
            <button class="btn btn-secondary" onclick="app.hideModal()">Cancel</button>
            <button class="btn ${confirmClass}" onclick="app.executeModalCallback()">${confirmText}</button>
        `;
        this.showModal(title, content, actions);
    }

    executeModalCallback() {
        const callback = this._modalCallback;
        this.hideModal();
        if (callback) {
            callback();
        }
    }

    showPrompt(title, message, currentValue, onSubmit) {
        // Store callback for later execution
        this._promptCallback = onSubmit;

        const content = `
            <p>${message}</p>
            <input type="text" id="modalPromptInput" value="${currentValue || ''}" placeholder="Enter value...">
        `;
        const actions = `
            <button class="btn btn-secondary" onclick="app.hideModal()">Cancel</button>
            <button class="btn btn-primary" onclick="app.executePromptCallback()">Save</button>
        `;
        this.showModal(title, content, actions);

        // Focus input after modal renders
        setTimeout(() => {
            const input = document.getElementById('modalPromptInput');
            if (input) {
                input.focus();
                input.select();
                // Allow Enter key to submit
                input.addEventListener('keyup', (e) => {
                    if (e.key === 'Enter') {
                        this.executePromptCallback();
                    }
                });
            }
        }, 100);
    }

    executePromptCallback() {
        const input = document.getElementById('modalPromptInput');
        const value = input ? input.value.trim() : '';
        const callback = this._promptCallback;
        this.hideModal();
        if (value && callback) {
            callback(value);
        }
    }

    showLoading() {
        document.getElementById('loadingOverlay').style.display = 'flex';
    }

    hideLoading() {
        document.getElementById('loadingOverlay').style.display = 'none';
    }

    showNotification(message, type = 'info') {
        const container = document.getElementById('toastContainer');

        const icons = {
            success: '✓',
            error: '✕',
            warning: '⚠',
            info: 'ℹ'
        };

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <span class="toast-icon">${icons[type] || icons.info}</span>
            <span class="toast-message">${message}</span>
            <button class="toast-close" onclick="this.parentElement.remove()">×</button>
        `;

        container.appendChild(toast);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (toast.parentElement) {
                toast.classList.add('fade-out');
                setTimeout(() => toast.remove(), 300);
            }
        }, 5000);
    }
}

// Initialize app when DOM is ready
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new AdminApp();
});
