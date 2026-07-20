/**
 * CMS default theme — JavaScript interactions.
 */

const MOBILE_BREAKPOINT = 768;
const STICKY_HEADER_OFFSET = 100;

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

class Navigation {
    constructor() {
        this.header   = document.querySelector('.site-header');
        this.menuBtn  = document.querySelector('.menu-toggle');
        this.mobileNav = document.querySelector('.mobile-nav');
        this._lastScrollY = 0;
        this._isOpen = false;
    }

    init() {
        this._initSticky();
        this._initMobileMenu();
        this._initDropdowns();
    }

    _initSticky() {
        const onScroll = throttleNav(() => {
            const y = window.scrollY;
            if (this.header) {
                this.header.classList.toggle('sticky', y > STICKY_HEADER_OFFSET);
                this.header.classList.toggle('hidden', y > this._lastScrollY && y > 200);
            }
            this._lastScrollY = y;
        }, 50);
        window.addEventListener('scroll', onScroll, { passive: true });
    }

    _initMobileMenu() {
        this.menuBtn?.addEventListener('click', () => this._toggleMenu());
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape' && this._isOpen) this._closeMenu();
        });
    }

    _initDropdowns() {
        document.querySelectorAll('.has-dropdown').forEach(item => {
            item.addEventListener('mouseenter', () => this._openDropdown(item));
            item.addEventListener('mouseleave', () => this._closeDropdown(item));
        });
    }

    _toggleMenu() {
        this._isOpen ? this._closeMenu() : this._openMenu();
    }

    _openMenu() {
        this._isOpen = true;
        this.mobileNav?.classList.add('open');
        this.menuBtn?.setAttribute('aria-expanded', 'true');
        document.body.style.overflow = 'hidden';
    }

    _closeMenu() {
        this._isOpen = false;
        this.mobileNav?.classList.remove('open');
        this.menuBtn?.setAttribute('aria-expanded', 'false');
        document.body.style.overflow = '';
    }

    _openDropdown(item) {
        item.querySelector('.dropdown')?.classList.add('visible');
    }

    _closeDropdown(item) {
        item.querySelector('.dropdown')?.classList.remove('visible');
    }
}

// ---------------------------------------------------------------------------
// Image lazy loading
// ---------------------------------------------------------------------------

class LazyLoader {
    constructor(selector = '[data-lazy]') {
        this.selector = selector;
        this.observer = null;
    }

    init() {
        if (!('IntersectionObserver' in window)) {
            this._loadAll();
            return;
        }
        this.observer = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    this._loadImage(entry.target);
                    this.observer.unobserve(entry.target);
                }
            });
        }, { rootMargin: '200px' });

        document.querySelectorAll(this.selector).forEach(el => this.observer.observe(el));
    }

    _loadImage(el) {
        const src = el.dataset.lazy;
        if (!src) return;
        if (el.tagName === 'IMG') {
            el.src = src;
            el.removeAttribute('data-lazy');
            el.classList.add('loaded');
        } else {
            el.style.backgroundImage = `url(${src})`;
            el.removeAttribute('data-lazy');
        }
    }

    _loadAll() {
        document.querySelectorAll(this.selector).forEach(el => this._loadImage(el));
    }
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

class SearchWidget {
    constructor(inputId, resultsId) {
        this.input   = document.getElementById(inputId);
        this.results = document.getElementById(resultsId);
        this._cache  = new Map();
        this._timer  = null;
    }

    init() {
        this.input?.addEventListener('input', () => {
            clearTimeout(this._timer);
            this._timer = setTimeout(() => this._search(this.input.value), 300);
        });

        document.addEventListener('click', e => {
            if (!this.results?.contains(e.target) && e.target !== this.input) {
                this._hideResults();
            }
        });
    }

    async _search(query) {
        const q = query.trim();
        if (q.length < 2) { this._hideResults(); return; }

        if (this._cache.has(q)) {
            this._renderResults(this._cache.get(q));
            return;
        }

        try {
            const data = await fetch(`/api/search?q=${encodeURIComponent(q)}`).then(r => r.json());
            this._cache.set(q, data.results);
            this._renderResults(data.results);
        } catch {
            this._renderError();
        }
    }

    _renderResults(items) {
        if (!this.results) return;
        if (!items.length) {
            this.results.innerHTML = '<p class="no-results">No results found.</p>';
        } else {
            this.results.innerHTML = items
                .map(item => `<a class="search-result-item" href="${item.url}">
                    <strong>${item.title}</strong>
                    <span>${item.excerpt}</span>
                </a>`).join('');
        }
        this.results.classList.add('visible');
    }

    _renderError() {
        if (this.results) {
            this.results.innerHTML = '<p class="search-error">Search unavailable.</p>';
            this.results.classList.add('visible');
        }
    }

    _hideResults() {
        this.results?.classList.remove('visible');
    }

    clearCache() {
        this._cache.clear();
    }
}

// ---------------------------------------------------------------------------
// Comments
// ---------------------------------------------------------------------------

class CommentForm {
    constructor(formId) {
        this.form = document.getElementById(formId);
        this._submitting = false;
    }

    init() {
        this.form?.addEventListener('submit', e => {
            e.preventDefault();
            if (!this._submitting) this._submit();
        });
    }

    async _submit() {
        this._submitting = true;
        this._setLoading(true);
        const data = Object.fromEntries(new FormData(this.form).entries());
        try {
            const res = await fetch('/api/comments', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
            if (!res.ok) throw new Error();
            this._showSuccess();
            this.form.reset();
        } catch {
            this._showError('Failed to submit comment. Please try again.');
        } finally {
            this._submitting = false;
            this._setLoading(false);
        }
    }

    _setLoading(state) {
        const btn = this.form?.querySelector('[type="submit"]');
        if (btn) { btn.disabled = state; btn.textContent = state ? 'Sending…' : 'Post comment'; }
    }

    _showSuccess() {
        const msg = document.createElement('p');
        msg.className = 'comment-success';
        msg.textContent = 'Comment submitted and awaiting moderation.';
        this.form.parentElement?.insertBefore(msg, this.form);
    }

    _showError(text) {
        const msg = document.createElement('p');
        msg.className = 'comment-error';
        msg.textContent = text;
        this.form.parentElement?.insertBefore(msg, this.form);
    }
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function throttleNav(fn, limit) {
    let last = 0;
    return function (...args) {
        const now = Date.now();
        if (now - last >= limit) { last = now; fn.apply(this, args); }
    };
}

function formatDate(isoString) {
    return new Date(isoString).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
}

function copyToClipboard(text) {
    return navigator.clipboard.writeText(text);
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    new Navigation().init();
    new LazyLoader().init();
    new SearchWidget('search-input', 'search-results').init();
    new CommentForm('comment-form').init();
});
