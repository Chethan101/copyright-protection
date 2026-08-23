import { BrowserRouter as Router, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import Login from './pages/Login';
import Register from './pages/Register';
import Feed from './pages/Feed';
import Upload from './pages/Upload';
import Notifications from './pages/Notifications';
import Profile from './pages/Profile';
import Saved from './pages/Saved';
import './index.css';

function Sidebar({ onUpload }: { onUpload: () => void }) {
  const location = useLocation();
  const navigate = useNavigate();
  const username = localStorage.getItem('social_username') || 'me';

  const logout = () => {
    localStorage.removeItem('social_token');
    localStorage.removeItem('social_username');
    localStorage.removeItem('social_user_id');
    window.location.href = '/login';
  };

  const active = (path: string) => location.pathname === path ? 'nav-item active' : 'nav-item';

  return (
    <div className="sidebar">
      <div className="sidebar-logo">VibeSocial</div>
      <nav className="sidebar-nav">
        <button className={active('/feed')} onClick={() => navigate('/feed')}>
          <svg viewBox="0 0 24 24" fill={location.pathname === '/feed' ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
          Home
        </button>

        <button className="nav-item" onClick={() => {}}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          Search
        </button>

        <button className="nav-item" onClick={onUpload}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
          Create
        </button>

        <button className={active('/notifications')} onClick={() => navigate('/notifications')}>
          <svg viewBox="0 0 24 24" fill={location.pathname === '/notifications' ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
          Notifications
        </button>

        <button className={active('/saved')} onClick={() => navigate('/saved')}>
          <svg viewBox="0 0 24 24" fill={location.pathname === '/saved' ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
          Saved
        </button>

        <button className={active(`/profile/${username}`)} onClick={() => navigate(`/profile/${username}`)}>
          <div className="avatar" style={{ width: 26, height: 26, fontSize: 12 }}>{username[0]?.toUpperCase()}</div>
          Profile
        </button>
      </nav>

      <div className="sidebar-footer">
        <button className="nav-item" onClick={logout}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
          Log out
        </button>
      </div>
    </div>
  );
}

function MobileNav({ onUpload }: { onUpload: () => void }) {
  const navigate = useNavigate();
  const username = localStorage.getItem('social_username') || 'me';
  return (
    <div className="mobile-nav">
      <button className="mobile-nav-btn" onClick={() => navigate('/feed')}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
      </button>
      <button className="mobile-nav-btn" onClick={onUpload}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
      </button>
      <button className="mobile-nav-btn" onClick={() => navigate('/notifications')}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
      </button>
      <button className="mobile-nav-btn" onClick={() => navigate(`/profile/${username}`)}>
        <div className="avatar" style={{ width: 26, height: 26, fontSize: 12 }}>{username[0]?.toUpperCase()}</div>
      </button>
    </div>
  );
}

function AppShell() {
  const token = localStorage.getItem('social_token');
  const [showUpload, setShowUpload] = useState(false);
  const location = useLocation();
  const isAuthPage = ['/login', '/register', '/'].includes(location.pathname);

  return (
    <div className="app-layout">
      {token && !isAuthPage && <Sidebar onUpload={() => setShowUpload(true)} />}
      <div className="main-content" style={isAuthPage ? { marginLeft: 0, maxWidth: '100%' } : {}}>
        <Routes>
          <Route path="/" element={token ? <Navigate to="/feed" /> : <Navigate to="/login" />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/feed" element={token ? <Feed onOpenUpload={() => setShowUpload(true)} /> : <Navigate to="/login" />} />
          <Route path="/notifications" element={token ? <Notifications /> : <Navigate to="/login" />} />
          <Route path="/saved" element={token ? <Saved /> : <Navigate to="/login" />} />
          <Route path="/profile/:username" element={token ? <Profile /> : <Navigate to="/login" />} />
        </Routes>
      </div>
      {token && !isAuthPage && <MobileNav onUpload={() => setShowUpload(true)} />}
      {showUpload && <Upload onClose={() => setShowUpload(false)} />}
    </div>
  );
}

export default function App() {
  return (
    <Router>
      <AppShell />
    </Router>
  );
}
