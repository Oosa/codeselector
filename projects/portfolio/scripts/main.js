/**
 * Portfolio site — interaction scripts.
 */

const ANIMATION_DURATION = 300;
const SCROLL_OFFSET = 80;
const DEBOUNCE_DELAY = 150;

// ---------------------------------------------------------------------------
// Utility functions
// ---------------------------------------------------------------------------

function debounce(fn, delay) {
    let timer = null;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

function throttle(fn, limit) {
    let inThrottle = false;
    return function (...args) {
        if (!inThrottle) {
            fn.apply(this, args);
            inThrottle = true;
            setTimeout(() => { inThrottle = false; }, limit);
        }
    };
}

function lerp(a, b, t) {
    return a + (b - a) * t;
}

function clamp(val, min, max) {
    return Math.min(Math.max(val, min), max);
}

function qs(selector, parent = document) {
    return parent.querySelector(selector);
}

function qsAll(selector, parent = document) {
    return Array.from(parent.querySelectorAll(selector));
}

function createElement(tag, classes = [], attrs = {}) {
    const el = document.createElement(tag);
    classes.forEach(c => el.classList.add(c));
    Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
    return el;
}

// ---------------------------------------------------------------------------
// Smooth scroll
// ---------------------------------------------------------------------------

function scrollToSection(targetId) {
    const target = document.getElementById(targetId);
    if (!target) return;
    const top = target.getBoundingClientRect().top + window.scrollY - SCROLL_OFFSET;
    window.scrollTo({ top, behavior: 'smooth' });
}

function initNavLinks() {
    qsAll('[data-scroll-to]').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            scrollToSection(link.dataset.scrollTo);
        });
    });
}

// ---------------------------------------------------------------------------
// Intersection observer — reveal on scroll
// ---------------------------------------------------------------------------

function initRevealAnimations() {
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.15 });

    qsAll('[data-reveal]').forEach(el => observer.observe(el));
}

// ---------------------------------------------------------------------------
// Project filter
// ---------------------------------------------------------------------------

class ProjectFilter {
    constructor(containerId, filterBarId) {
        this.container = qs(`#${containerId}`);
        this.filterBar = qs(`#${filterBarId}`);
        this.projects  = qsAll('.project-card', this.container);
        this.activeTag = 'all';
    }

    init() {
        if (!this.filterBar) return;
        this.filterBar.addEventListener('click', e => {
            const btn = e.target.closest('[data-filter]');
            if (!btn) return;
            this._setActive(btn);
            this._filter(btn.dataset.filter);
        });
    }

    _setActive(btn) {
        qsAll('[data-filter]', this.filterBar).forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.activeTag = btn.dataset.filter;
    }

    _filter(tag) {
        this.projects.forEach(card => {
            const tags = (card.dataset.tags || '').split(',').map(t => t.trim());
            const show = tag === 'all' || tags.includes(tag);
            card.style.display = show ? '' : 'none';
        });
    }

    getActiveTag() {
        return this.activeTag;
    }
}

// ---------------------------------------------------------------------------
// Dark mode toggle
// ---------------------------------------------------------------------------

const darkMode = {
    _key: 'theme',

    init() {
        const saved = localStorage.getItem(this._key);
        if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
            document.documentElement.classList.add('dark');
        }
        qs('#theme-toggle')?.addEventListener('click', () => this.toggle());
    },

    toggle() {
        const isDark = document.documentElement.classList.toggle('dark');
        localStorage.setItem(this._key, isDark ? 'dark' : 'light');
    },

    isDark() {
        return document.documentElement.classList.contains('dark');
    },
};

// ---------------------------------------------------------------------------
// Contact form
// ---------------------------------------------------------------------------

async function submitContactForm(formEl) {
    const data = Object.fromEntries(new FormData(formEl).entries());
    const errors = validateContactForm(data);
    if (errors.length) {
        showFormErrors(formEl, errors);
        return false;
    }
    try {
        const res = await fetch('/api/contact', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!res.ok) throw new Error('Server error');
        showSuccessMessage(formEl);
        formEl.reset();
        return true;
    } catch (err) {
        showFormErrors(formEl, ['Failed to send message. Please try again.']);
        return false;
    }
}

function validateContactForm(data) {
    const errors = [];
    if (!data.name || data.name.trim().length < 2) errors.push('Name is required (min 2 chars)');
    if (!data.email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email)) errors.push('Valid email required');
    if (!data.message || data.message.trim().length < 10) errors.push('Message must be at least 10 characters');
    return errors;
}

function showFormErrors(formEl, errors) {
    const existing = qs('.form-errors', formEl.parentElement);
    if (existing) existing.remove();
    const div = createElement('div', ['form-errors']);
    div.innerHTML = errors.map(e => `<p class="form-error">${e}</p>`).join('');
    formEl.parentElement.insertBefore(div, formEl);
}

function showSuccessMessage(formEl) {
    const msg = createElement('div', ['form-success']);
    msg.textContent = 'Message sent! I will get back to you soon.';
    formEl.parentElement.insertBefore(msg, formEl);
    setTimeout(() => msg.remove(), 5000);
}

// ---------------------------------------------------------------------------
// Typing animation
// ---------------------------------------------------------------------------

class TypeWriter {
    constructor(elementId, phrases, speed = 80) {
        this.el      = document.getElementById(elementId);
        this.phrases = phrases;
        this.speed   = speed;
        this._i      = 0;
        this._j      = 0;
        this._deleting = false;
    }

    start() {
        if (!this.el) return;
        this._tick();
    }

    _tick() {
        const phrase = this.phrases[this._i % this.phrases.length];
        if (this._deleting) {
            this.el.textContent = phrase.slice(0, --this._j);
        } else {
            this.el.textContent = phrase.slice(0, ++this._j);
        }
        let delay = this._deleting ? this.speed / 2 : this.speed;
        if (!this._deleting && this._j === phrase.length) {
            delay = 1500;
            this._deleting = true;
        } else if (this._deleting && this._j === 0) {
            this._deleting = false;
            this._i++;
            delay = 500;
        }
        setTimeout(() => this._tick(), delay);
    }
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    initNavLinks();
    initRevealAnimations();
    darkMode.init();

    const filter = new ProjectFilter('projects-grid', 'project-filter-bar');
    filter.init();

    const tw = new TypeWriter('hero-typewriter', ['Full-Stack Developer', 'UI Enthusiast', 'Open Source Contributor']);
    tw.start();

    qs('#contact-form')?.addEventListener('submit', async e => {
        e.preventDefault();
        await submitContactForm(e.target);
    });
});
