// Centralized axios client with JWT interceptors and auto-refresh.
// Lifted from RateRail (frontend/src/api.js) with the auth-endpoint list trimmed
// to match Critter's narrower auth surface.

import axios from 'axios';
import tokenManager from './utils/TokenManager';

export const BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

const api = axios.create({ baseURL: BASE_URL });

const AUTH_ENDPOINTS = [
  'users/auth/initiate-login',
  'users/auth/verify-login',
  'users/auth/resend-code',
  'users/auth/forgot-username',
  'users/auth/forgot-password',
  'users/auth/verify-password-reset',
  'users/auth/resend-password-reset',
  'users/register',
  'users/token',
];

const isAuthEndpoint = (url) => {
  if (!url) return false;
  const normalized = url.replace(/^\/?(api\/)?/, '');
  return AUTH_ENDPOINTS.some((e) => normalized.includes(e));
};

const isPublicEndpoint = (url) => {
  if (!url) return false;
  const normalized = url.replace(/^\/?(api\/)?/, '');
  return normalized.startsWith('orgs/invitations/');
};

const PUBLIC_PAGE_PREFIXES = ['/login', '/register', '/forgot-password', '/forgot-username'];
const isOnPublicPage = (path) => PUBLIC_PAGE_PREFIXES.some((p) => path.startsWith(p));

api.interceptors.request.use(
  (config) => {
    if (!isPublicEndpoint(config.url)) {
      const token = tokenManager.getAccessToken();
      if (token && tokenManager.isAccessTokenValid()) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  },
  (err) => Promise.reject(err),
);

api.interceptors.response.use(
  (resp) => resp,
  async (error) => {
    const originalRequest = error.config;

    if (isAuthEndpoint(originalRequest.url) || isPublicEndpoint(originalRequest.url)) {
      return Promise.reject(error);
    }
    if (originalRequest._retry) return Promise.reject(error);

    if (error.response?.status === 401) {
      originalRequest._retry = true;
      try {
        const newToken = await tokenManager.getValidAccessToken();
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return api(originalRequest);
      } catch (refreshError) {
        handleLogout('token_refresh_failed');
        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  },
);

const handleLogout = (reason = 'unknown') => {
  tokenManager.clearTokens();
  window.dispatchEvent(new CustomEvent('logout', { detail: { reason } }));

  const path = window.location.pathname;
  if (isOnPublicPage(path)) return;

  const redirect = `&redirect=${encodeURIComponent(path)}`;
  if (reason === 'token_refresh_failed' || reason === 'session_expired') {
    window.location.href = `/login?reason=session_expired${redirect}`;
  } else {
    window.location.href = `/login?redirect=${encodeURIComponent(path)}`;
  }
};

export { handleLogout, isOnPublicPage };
export default api;
