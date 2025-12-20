// SeenSlide Web Client JavaScript

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

        // Initial load
        this.loadSessions();
        this.connectWebSocket();
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
        if (connected) {
            statusElement.textContent = 'Connected';
            statusElement.className = 'status-indicator connected';
        } else {
            statusElement.textContent = 'Disconnected';
            statusElement.className = 'status-indicator disconnected';
        }
    }

    handleWebSocketMessage(message) {
        console.log('Received WebSocket message:', message);

        // Handle different event types
        switch (message.type) {
            case 'slide.stored':
                if (this.currentSession && message.data.session_id === this.currentSession.session_id) {
                    // Reload slides when new slide is stored
                    this.loadSlides(this.currentSession.session_id);
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
            select.innerHTML = '<option value="">Select a session...</option>';

            sessions.forEach(session => {
                const option = document.createElement('option');
                option.value = session.session_id;
                option.textContent = `${session.name} (${session.total_slides} slides)`;
                select.appendChild(option);
            });
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

            // Show first slide
            if (this.slides.length > 0) {
                this.currentSlideIndex = 0;
                this.showSlide(0);
            }
        } catch (error) {
            console.error('Error loading slides:', error);
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
            item.className = 'thumbnail-item';
            if (index === this.currentSlideIndex) {
                item.classList.add('active');
            }

            const img = document.createElement('img');
            img.src = `/api/slides/thumbnail/${slide.slide_id}`;
            img.alt = `Slide ${slide.sequence_number}`;

            const label = document.createElement('div');
            label.className = 'thumbnail-label';
            label.textContent = `#${slide.sequence_number}`;

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
        const thumbnails = document.querySelectorAll('.thumbnail-item');
        thumbnails.forEach((item, i) => {
            if (i === index) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
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
