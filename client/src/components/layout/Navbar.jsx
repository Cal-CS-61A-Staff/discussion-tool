import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext.jsx';
import { isStaff } from '../../utils/roles.js';

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <nav className="navbar">
      <div className="container navbar-inner">
        <NavLink to="/" className="navbar-brand">
          CS 61A <span>Discussion</span>
        </NavLink>
        <div className="navbar-nav">
          <NavLink to="/" className={({ isActive }) => (isActive ? 'active' : '')} end>
            Home
          </NavLink>
          {isStaff(user) && (
            <NavLink to="/discussions" className={({ isActive }) => (isActive ? 'active' : '')}>
              Rooms
            </NavLink>
          )}
          {user && (
            <NavLink to="/assignments" className={({ isActive }) => (isActive ? 'active' : '')}>
              Assignments
            </NavLink>
          )}
          {user?.role === 'admin' && (
            <NavLink to="/admin" className={({ isActive }) => (isActive ? 'active' : '')}>
              Admin
            </NavLink>
          )}
        </div>
        {user && (
          <div className="navbar-user">
            <span className="navbar-user-name">{user.display_name}</span>
            <span className="navbar-user-role">{user.role}</span>
            <button className="btn btn-outline btn-sm" onClick={handleLogout}>
              Sign out
            </button>
          </div>
        )}
      </div>
    </nav>
  );
}
