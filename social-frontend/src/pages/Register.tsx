import { useState } from 'react';
import api from '../api';

export default function Register() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setError('');
    try {
      const form = new FormData();
      form.append('username', username);
      form.append('password', password);
      await api.post('/register', form);
      // Auto-login after register
      const loginForm = new URLSearchParams();
      loginForm.append('username', username);
      loginForm.append('password', password);
      const res = await api.post('/login', loginForm);
      localStorage.setItem('social_token', res.data.access_token);
      localStorage.setItem('social_username', res.data.username);
      localStorage.setItem('social_user_id', String(res.data.user_id));
      window.location.href = '/feed';
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed');
    } finally { setLoading(false); }
  };

  return (
    <div className="auth-page">
      <div className="auth-box">
        <div className="auth-logo">VibeSocial</div>
        <div className="auth-card">
          <p style={{ color: 'var(--text-muted)', fontSize: 17, fontWeight: 600, marginBottom: 20, lineHeight: 1.4 }}>
            Sign up to see photos and videos from your friends.
          </p>
          <form onSubmit={handleRegister}>
            <input className="auth-input" placeholder="Username" value={username} onChange={e => setUsername(e.target.value)} autoFocus />
            <input className="auth-input" placeholder="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} />
            {error && <div className="auth-error">{error}</div>}
            <p style={{ fontSize: 11, color: 'var(--text-muted)', margin: '10px 0 6px', lineHeight: 1.5 }}>
              By signing up, you agree to our Terms and Privacy Policy.
            </p>
            <button className="auth-btn" type="submit" disabled={loading || !username || !password}>
              {loading ? 'Signing up...' : 'Sign up'}
            </button>
          </form>
        </div>
        <div className="auth-card" style={{ padding: '18px 40px', fontSize: 14 }}>
          Have an account? <a href="/login" style={{ color: 'var(--blue)', fontWeight: 700, textDecoration: 'none' }}>Log in</a>
        </div>
      </div>
    </div>
  );
}
