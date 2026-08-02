import { useState } from 'react';
import axios from 'axios';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setError('');
    try {
      const form = new URLSearchParams();
      form.append('username', username);
      form.append('password', password);
      const res = await axios.post('http://127.0.0.1:8001/api/login', form);
      localStorage.setItem('social_token', res.data.access_token);
      localStorage.setItem('social_username', res.data.username);
      localStorage.setItem('social_user_id', String(res.data.user_id));
      window.location.href = '/feed';
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Login failed');
    } finally { setLoading(false); }
  };

  return (
    <div className="auth-page">
      <div className="auth-box">
        <div className="auth-logo">VibeSocial</div>
        <div className="auth-card">
          <form onSubmit={handleLogin}>
            <input className="auth-input" placeholder="Username" value={username} onChange={e => setUsername(e.target.value)} autoFocus />
            <input className="auth-input" placeholder="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} />
            {error && <div className="auth-error">{error}</div>}
            <button className="auth-btn" type="submit" disabled={loading || !username || !password}>
              {loading ? 'Logging in...' : 'Log in'}
            </button>
          </form>
        </div>
        <div className="auth-card" style={{ padding: '18px 40px', fontSize: 14 }}>
          Don't have an account? <a href="/register" style={{ color: 'var(--blue)', fontWeight: 700, textDecoration: 'none' }}>Sign up</a>
        </div>
      </div>
    </div>
  );
}
