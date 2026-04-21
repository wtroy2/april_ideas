import { useContext } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { LogOut, Sparkles } from 'lucide-react';
import { AuthContext } from '../context/AuthContext';
import api from '../api';
import tokenManager from '../utils/TokenManager';

export default function MainLayout() {
  const { username, organizationStatus, logout } = useContext(AuthContext);
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      const refresh = tokenManager.getRefreshToken();
      await api.post('/api/users/auth/logout/', { refresh });
    } catch {
      // best-effort
    }
    logout('manual');
    navigate('/login');
  };

  return (
    <div className="critter-shell">
      <nav className="critter-nav">
        <div className="d-flex align-items-center gap-3">
          <NavLink to="/" className="critter-nav-brand d-flex align-items-center gap-2">
            <Sparkles size={20} /> Critter
          </NavLink>
          <div className="critter-nav-links d-none d-md-flex">
            <NavLink to="/" end className={({ isActive }) => `critter-nav-link ${isActive ? 'active' : ''}`}>
              Dashboard
            </NavLink>
            <NavLink to="/subjects" className={({ isActive }) => `critter-nav-link ${isActive ? 'active' : ''}`}>
              Pets
            </NavLink>
            <NavLink to="/themes" className={({ isActive }) => `critter-nav-link ${isActive ? 'active' : ''}`}>
              Themes
            </NavLink>
            <NavLink to="/music" className={({ isActive }) => `critter-nav-link ${isActive ? 'active' : ''}`}>
              Music
            </NavLink>
            <NavLink to="/generate" className={({ isActive }) => `critter-nav-link ${isActive ? 'active' : ''}`}>
              Generate
            </NavLink>
            <NavLink to="/stories" className={({ isActive }) => `critter-nav-link ${isActive ? 'active' : ''}`}>
              Stories
            </NavLink>
            <NavLink to="/generations" className={({ isActive }) => `critter-nav-link ${isActive ? 'active' : ''}`}>
              History
            </NavLink>
          </div>
        </div>
        <div className="d-flex align-items-center gap-3">
          {organizationStatus.quota && (
            <small className="text-muted d-none d-sm-inline">
              {organizationStatus.quota.used}/{organizationStatus.quota.quota} videos this month
            </small>
          )}
          <small className="text-muted d-none d-sm-inline">{username}</small>
          <button onClick={handleLogout} className="btn btn-sm btn-outline-secondary d-flex align-items-center gap-1">
            <LogOut size={14} /> Sign out
          </button>
        </div>
      </nav>
      <div className="critter-page flex-grow-1">
        <Outlet />
      </div>
    </div>
  );
}
