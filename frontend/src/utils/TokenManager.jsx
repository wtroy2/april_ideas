// TokenManager — singleton that manages access + refresh tokens with debouncing.
// Lifted from RateRail (frontend/src/utils/TokenManager.jsx) with no functional changes.

import { jwtDecode } from 'jwt-decode';
import { ACCESS_TOKEN, REFRESH_TOKEN } from '../constants';

class TokenManager {
  constructor() {
    this.isRefreshing = false;
    this.refreshPromise = null;
    this.subscribers = [];
    this.baseURL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
  }

  getAccessToken() {
    return localStorage.getItem(ACCESS_TOKEN);
  }

  getRefreshToken() {
    return localStorage.getItem(REFRESH_TOKEN);
  }

  setTokens(accessToken, refreshToken = null) {
    if (accessToken) localStorage.setItem(ACCESS_TOKEN, accessToken);
    if (refreshToken) localStorage.setItem(REFRESH_TOKEN, refreshToken);
  }

  clearTokens() {
    localStorage.removeItem(ACCESS_TOKEN);
    localStorage.removeItem(REFRESH_TOKEN);
  }

  isAccessTokenValid() {
    const token = this.getAccessToken();
    if (!token) return false;
    try {
      const decoded = jwtDecode(token);
      return decoded.exp > Date.now() / 1000;
    } catch {
      return false;
    }
  }

  isRefreshTokenValid() {
    const token = this.getRefreshToken();
    if (!token) return false;
    try {
      const decoded = jwtDecode(token);
      return decoded.exp > Date.now() / 1000;
    } catch {
      return false;
    }
  }

  getTimeUntilExpiry() {
    const token = this.getAccessToken();
    if (!token) return 0;
    try {
      const decoded = jwtDecode(token);
      return Math.max(0, Math.floor(decoded.exp - Date.now() / 1000));
    } catch {
      return 0;
    }
  }

  subscribeToRefresh(callback) {
    this.subscribers.push(callback);
    return () => {
      this.subscribers = this.subscribers.filter((cb) => cb !== callback);
    };
  }

  notifySubscribers(success, token = null, error = null) {
    this.subscribers.forEach((cb) => {
      try { cb(success, token, error); } catch (e) { console.error(e); }
    });
  }

  async refreshAccessToken() {
    if (this.isRefreshing && this.refreshPromise) {
      return this.refreshPromise;
    }

    const refreshToken = this.getRefreshToken();
    if (!refreshToken) {
      const err = new Error('No refresh token available');
      this.notifySubscribers(false, null, err);
      throw err;
    }
    if (!this.isRefreshTokenValid()) {
      const err = new Error('Refresh token expired');
      err.code = 'token_expired';
      this.notifySubscribers(false, null, err);
      throw err;
    }

    this.isRefreshing = true;
    this.refreshPromise = this.performTokenRefresh(refreshToken);
    try {
      const result = await this.refreshPromise;
      this.notifySubscribers(true, result.access);
      return result;
    } catch (e) {
      this.notifySubscribers(false, null, e);
      throw e;
    } finally {
      this.isRefreshing = false;
      this.refreshPromise = null;
    }
  }

  async performTokenRefresh(refreshToken) {
    const url = `${this.baseURL}/api/users/token/refresh/`;
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: refreshToken }),
    });
    if (!res.ok) {
      const err = new Error(`Refresh failed: ${res.status}`);
      err.status = res.status;
      if (res.status === 401) this.clearTokens();
      throw err;
    }
    const data = await res.json();
    if (!data.access) throw new Error('No access token in refresh response');
    this.setTokens(data.access, data.refresh);
    return data;
  }

  async getValidAccessToken() {
    if (this.isAccessTokenValid()) return this.getAccessToken();
    const result = await this.refreshAccessToken();
    return result.access;
  }
}

const tokenManager = new TokenManager();
export default tokenManager;
