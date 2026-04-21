// AuthContext — lifted from RateRail and trimmed for Critter's needs.
// Owns: auth state, current user, current org status, proactive session refresh,
// logout event listener.

import { createContext, useEffect, useState, useCallback, useRef } from 'react';
import tokenManager from '../utils/TokenManager';
import api, { isOnPublicPage } from '../api';

export const AuthContext = createContext(null);

const DEFAULT_ORG_STATUS = {
  hasOrganization: false,
  isActive: false,
  needsSetup: false,
  canInviteMembers: false,
  userRole: null,
  organizationId: null,
  organizationName: null,
  organizationType: null,
  isOnTrial: false,
  quota: null,
};

export function AuthProvider({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState('');
  const [firstname, setFirstname] = useState('');
  const [organizationStatus, setOrganizationStatus] = useState(DEFAULT_ORG_STATUS);
  const [authLoading, setAuthLoading] = useState(true);
  const [orgStatusLoading, setOrgStatusLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);
  const isHandlingExpiry = useRef(false);

  const logout = useCallback((reason = 'manual') => {
    tokenManager.clearTokens();
    setIsAuthenticated(false);
    setUsername('');
    setFirstname('');
    setOrganizationStatus(DEFAULT_ORG_STATUS);
    setOrgStatusLoading(false);
    if (reason.includes('expired') || reason.includes('token')) {
      setSessionExpired(true);
    }
  }, []);

  // Proactive session refresh
  useEffect(() => {
    if (!isAuthenticated) return;

    const SESSION_CHECK_INTERVAL = 30_000;
    const PRE_EXPIRY_REFRESH_BUFFER = 120;

    const check = async () => {
      if (isHandlingExpiry.current) return;
      const accessValid = tokenManager.isAccessTokenValid();
      const refreshValid = tokenManager.isRefreshTokenValid();

      if (!accessValid && !refreshValid) {
        isHandlingExpiry.current = true;
        logout('session_expired');
        if (!isOnPublicPage(window.location.pathname)) {
          const redirect = encodeURIComponent(window.location.pathname);
          window.location.href = `/login?reason=session_expired&redirect=${redirect}`;
        }
        return;
      }

      if ((!accessValid || tokenManager.getTimeUntilExpiry() < PRE_EXPIRY_REFRESH_BUFFER) && refreshValid) {
        try {
          await tokenManager.refreshAccessToken();
        } catch {
          if (!tokenManager.isRefreshTokenValid()) {
            isHandlingExpiry.current = true;
            logout('session_expired');
          }
        }
      }
    };

    check();
    const id = setInterval(check, SESSION_CHECK_INTERVAL);
    const onVisible = () => { if (document.visibilityState === 'visible') check(); };
    const onFocus = () => check();
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onFocus);
    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onFocus);
    };
  }, [isAuthenticated, logout]);

  useEffect(() => {
    if (isAuthenticated) isHandlingExpiry.current = false;
  }, [isAuthenticated]);

  const checkAuth = useCallback(async () => {
    try {
      if (!tokenManager.getAccessToken() && !tokenManager.getRefreshToken()) {
        setIsAuthenticated(false);
        setAuthLoading(false);
        setOrgStatusLoading(false);
        return;
      }
      if (tokenManager.isAccessTokenValid()) {
        setIsAuthenticated(true);
        setAuthLoading(false);
        return;
      }
      if (tokenManager.isRefreshTokenValid()) {
        try {
          await tokenManager.refreshAccessToken();
          setIsAuthenticated(true);
        } catch {
          logout('token_refresh_failed');
        }
      } else {
        logout('tokens_expired');
      }
    } catch {
      logout('auth_check_error');
    }
    setAuthLoading(false);
  }, [logout]);

  const fetchUsername = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const res = await api.get('/api/users/get_username/');
      setUsername(res.data.username);
      setFirstname(res.data.user_firstname);
    } catch (err) {
      if (err.response?.status === 401) logout('api_unauthorized');
    }
  }, [isAuthenticated, logout]);

  const checkOrganizationStatus = useCallback(async () => {
    if (!isAuthenticated) {
      setOrgStatusLoading(false);
      return;
    }
    setOrgStatusLoading(true);
    try {
      const orgRes = await api.get('/api/orgs/my/');
      const orgs = orgRes.data;

      if (!orgs || orgs.length === 0) {
        setOrganizationStatus({ ...DEFAULT_ORG_STATUS, needsSetup: true });
        setOrgStatusLoading(false);
        return;
      }

      const org = orgs[0];

      // Pull billing info
      let quota = null;
      let isOnTrial = false;
      let isActive = true;
      try {
        const b = await api.get('/api/billing/my/');
        quota = {
          quota: b.data.monthly_generation_quota,
          used: b.data.generations_used_this_period,
          remaining: Math.max(0, b.data.monthly_generation_quota - b.data.generations_used_this_period),
        };
        isOnTrial = !!b.data.is_trial;
        isActive = !!b.data.is_active;
      } catch (e) {
        // Billing not critical — keep defaults
      }

      setOrganizationStatus({
        hasOrganization: true,
        isActive,
        needsSetup: false,
        canInviteMembers: org.your_role === 'admin' && isActive,
        userRole: org.your_role,
        organizationId: org.id,
        organizationName: org.name,
        organizationType: org.org_type,
        isOnTrial,
        quota,
      });
    } catch (err) {
      setOrganizationStatus({ ...DEFAULT_ORG_STATUS, needsSetup: true });
      if (err.response?.status === 401) logout('api_unauthorized');
    }
    setOrgStatusLoading(false);
  }, [isAuthenticated, logout]);

  // Logout event listener (api.js dispatches these)
  useEffect(() => {
    const onLogout = (event) => logout(event.detail?.reason || 'unknown');
    window.addEventListener('logout', onLogout);
    return () => window.removeEventListener('logout', onLogout);
  }, [logout]);

  // Init
  useEffect(() => { checkAuth(); }, [checkAuth]);
  useEffect(() => {
    if (isAuthenticated && !authLoading) {
      const t = setTimeout(() => {
        fetchUsername();
        checkOrganizationStatus();
      }, 100);
      return () => clearTimeout(t);
    }
  }, [isAuthenticated, authLoading, fetchUsername, checkOrganizationStatus]);
  useEffect(() => {
    if (isAuthenticated && sessionExpired) setSessionExpired(false);
  }, [isAuthenticated, sessionExpired]);

  const value = {
    isAuthenticated,
    username,
    firstname,
    authLoading,
    orgStatusLoading,
    sessionExpired,
    organizationStatus,
    setIsAuthenticated,
    fetchUsername,
    checkOrganizationStatus,
    logout,
    checkAuth,
    isAdmin: () => organizationStatus.userRole === 'admin',
    isEditor: () => ['admin', 'editor'].includes(organizationStatus.userRole),
    tokenManager,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
