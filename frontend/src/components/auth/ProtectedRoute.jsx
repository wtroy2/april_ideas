import { useContext } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { ClipLoader } from 'react-spinners';
import { AuthContext } from '../../context/AuthContext';

/**
 * Wraps protected routes.
 *  - If not authenticated → redirect to /login (with redirect= back-link).
 *  - If authenticated but no org and requireOrg=true → redirect to /setup.
 *  - Otherwise render children.
 */
export default function ProtectedRoute({ children, requireOrg = true }) {
  const { isAuthenticated, authLoading, organizationStatus, orgStatusLoading } = useContext(AuthContext);
  const location = useLocation();

  if (authLoading) {
    return (
      <div className="d-flex justify-content-center align-items-center" style={{ minHeight: '50vh' }}>
        <ClipLoader color="#2563eb" />
      </div>
    );
  }

  if (!isAuthenticated) {
    const redirect = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?redirect=${redirect}`} replace />;
  }

  if (requireOrg) {
    if (orgStatusLoading) {
      return (
        <div className="d-flex justify-content-center align-items-center" style={{ minHeight: '50vh' }}>
          <ClipLoader color="#2563eb" />
        </div>
      );
    }
    if (!organizationStatus.hasOrganization) {
      return <Navigate to="/setup" replace />;
    }
  }

  return children;
}
