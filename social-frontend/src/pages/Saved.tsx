import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';
import { API_BASE_URL } from '../config';

export default function Saved() {
  const [posts, setPosts] = useState<any[] | null>(null);

  useEffect(() => {
    const fetch = async () => {
      try {
        const res = await api.get('/saved');
        setPosts(res.data.posts);
      } catch { }
    };
    fetch();
  }, []);

  if (!posts) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
      <div className="spinner" style={{ width: 36, height: 36, borderWidth: 3 }} />
    </div>
  );

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <div style={{ padding: '20px 16px 12px', fontSize: 22, fontWeight: 800 }}>Saved</div>
      <div style={{ borderTop: '1px solid var(--border)' }} />

      {posts.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>
          <svg width="60" height="60" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" style={{ margin: '0 auto 16px', display: 'block', opacity: 0.3 }}>
            <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
          </svg>
          <p style={{ fontWeight: 700, fontSize: 18, color: 'var(--text)', marginBottom: 8 }}>No Saved Posts Yet</p>
          <p>Tap the bookmark icon on any post to save it here.</p>
        </div>
      ) : (
        <div className="profile-grid" style={{ marginTop: 3 }}>
          {posts.map((p: any) => (
            <Link key={p.id} to={`/profile/${p.uploader}`} style={{ position: 'relative', aspectRatio: '1', overflow: 'hidden', background: 'var(--surface2)', display: 'block' }}>
              {['.mp4', '.mov', '.webm', '.avi', '.mkv'].some(ext => p.image_url.toLowerCase().endsWith(ext)) ? (
                <video src={`${API_BASE_URL}${p.image_url}`} className="profile-grid-img" muted />
              ) : (
                <img src={`${API_BASE_URL}${p.image_url}`} alt="" className="profile-grid-img" />
              )}
              <div style={{
                position: 'absolute', inset: 0, background: 'rgba(0,0,0,0)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 20,
                transition: 'background 0.2s', fontSize: 16, fontWeight: 700, color: 'white',
              }}
                onMouseEnter={e => (e.currentTarget.style.background = 'rgba(0,0,0,0.4)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'rgba(0,0,0,0)')}
              >
                <span>❤️ {p.likes_count}</span>
                <span>💬 {p.comments_count}</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
