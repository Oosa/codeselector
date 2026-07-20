/**
 * API client module — fetch wrappers with auth and error handling.
 */

const BASE_URL = '/api/v1';
const DEFAULT_TIMEOUT_MS = 8000;

let _authToken = null;

function setAuthToken(token) {
    _authToken = token;
}

function getAuthToken() {
    return _authToken;
}

function buildHeaders(extra = {}) {
    const headers = { 'Content-Type': 'application/json', ...extra };
    if (_authToken) headers['Authorization'] = `Bearer ${_authToken}`;
    return headers;
}

async function request(method, path, body = null, options = {}) {
    const url = `${BASE_URL}${path}`;
    const headers = buildHeaders(options.headers || {});
    const config = { method, headers };
    if (body) config.body = JSON.stringify(body);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

    try {
        const response = await fetch(url, { ...config, signal: controller.signal });
        clearTimeout(timeoutId);
        if (!response.ok) {
            const err = await response.json().catch(() => ({ message: response.statusText }));
            throw new ApiError(response.status, err.message || 'Request failed');
        }
        return response.json();
    } catch (err) {
        clearTimeout(timeoutId);
        if (err.name === 'AbortError') throw new ApiError(408, 'Request timed out');
        throw err;
    }
}

const get    = (path, opts)       => request('GET',    path, null, opts);
const post   = (path, body, opts) => request('POST',   path, body, opts);
const put    = (path, body, opts) => request('PUT',    path, body, opts);
const patch  = (path, body, opts) => request('PATCH',  path, body, opts);
const del    = (path, opts)       => request('DELETE', path, null, opts);

class ApiError extends Error {
    constructor(status, message) {
        super(message);
        this.status = status;
        this.name = 'ApiError';
    }

    isUnauthorised() { return this.status === 401; }
    isForbidden()    { return this.status === 403; }
    isNotFound()     { return this.status === 404; }
    isServerError()  { return this.status >= 500; }
}

class ProductApi {
    static async getAll(page = 1, pageSize = 20) {
        return get(`/products?page=${page}&page_size=${pageSize}`);
    }

    static async getById(id) {
        return get(`/products/${id}`);
    }

    static async search(query, filters = {}) {
        const params = new URLSearchParams({ q: query, ...filters });
        return get(`/products/search?${params}`);
    }

    static async create(data) {
        return post('/products', data);
    }

    static async update(id, data) {
        return patch(`/products/${id}`, data);
    }

    static async remove(id) {
        return del(`/products/${id}`);
    }
}

class OrderApi {
    static async create(orderData) {
        return post('/orders', orderData);
    }

    static async getById(id) {
        return get(`/orders/${id}`);
    }

    static async listForUser() {
        return get('/orders/me');
    }

    static async cancel(id) {
        return post(`/orders/${id}/cancel`);
    }
}

class AuthApi {
    static async login(email, password) {
        return post('/auth/login', { email, password });
    }

    static async logout() {
        return post('/auth/logout');
    }

    static async refreshToken(token) {
        return post('/auth/refresh', { token });
    }

    static async register(email, password, name) {
        return post('/auth/register', { email, password, name });
    }
}

export { ApiError, ProductApi, OrderApi, AuthApi, setAuthToken, getAuthToken, get, post, put, patch, del };
