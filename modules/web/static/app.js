// SeenSlide Cloud Viewer JavaScript

class SeenSlideClient {
    constructor() {
        this.ws = null;
        this.currentSession = null;
        this.slides = [];
        this.currentSlideIndex = 0;
        this.init();
    }

    init() {
        // Set up event listeners
        document.getElementById('session-select').addEventListener('change', (e) => {
            this.loadSession(e.target.value);
        });

        document.getElementById('refresh-sessions').addEventListener('click', () => {
            this.loadSessions();
        });

        document.getElementById('prev-slide').addEventListener('click', () => {
            this.previousSlide();
        });

        document.getElementById('next-slide').addEventListener('click', () => {
            this.nextSlide();
        });

        // Fullscreen button
        document.getElementById('btn-fullscreen').addEventListener('click', () => {
            this.toggleFullscreen();
        });

        // Theme toggle button
        document.getElementById('theme-toggle').addEventListener('click', () => {
            this.toggleTheme();
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
                e.preventDefault();
                this.previousSlide();
            } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
                e.preventDefault();
                this.nextSlide();
            } else if (e.key.toLowerCase() === 'f') {
                e.preventDefault();
                this.toggleFullscreen();
            }
        });

        // Initial load
        this.loadSessions();
        this.connectWebSocket();
    }

    toggleTheme() {
        const html = document.documentElement;
        const currentTheme = html.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        html.setAttribute('data-theme', newTheme);
    }

    async toggleFullscreen() {
        const slideFrame = document.getElementById('slide-frame');
        try {
            if (!document.fullscreenElement) {
                await slideFrame.requestFullscreen();
            } else {
                await document.exitFullscreen();
            }
        } catch (e) {
            console.error('Fullscreen not available:', e);
        }
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/events`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.updateConnectionStatus(true);
        };

        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
            this.updateConnectionStatus(false);
            // Attempt to reconnect after 5 seconds
            setTimeout(() => this.connectWebSocket(), 5000);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleWebSocketMessage(data);
        };

        // Send ping every 30 seconds to keep connection alive
        setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send('ping');
            }
        }, 30000);
    }

    updateConnectionStatus(connected) {
        const statusElement = document.getElementById('connection-status');
        const dotElement = document.getElementById('connection-dot');

        if (connected) {
            statusElement.textContent = 'Connected';
            dotElement.className = 'dot ok';
        } else {
            statusElement.textContent = 'Disconnected';
            dotElement.className = 'dot bad';
        }
    }

    handleWebSocketMessage(message) {
        console.log('Received WebSocket message:', message);

        // Handle different event types
        switch (message.type) {
            case 'slide.stored':
                if (this.currentSession && message.data.session_id === this.currentSession.session_id) {
                    // NEW: Don't reload slides and auto-jump to first slide
                    // Just update the thumbnail list quietly
                    this.loadSlidesQuietly(this.currentSession.session_id);
                }
                break;
            case 'session.created':
            case 'session.started':
            case 'session.stopped':
                // Reload sessions list
                this.loadSessions();
                break;
            default:
                console.log('Unhandled event type:', message.type);
        }
    }

    async loadSessions() {
        try {
            const response = await fetch('/api/sessions/');
            const sessions = await response.json();

            const select = document.getElementById('session-select');
            const currentValue = select.value;
            select.innerHTML = '<option value="">Select a session...</option>';

            sessions.forEach(session => {
                const option = document.createElement('option');
                option.value = session.session_id;
                option.textContent = `${session.name} (${session.total_slides} slides)`;
                select.appendChild(option);
            });

            // Restore previous selection if it exists
            if (currentValue) {
                select.value = currentValue;
            }
        } catch (error) {
            console.error('Error loading sessions:', error);
        }
    }

    async loadSession(sessionId) {
        if (!sessionId) {
            document.getElementById('session-info').style.display = 'none';
            return;
        }

        try {
            const response = await fetch(`/api/sessions/${sessionId}`);
            this.currentSession = await response.json();

            // Update session info
            document.getElementById('session-name').textContent = this.currentSession.name;
            document.getElementById('session-description').textContent = this.currentSession.description || 'No description';
            document.getElementById('session-presenter').textContent = this.currentSession.presenter_name || 'Unknown';
            document.getElementById('session-status').textContent = this.currentSession.status;
            document.getElementById('session-info').style.display = 'block';

            // Load slides
            await this.loadSlides(sessionId);
        } catch (error) {
            console.error('Error loading session:', error);
        }
    }

    async loadSlides(sessionId) {
        try {
            const response = await fetch(`/api/slides/${sessionId}`);
            this.slides = await response.json();

            // Update slide count
            document.getElementById('session-slide-count').textContent = this.slides.length;
            document.getElementById('total-slides').textContent = this.slides.length;

            // Render thumbnails
            this.renderThumbnails();

            // Show first slide (initial load only)
            if (this.slides.length > 0) {
                this.currentSlideIndex = 0;
                this.showSlide(0);
            }
        } catch (error) {
            console.error('Error loading slides:', error);
        }
    }

    async loadSlidesQuietly(sessionId) {
        // Load slides but DON'T auto-jump to first slide
        // Only update thumbnails if user is viewing a different slide
        try {
            const response = await fetch(`/api/slides/${sessionId}`);
            const newSlides = await response.json();

            // Check if new slides were added
            const hadNewSlides = newSlides.length > this.slides.length;
            this.slides = newSlides;

            // Update slide count
            document.getElementById('session-slide-count').textContent = this.slides.length;
            document.getElementById('total-slides').textContent = this.slides.length;

            // Re-render thumbnails to show new slides
            this.renderThumbnails();

            // DON'T call showSlide() - let user stay on current slide
            // Just update the current slide index if it's out of bounds
            if (this.currentSlideIndex >= this.slides.length) {
                this.currentSlideIndex = Math.max(0, this.slides.length - 1);
                this.showSlide(this.currentSlideIndex);
            }

            if (hadNewSlides) {
                console.log(`New slides added. Total: ${this.slides.length}. Staying on slide ${this.currentSlideIndex + 1}.`);
            }
        } catch (error) {
            console.error('Error loading slides quietly:', error);
        }
    }

    renderThumbnails() {
        const container = document.getElementById('thumbnail-container');

        if (this.slides.length === 0) {
            container.innerHTML = '<p class="no-slides-message">No slides available</p>';
            return;
        }

        container.innerHTML = '';

        this.slides.forEach((slide, index) => {
            const item = document.createElement('div');
            item.className = 'thumb-item';
            if (index === this.currentSlideIndex) {
                item.classList.add('active');
            }

            const img = document.createElement('img');
            img.src = `/api/slides/thumbnail/${slide.slide_id}`;
            img.alt = `Slide ${slide.sequence_number}`;
            img.loading = 'lazy'; // Lazy load thumbnails for performance

            const label = document.createElement('div');
            label.className = 'thumb-label';
            label.textContent = `Slide ${slide.sequence_number}`;

            item.appendChild(img);
            item.appendChild(label);
            item.addEventListener('click', () => this.showSlide(index));

            container.appendChild(item);
        });
    }

    showSlide(index) {
        if (index < 0 || index >= this.slides.length) {
            return;
        }

        this.currentSlideIndex = index;
        const slide = this.slides[index];

        // Update current slide display
        const display = document.getElementById('current-slide-display');
        display.innerHTML = '';

        const img = document.createElement('img');
        img.src = `/api/slides/image/${slide.slide_id}`;
        img.alt = `Slide ${slide.sequence_number}`;
        display.appendChild(img);

        // Update slide number
        document.getElementById('current-slide-number').textContent = slide.sequence_number;

        // Update button states
        document.getElementById('prev-slide').disabled = (index === 0);
        document.getElementById('next-slide').disabled = (index === this.slides.length - 1);

        // Update thumbnail selection
        const thumbnails = document.querySelectorAll('.thumb-item');
        thumbnails.forEach((item, i) => {
            if (i === index) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });

        // Scroll thumbnail into view
        if (thumbnails[index]) {
            thumbnails[index].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }

    previousSlide() {
        this.showSlide(this.currentSlideIndex - 1);
    }

    nextSlide() {
        this.showSlide(this.currentSlideIndex + 1);
    }
}

// Initialize client when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new SeenSlideClient();
});
