import { BrowserRouter as Router, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import Login from './pages/Login';
import Register from './pages/Register';
import Feed from './pages/Feed';
import Upload from './pages/Upload';
import Notifications from './pages/Notifications';
import Profile from './pages/Profile';
import Saved from './pages/Saved';
import Registry from './pages/Registry';
import './index.css';

function logout() {
  localStorage.removeItem('social_token');
  localStorage.removeItem('social_username');
  localStorage.removeItem('social_user_id');
  // The registry session is issued for this VibeSocial user, so it ends with theirs.
  localStorage.removeItem('registry_token');
  window.location.href = '/login';
}

const Icon = {
  home: (filled: boolean) => (
    <svg viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
  ),
  search: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
  ),
  create: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
  ),
  heart: (filled: boolean) => (
    <svg viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
  ),
  bookmark: (filled: boolean) => (
    <svg viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
  ),
  shield: (filled: boolean) => (
    <svg viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
  ),
  logout: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
  ),
};

function Sidebar({ onUpload }: { onUpload: () => void }) {
  const location = useLocation();
  const navigate = useNavigate();
  const username = localStorage.getItem('social_username') || 'me';
  const is = (path: string) => location.pathname === path;
  const cls = (path: string) => (is(path) ? 'nav-item active' : 'nav-item');

  return (
    <div className="sidebar">
      <div className="sidebar-logo">
        <span className="logo-full">VibeSocial</span>
        <span className="logo-short">V</span>
      </div>
      <nav className="sidebar-nav">
        <button className={cls('/feed')} onClick={() => navigate('/feed')} title="Home">
          {Icon.home(is('/feed'))}<span className="nav-label">Home</span>
        </button>
        <button className="nav-item" onClick={() => {}} title="Search">
          {Icon.search()}<span className="nav-label">Search</span>
        </button>
        <button className="nav-item" onClick={onUpload} title="Create">
          {Icon.create()}<span className="nav-label">Create</span>
        </button>
        <button className={cls('/notifications')} onClick={() => navigate('/notifications')} title="Notifications">
          {Icon.heart(is('/notifications'))}<span className="nav-label">Notifications</span>
        </button>
        <button className={cls('/saved')} onClick={() => navigate('/saved')} title="Saved">
          {Icon.bookmark(is('/saved'))}<span className="nav-label">Saved</span>
        </button>
        <button className={cls('/registry')} onClick={() => navigate('/registry')} title="Registry">
          {Icon.shield(is('/registry'))}<span className="nav-label">Registry</span>
        </button>
        <button className={cls(`/profile/${username}`)} onClick={() => navigate(`/profile/${username}`)} title="Profile">
          <div className="avatar nav-avatar">{username[0]?.toUpperCase()}</div>
          <span className="nav-label">Profile</span>
        </button>
      </nav>

      <div className="sidebar-footer">
        <button className="nav-item" onClick={logout} title="Log out">
          {Icon.logout()}<span className="nav-label">Log out</span>
        </button>
      </div>
    </div>
  );
}

/** Phone top bar: brand plus the two destinations that don't fit the bottom bar. */
function MobileHeader() {
  const navigate = useNavigate();
  const location = useLocation();
  return (
    <div className="mobile-header">
      <div className="mobile-logo" onClick={() => navigate('/feed')}>VibeSocial</div>
      <div className="mobile-header-actions">
        <button className="mobile-nav-btn" onClick={() => navigate('/saved')} aria-label="Saved">
          {Icon.bookmark(location.pathname === '/saved')}
        </button>
        <button className="mobile-nav-btn" onClick={logout} aria-label="Log out">
          {Icon.logout()}
        </button>
      </div>
    </div>
  );
}

function MobileNav({ onUpload }: { onUpload: () => void }) {
  const navigate = useNavigate();
  const location = useLocation();
  const username = localStorage.getItem('social_username') || 'me';
  const is = (path: string) => location.pathname === path;
  return (
    <div className="mobile-nav">
      <button className="mobile-nav-btn" onClick={() => navigate('/feed')} aria-label="Home">{Icon.home(is('/feed'))}</button>
      <button className="mobile-nav-btn" onClick={() => navigate('/registry')} aria-label="Registry">{Icon.shield(is('/registry'))}</button>
      <button className="mobile-nav-btn" onClick={onUpload} aria-label="Create">{Icon.create()}</button>
      <button className="mobile-nav-btn" onClick={() => navigate('/notifications')} aria-label="Notifications">{Icon.heart(is('/notifications'))}</button>
      <button className="mobile-nav-btn" onClick={() => navigate(`/profile/${username}`)} aria-label="Profile">
        <div className={`avatar nav-avatar ${is(`/profile/${username}`) ? 'nav-avatar-active' : ''}`}>{username[0]?.toUpperCase()}</div>
      </button>
    </div>
  );
}

function AppShell() {
  const token = localStorage.getItem('social_token');
  const [showUpload, setShowUpload] = useState(false);
  const location = useLocation();
  const isAuthPage = ['/login', '/register', '/'].includes(location.pathname);
  // The feed and notifications read best as a narrow column; the registry dashboard,
  // profile grid and saved grid need the room.
  const isWide = ['/registry', '/saved'].includes(location.pathname) || location.pathname.startsWith('/profile/');
  const showChrome = !!token && !isAuthPage;

  return (
    <div className="app-layout">
      {showChrome && <Sidebar onUpload={() => setShowUpload(true)} />}
      {showChrome && <MobileHeader />}
      <div className={`main-content${isAuthPage ? ' auth' : ''}${isWide ? ' wide' : ''}`}>
        <Routes>
          <Route path="/" element={token ? <Navigate to="/feed" /> : <Navigate to="/login" />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/feed" element={token ? <Feed onOpenUpload={() => setShowUpload(true)} /> : <Navigate to="/login" />} />
          <Route path="/notifications" element={token ? <Notifications /> : <Navigate to="/login" />} />
          <Route path="/saved" element={token ? <Saved /> : <Navigate to="/login" />} />
          <Route path="/registry" element={token ? <Registry /> : <Navigate to="/login" />} />
          <Route path="/profile/:username" element={token ? <Profile /> : <Navigate to="/login" />} />
        </Routes>
      </div>
      {showChrome && <MobileNav onUpload={() => setShowUpload(true)} />}
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
