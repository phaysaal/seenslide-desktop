/**
 * SeenSlide Viewer - Client Application
 * Handles slide viewing, navigation, and real-time updates
 */

class SlideViewer {
    constructor() {
        this.currentSession = null;
        this.currentSlide = 1;
        this.totalSlides = 0;
        this.slides = [];
        this.websocket = null;
        this.liveMode = true;
        this.refreshInterval = null;
        this.lastSlideCount = 0;

        // Initialize
        this.init();
    }

    async init() {
        // Setup event listeners
        this.setupEventListeners();

        // Load sessions
        await this.loadSessions();

        // Setup keyboard shortcuts
        this.setupKeyboardShortcuts();
    }

    setupEventListeners() {
        // Session selection
        document.getElementById('sessionSelect').addEventListener('change', (e) => {
            this.selectSession(e.target.value);
        });

        // Navigation buttons
        document.getElementById('firstBtn').addEventListener('click', () => this.goToSlide(1));
        document.getElementById('prevBtn').addEventListener('click', () => this.previousSlide());
        document.getElementById('nextBtn').addEventListener('click', () => this.nextSlide());
        document.getElementById('lastBtn').addEventListener('click', () => this.goToSlide(this.totalSlides));
        document.getElementById('liveBtn').addEventListener('click', () => this.toggleLiveMode());
        document.getElementById('fullscreenBtn').addEventListener('click', () => this.toggleFullscreen());

        // Slide input
        document.getElementById('slideInput').addEventListener('change', (e) => {
            const slideNum = parseInt(e.target.value);
            if (slideNum >= 1 && slideNum <= this.totalSlides) {
                this.goToSlide(slideNum);
            } else {
                e.target.value = this.currentSlide;
            }
        });

        // Allow Enter key in slide input
        document.getElementById('slideInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.target.blur();
            }
        });
    }

    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ignore if typing in input field
            if (e.target.tagName === 'INPUT') return;

            switch(e.key) {
                case 'ArrowLeft':
                case 'PageUp':
                    e.preventDefault();
                    this.previousSlide();
                    break;
                case 'ArrowRight':
                case 'PageDown':
                case ' ':
                    e.preventDefault();
                    this.nextSlide();
                    break;
                case 'Home':
                    e.preventDefault();
                    this.goToSlide(1);
                    break;
                case 'End':
                    e.preventDefault();
                    this.goToSlide(this.totalSlides);
                    break;
                case 'l':
                case 'L':
                    this.toggleLiveMode();
                    break;
                case 'f':
                case 'F':
                    this.toggleFullscreen();
                    break;
                case 'Escape':
                    if (document.fullscreenElement) {
                        this.exitFullscreen();
                    }
                    break;
            }
        });
    }

    async loadSessions() {
        this.showLoading();
        try {
            const response = await fetch('/api/sessions');
            const sessions = await response.json();

            const select = document.getElementById('sessionSelect');
            select.innerHTML = '<option value="">Select a session...</option>';

            sessions.forEach(session => {
                const option = document.createElement('option');
                option.value = session.session_id;
                option.textContent = `${session.name} (${session.slide_count} slides)`;
                select.appendChild(option);
            });

            // Auto-select last (most recent) session if available
            if (sessions.length > 0) {
                // Sessions are returned in desc order by start_time, so first is most recent
                const lastSession = sessions[0];
                select.value = lastSession.session_id;
                await this.selectSession(lastSession.session_id);
            }
        } catch (error) {
            console.error('Error loading sessions:', error);
            this.showError('Failed to load sessions');
        } finally {
            this.hideLoading();
        }
    }

    async selectSession(sessionId) {
        if (!sessionId) return;

        this.currentSession = sessionId;
        this.currentSlide = 1;

        // Close existing websocket
        if (this.websocket) {
            this.websocket.close();
        }

        // Load session details and slides
        await this.loadSessionDetails();
        await this.loadSlides();

        // Setup WebSocket for real-time updates
        this.connectWebSocket();

        // Always go to latest slide on initial load
        if (this.totalSlides > 0) {
            this.goToSlide(this.totalSlides);
            // Enable live mode by default
            this.liveMode = true;
            document.getElementById('liveBtn').classList.add('active');
        }

        // Start auto-refresh interval (check for new slides every 5 seconds)
        this.startAutoRefresh();
    }

    async loadSessionDetails() {
        try {
            const response = await fetch(`/api/sessions/${this.currentSession}`);
            const session = await response.json();

            document.getElementById('sessionName').textContent = session.name || 'Untitled';
            this.totalSlides = session.slide_count;
            this.lastSlideCount = session.slide_count; // Initialize for auto-refresh
            document.getElementById('totalSlides').textContent = this.totalSlides;
            document.getElementById('slideInput').max = this.totalSlides;
        } catch (error) {
            console.error('Error loading session details:', error);
        }
    }

    async loadSlides() {
        this.showLoading();
        try {
            const response = await fetch(`/api/sessions/${this.currentSession}/slides?limit=1000`);
            this.slides = await response.json();

            // Update total slides count
            this.totalSlides = this.slides.length;
            document.getElementById('totalSlides').textContent = this.totalSlides;
            document.getElementById('slideInput').max = this.totalSlides;

            // Load thumbnails
            this.loadThumbnails();

            // Display first slide
            if (this.slides.length > 0) {
                this.displaySlide(1);
            }
        } catch (error) {
            console.error('Error loading slides:', error);
            this.showError('Failed to load slides');
        } finally {
            this.hideLoading();
        }
    }

    loadThumbnails() {
        const grid = document.getElementById('thumbnailGrid');
        grid.innerHTML = '';

        this.slides.forEach((slide, index) => {
            const item = document.createElement('div');
            item.className = 'thumbnail-item';
            item.dataset.slideNumber = index + 1;

            const img = document.createElement('img');
            const filename = slide.thumbnail_path ? slide.thumbnail_path.split('/').pop() : slide.image_path.split('/').pop();
            img.src = `/api/images/${this.currentSession}/${filename}`;
            img.alt = `Slide ${slide.sequence_number}`;

            const number = document.createElement('div');
            number.className = 'thumbnail-number';
            number.textContent = slide.sequence_number;

            item.appendChild(img);
            item.appendChild(number);

            item.addEventListener('click', () => {
                this.goToSlide(parseInt(item.dataset.slideNumber));
            });

            grid.appendChild(item);
        });
    }

    displaySlide(slideNumber) {
        if (slideNumber < 1 || slideNumber > this.totalSlides) return;

        this.currentSlide = slideNumber;
        const slide = this.slides[slideNumber - 1];

        if (!slide) return;

        // Update slide image
        const container = document.getElementById('slideContainer');
        container.innerHTML = '';

        const img = document.createElement('img');
        const filename = slide.image_path.split('/').pop();
        img.src = `/api/images/${this.currentSession}/${filename}`;
        img.alt = `Slide ${slide.sequence_number}`;

        // Add zoom functionality
        this.setupZoom(container, img);

        container.appendChild(img);

        // Update info
        const timestamp = new Date(slide.timestamp * 1000).toLocaleString();
        document.getElementById('slideTimestamp').textContent = timestamp;
        document.getElementById('slideDimensions').textContent = `${slide.width}x${slide.height}`;
        document.getElementById('slideInput').value = slideNumber;

        // Update thumbnail selection
        document.querySelectorAll('.thumbnail-item').forEach(item => {
            item.classList.remove('active');
            if (parseInt(item.dataset.slideNumber) === slideNumber) {
                item.classList.add('active');
                item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        });

        // Update navigation buttons
        this.updateNavigationButtons();

        // If not on last slide, disable live mode
        if (slideNumber < this.totalSlides) {
            this.liveMode = false;
            document.getElementById('liveBtn').classList.remove('active');
        }
    }

    setupZoom(container, img) {
        let scale = 1;
        let panning = false;
        let pointX = 0;
        let pointY = 0;
        let start = { x: 0, y: 0 };

        // Mouse wheel zoom
        container.addEventListener('wheel', (e) => {
            e.preventDefault();

            const delta = e.deltaY > 0 ? 0.9 : 1.1;
            const newScale = scale * delta;

            // Limit zoom between 1x and 5x
            if (newScale >= 1 && newScale <= 5) {
                scale = newScale;
                img.style.transform = `scale(${scale}) translate(${pointX}px, ${pointY}px)`;

                if (scale > 1) {
                    container.classList.add('zoomed');
                } else {
                    container.classList.remove('zoomed');
                    pointX = 0;
                    pointY = 0;
                }
            }
        });

        // Mouse drag for panning
        img.addEventListener('mousedown', (e) => {
            if (scale > 1) {
                e.preventDefault();
                start = { x: e.clientX - pointX, y: e.clientY - pointY };
                panning = true;
            }
        });

        document.addEventListener('mousemove', (e) => {
            if (!panning) return;
            e.preventDefault();

            pointX = e.clientX - start.x;
            pointY = e.clientY - start.y;
            img.style.transform = `scale(${scale}) translate(${pointX}px, ${pointY}px)`;
        });

        document.addEventListener('mouseup', () => {
            panning = false;
        });

        // Touch pinch zoom and pan
        let initialDistance = 0;
        let initialScale = 1;

        img.addEventListener('touchstart', (e) => {
            if (e.touches.length === 2) {
                e.preventDefault();
                initialDistance = this.getDistance(e.touches[0], e.touches[1]);
                initialScale = scale;
            } else if (e.touches.length === 1 && scale > 1) {
                start = {
                    x: e.touches[0].clientX - pointX,
                    y: e.touches[0].clientY - pointY
                };
                panning = true;
            }
        });

        img.addEventListener('touchmove', (e) => {
            if (e.touches.length === 2) {
                e.preventDefault();
                const distance = this.getDistance(e.touches[0], e.touches[1]);
                const newScale = initialScale * (distance / initialDistance);

                if (newScale >= 1 && newScale <= 5) {
                    scale = newScale;
                    img.style.transform = `scale(${scale}) translate(${pointX}px, ${pointY}px)`;

                    if (scale > 1) {
                        container.classList.add('zoomed');
                    } else {
                        container.classList.remove('zoomed');
                        pointX = 0;
                        pointY = 0;
                    }
                }
            } else if (e.touches.length === 1 && panning) {
                e.preventDefault();
                pointX = e.touches[0].clientX - start.x;
                pointY = e.touches[0].clientY - start.y;
                img.style.transform = `scale(${scale}) translate(${pointX}px, ${pointY}px)`;
            }
        });

        img.addEventListener('touchend', (e) => {
            if (e.touches.length < 2) {
                panning = false;
            }
        });

        // Double-click/tap to reset zoom
        let lastTap = 0;
        img.addEventListener('dblclick', () => {
            scale = 1;
            pointX = 0;
            pointY = 0;
            img.style.transform = `scale(1)`;
            container.classList.remove('zoomed');
        });

        img.addEventListener('touchend', (e) => {
            const currentTime = new Date().getTime();
            const tapLength = currentTime - lastTap;
            if (tapLength < 300 && tapLength > 0) {
                scale = 1;
                pointX = 0;
                pointY = 0;
                img.style.transform = `scale(1)`;
                container.classList.remove('zoomed');
            }
            lastTap = currentTime;
        });
    }

    getDistance(touch1, touch2) {
        const dx = touch1.clientX - touch2.clientX;
        const dy = touch1.clientY - touch2.clientY;
        return Math.sqrt(dx * dx + dy * dy);
    }

    updateNavigationButtons() {
        document.getElementById('firstBtn').disabled = this.currentSlide === 1;
        document.getElementById('prevBtn').disabled = this.currentSlide === 1;
        document.getElementById('nextBtn').disabled = this.currentSlide === this.totalSlides;
        document.getElementById('lastBtn').disabled = this.currentSlide === this.totalSlides;
    }

    goToSlide(slideNumber) {
        this.displaySlide(slideNumber);
    }

    previousSlide() {
        if (this.currentSlide > 1) {
            this.goToSlide(this.currentSlide - 1);
        }
    }

    nextSlide() {
        if (this.currentSlide < this.totalSlides) {
            this.goToSlide(this.currentSlide + 1);
        }
    }

    toggleLiveMode() {
        this.liveMode = !this.liveMode;
        const btn = document.getElementById('liveBtn');

        if (this.liveMode) {
            btn.classList.add('active');
            btn.textContent = 'LIVE';
            this.goToSlide(this.totalSlides);
        } else {
            btn.classList.remove('active');
            btn.textContent = 'LIVE';
        }
    }

    connectWebSocket() {
        if (!this.currentSession) return;

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/session/${this.currentSession}`;

        this.websocket = new WebSocket(wsUrl);

        this.websocket.onopen = () => {
            console.log('WebSocket connected');
            this.updateConnectionStatus(true);
        };

        this.websocket.onclose = () => {
            console.log('WebSocket disconnected');
            this.updateConnectionStatus(false);

            // Attempt to reconnect after 3 seconds
            setTimeout(() => {
                if (this.currentSession) {
                    this.connectWebSocket();
                }
            }, 3000);
        };

        this.websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        this.websocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleWebSocketMessage(data);
        };
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'connected':
                console.log('WebSocket connected to session:', data.session_id);
                break;

            case 'new_slide':
                console.log('New slide received:', data.slide);
                this.handleNewSlide(data.slide);
                break;

            case 'pong':
                // Heartbeat response
                break;

            default:
                console.log('Unknown message type:', data.type);
        }
    }

    async handleNewSlide(slideData) {
        // Reload slides to get the new one
        await this.loadSlides();

        // If in live mode, jump to the new slide
        if (this.liveMode) {
            this.goToSlide(this.totalSlides);
        }

        // Show notification
        this.showNotification('New slide captured!');
    }

    updateConnectionStatus(connected) {
        const status = document.getElementById('connectionStatus');
        if (connected) {
            status.classList.remove('disconnected');
            status.classList.add('connected');
        } else {
            status.classList.remove('connected');
            status.classList.add('disconnected');
        }
    }

    showLoading() {
        document.getElementById('loadingOverlay').style.display = 'flex';
    }

    hideLoading() {
        document.getElementById('loadingOverlay').style.display = 'none';
    }

    showError(message) {
        // Simple error display - could be enhanced with a modal
        alert(`Error: ${message}`);
    }

    showNotification(message) {
        // Simple notification - could be enhanced with a toast notification
        console.log('Notification:', message);
    }

    toggleFullscreen() {
        if (!document.fullscreenElement) {
            const container = document.querySelector('.main-content');
            if (container.requestFullscreen) {
                container.requestFullscreen();
            } else if (container.webkitRequestFullscreen) {
                container.webkitRequestFullscreen();
            } else if (container.msRequestFullscreen) {
                container.msRequestFullscreen();
            }

            // Show fullscreen overlay controls
            this.showFullscreenControls();
        } else {
            this.exitFullscreen();
        }
    }

    exitFullscreen() {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        } else if (document.webkitExitFullscreen) {
            document.webkitExitFullscreen();
        } else if (document.msExitFullscreen) {
            document.msExitFullscreen();
        }

        // Hide fullscreen overlay controls
        this.hideFullscreenControls();
    }

    showFullscreenControls() {
        let overlay = document.getElementById('fullscreenOverlay');
        if (!overlay) {
            // Create fullscreen overlay controls
            overlay = document.createElement('div');
            overlay.id = 'fullscreenOverlay';
            overlay.className = 'fullscreen-overlay';
            overlay.innerHTML = `
                <button class="fullscreen-nav-btn fullscreen-nav-left" id="fsPrevBtn">◀</button>
                <button class="fullscreen-nav-btn fullscreen-nav-right" id="fsNextBtn">▶</button>
                <button class="fullscreen-exit-btn" id="fsExitBtn">✕</button>
            `;
            document.querySelector('.main-content').appendChild(overlay);

            // Add event listeners
            document.getElementById('fsPrevBtn').addEventListener('click', () => this.previousSlide());
            document.getElementById('fsNextBtn').addEventListener('click', () => this.nextSlide());
            document.getElementById('fsExitBtn').addEventListener('click', () => this.exitFullscreen());
        }

        overlay.style.display = 'block';

        // Auto-hide controls after 3 seconds of no mouse movement
        let hideTimeout;
        const resetHideTimeout = () => {
            clearTimeout(hideTimeout);
            overlay.style.opacity = '1';
            hideTimeout = setTimeout(() => {
                overlay.style.opacity = '0';
            }, 3000);
        };

        document.addEventListener('mousemove', resetHideTimeout);
        resetHideTimeout();
    }

    hideFullscreenControls() {
        const overlay = document.getElementById('fullscreenOverlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
    }

    startAutoRefresh() {
        // Stop any existing refresh interval
        this.stopAutoRefresh();

        // Check for new slides every 5 seconds
        this.refreshInterval = setInterval(async () => {
            if (!this.currentSession) return;

            try {
                // Get current session info to check slide count
                const response = await fetch(`/api/sessions/${this.currentSession}`);
                const session = await response.json();

                // If slide count increased, fetch only new slides
                if (session.slide_count > this.lastSlideCount) {
                    console.log(`New slides detected: ${this.lastSlideCount} -> ${session.slide_count}`);

                    // Remember current slide before update
                    const wasViewingSlide = this.currentSlide;

                    // Fetch new slides
                    await this.loadNewSlides();

                    this.lastSlideCount = session.slide_count;

                    // If in live mode, jump to latest slide
                    if (this.liveMode && this.totalSlides > 0) {
                        this.goToSlide(this.totalSlides);
                        this.showNotification('New slide available!');
                    } else {
                        // Stay on the current slide
                        this.displaySlide(wasViewingSlide);
                    }
                }
            } catch (error) {
                console.error('Auto-refresh error:', error);
            }
        }, 5000); // 5 seconds

        console.log('Auto-refresh started');
    }

    async loadNewSlides() {
        // Fetch all slides (including new ones)
        try {
            const response = await fetch(`/api/sessions/${this.currentSession}/slides?limit=1000`);
            const newSlides = await response.json();

            // Only add new slides to the array
            const oldCount = this.slides.length;
            this.slides = newSlides;
            this.totalSlides = newSlides.length;

            // Update UI counts
            document.getElementById('totalSlides').textContent = this.totalSlides;
            document.getElementById('slideInput').max = this.totalSlides;

            // Add only new thumbnails
            const grid = document.getElementById('thumbnailGrid');
            for (let i = oldCount; i < newSlides.length; i++) {
                const slide = newSlides[i];
                const item = document.createElement('div');
                item.className = 'thumbnail-item';
                item.dataset.slideNumber = i + 1;

                const img = document.createElement('img');
                const filename = slide.thumbnail_path ? slide.thumbnail_path.split('/').pop() : slide.image_path.split('/').pop();
                img.src = `/api/images/${this.currentSession}/${filename}`;
                img.alt = `Slide ${slide.sequence_number}`;

                const number = document.createElement('div');
                number.className = 'thumbnail-number';
                number.textContent = slide.sequence_number;

                item.appendChild(img);
                item.appendChild(number);

                item.addEventListener('click', () => {
                    this.goToSlide(parseInt(item.dataset.slideNumber));
                });

                grid.appendChild(item);
            }

            console.log(`Added ${newSlides.length - oldCount} new thumbnails`);
        } catch (error) {
            console.error('Error loading new slides:', error);
        }
    }

    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
            console.log('Auto-refresh stopped');
        }
    }
}

// Initialize the viewer when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.slideViewer = new SlideViewer();
});

// Heartbeat to keep WebSocket alive
setInterval(() => {
    if (window.slideViewer && window.slideViewer.websocket && window.slideViewer.websocket.readyState === WebSocket.OPEN) {
        window.slideViewer.websocket.send('ping');
    }
}, 30000);
