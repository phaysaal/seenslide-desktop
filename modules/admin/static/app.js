/**
 * SeenSlide Admin Application
 * Handles authentication, session management, and server controls
 */

class AdminApp {
    constructor() {
        this.authenticated = false;
        this.currentUser = null;
        this.sessions = [];
        this.statusInterval = null;
        this.cloudEnabled = false;
        this.cloudSessionId = null;
        this.cloudApiUrl = null;

        this.init();
    }

    async init() {
        // Check if already authenticated
        try {
            const response = await fetch('/api/auth/me');
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

        const form = document.getElementById('loginForm');
        form.addEventListener('submit', (e) => this.handleLogin(e));
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

        // Start status polling
        this.statusInterval = setInterval(() => this.updateStatus(), 5000);
    }

    setupEventListeners() {
        document.getElementById('logoutBtn').addEventListener('click', () => this.handleLogout());
        document.getElementById('resetSessionBtn').addEventListener('click', () => this.resetPersistentSession());
        document.getElementById('startViewerBtn').addEventListener('click', () => this.startViewer());
        document.getElementById('stopViewerBtn').addEventListener('click', () => this.stopViewer());
        document.getElementById('startCaptureBtn').addEventListener('click', () => this.startCapture());
        document.getElementById('stopCaptureBtn').addEventListener('click', () => this.stopCapture());
        document.getElementById('refreshSessionsBtn').addEventListener('click', () => this.loadSessions());

        // Tolerance slider
        const toleranceSlider = document.getElementById('dedupTolerance');
        const toleranceValue = document.getElementById('toleranceValue');
        toleranceSlider.addEventListener('input', (e) => {
            toleranceValue.textContent = e.target.value;
        });
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
            await fetch('/api/auth/logout', {method: 'POST'});
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
            const response = await fetch('/api/persistent-session');
            const data = await response.json();

            document.getElementById('persistentSessionId').textContent = data.session_id;
            document.getElementById('persistentSessionName').textContent = data.session_name;

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
            document.getElementById('cloudStatus').innerHTML = '<span style="color: #ef4444;">❌ Error</span>';
        }
    }

    async resetPersistentSession() {
        if (!confirm('Are you sure you want to reset the session ID? This will generate a new QR code and viewers will need the new link.')) {
            return;
        }

        this.showLoading();
        try {
            const response = await fetch('/api/persistent-session/reset', {method: 'POST'});
            const data = await response.json();

            if (data.success) {
                this.showNotification('Session ID reset successfully! New QR code generated.', 'success');
                await this.loadPersistentSession();
            } else {
                this.showNotification(data.message || 'Failed to reset session ID', 'error');
            }
        } catch (error) {
            console.error('Reset session error:', error);
            this.showNotification('Failed to reset session ID', 'error');
        } finally {
            this.hideLoading();
        }
    }

    async updateStatus() {
        try {
            // Get capture status
            const captureResp = await fetch('/api/sessions/status');
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
                captureInfoEl.textContent = 'No active capture session';
                document.getElementById('startCaptureBtn').disabled = false;
                document.getElementById('stopCaptureBtn').disabled = true;
            }

            // Get viewer status
            const viewerResp = await fetch('/api/viewer/status');
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
            const urlResp = await fetch('/api/viewer-url');
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
            const response = await fetch('/api/viewer/start', {method: 'POST'});
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

    async stopViewer() {
        if (!confirm('Are you sure you want to stop the viewer server?')) return;

        this.showLoading();
        try {
            const response = await fetch('/api/viewer/stop', {method: 'POST'});
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
        const name = document.getElementById('sessionName').value.trim();
        if (!name) {
            alert('Please enter a session name');
            return;
        }

        const presenter = document.getElementById('presenterName').value.trim();
        const description = document.getElementById('sessionDescription').value.trim();
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
                })
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
                document.getElementById('sessionName').value = '';
                document.getElementById('presenterName').value = '';
                document.getElementById('sessionDescription').value = '';
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

    async stopCapture() {
        if (!confirm('Are you sure you want to stop the capture session?')) return;

        this.showLoading();
        try {
            const response = await fetch('/api/sessions/stop', {method: 'POST'});

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
            const response = await fetch('/api/sessions');
            this.sessions = await response.json();

            this.renderSessions();
        } catch (error) {
            console.error('Error loading sessions:', error);
        }
    }

    renderSessions() {
        const container = document.getElementById('sessionsList');

        if (this.sessions.length === 0) {
            container.innerHTML = '<p style="color: #6b7280; text-align: center;">No sessions found</p>';
            return;
        }

        container.innerHTML = this.sessions.map(session => `
            <div class="session-card ${session.is_active ? 'active' : ''}">
                <div class="session-header">
                    <div class="session-title">${session.name}</div>
                    ${session.is_active ? '<span class="status-badge active">Active</span>' : ''}
                </div>
                <div class="session-meta">
                    <div><strong>Presenter:</strong> ${session.presenter_name || 'N/A'}</div>
                    <div><strong>Slides:</strong> ${session.slide_count}</div>
                    <div><strong>Status:</strong> ${session.status}</div>
                    <div><strong>Started:</strong> ${session.start_time ? new Date(session.start_time).toLocaleString() : 'N/A'}</div>
                </div>
                ${session.description ? `<p style="color: #6b7280; margin-bottom: 12px;">${session.description}</p>` : ''}
                <div class="session-actions">
                    ${!session.is_active ? `
                        <button class="btn btn-danger btn-small" onclick="app.deleteSession('${session.session_id}')">Delete Local</button>
                        <button class="btn btn-danger btn-small" onclick="app.deleteCloudSession('${session.session_id}')" style="background: #dc2626;">Delete from Cloud</button>
                    ` : ''}
                </div>
            </div>
        `).join('');
    }

    async deleteSession(sessionId) {
        if (!confirm('Are you sure you want to delete this session? All slides will be permanently deleted.')) return;

        this.showLoading();
        try {
            const response = await fetch(`/api/sessions/${sessionId}`, {method: 'DELETE'});
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

    async deleteCloudSession(sessionId) {
        if (!confirm('Are you sure you want to delete this session from the cloud? All slides will be permanently deleted from cloud storage.')) return;

        this.showLoading();
        try {
            // Get cloud URL from viewer info
            const cloudApiUrl = 'https://web-production-2b06f.up.railway.app';
            const response = await fetch(`${cloudApiUrl}/api/cloud/session/${sessionId}`, {
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

    showLoading() {
        document.getElementById('loadingOverlay').style.display = 'flex';
    }

    hideLoading() {
        document.getElementById('loadingOverlay').style.display = 'none';
    }

    showNotification(message, type = 'info') {
        alert(message);
    }
}

// Initialize app when DOM is ready
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new AdminApp();
});
