import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import api from '../api';
import { API_BASE_URL } from '../config';

export default function Profile() {
  const { username } = useParams<{ username: string }>();
  const [data, setData] = useState<any>(null);
  const myUsername = localStorage.getItem('social_username');

  useEffect(() => {
    const fetch = async () => {
      try {
        const res = await api.get(`/profile/${username}`);
        setData(res.data);
      } catch { }
    };
    fetch();
  }, [username]);

  if (!data) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
      <div className="spinner" style={{ width: 36, height: 36, borderWidth: 3 }} />
    </div>
  );

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      {/* Profile Header */}
      <div className="profile-header">
        <div className="avatar xl">{data.user.username[0]?.toUpperCase()}</div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
            <h2 style={{ fontSize: 24, fontWeight: 300 }}>{data.user.username}</h2>
            {myUsername === username && (
              <button style={{ background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--text)', padding: '6px 16px', borderRadius: 8, fontWeight: 700, fontSize: 14, cursor: 'pointer' }}>
                Edit profile
              </button>
            )}
          </div>
          <div className="profile-stats">
            <div className="profile-stat">
              <span className="num">{data.posts_count}</span>
              <span className="label">posts</span>
            </div>
          </div>
          {data.user.bio && <p style={{ marginTop: 14, fontSize: 14 }}>{data.user.bio}</p>}
        </div>
      </div>

      {/* Divider */}
      <div style={{ borderTop: '1px solid var(--border)' }} />

      {/* Posts Grid */}
      {data.posts.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>
          <svg width="60" height="60" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" style={{ margin: '0 auto 16px', display: 'block', opacity: 0.3 }}>
            <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
          </svg>
          <p style={{ fontWeight: 700, fontSize: 18, color: 'var(--text)' }}>No Posts Yet</p>
        </div>
      ) : (
        <div className="profile-grid" style={{ marginTop: 3 }}>
          {data.posts.map((p: any) => (
            <div key={p.id} style={{ position: 'relative', aspectRatio: '1', overflow: 'hidden', background: 'var(--surface2)' }}>
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
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
