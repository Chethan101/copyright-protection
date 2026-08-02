import { useState, useEffect } from 'react';
import axios from 'axios';

const API = 'http://127.0.0.1:8001/api';

export default function Notifications() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    const fetch = async () => {
      try {
        const res = await axios.get(`${API}/violations`, { headers: { Authorization: `Bearer ${localStorage.getItem('social_token')}` } });
        setData(res.data);
      } catch { }
    };
    fetch();
  }, []);

  if (!data) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
      <div className="spinner" style={{ width: 36, height: 36, borderWidth: 3 }} />
    </div>
  );

  const allNotifications = [
    ...data.notifications.map((n: any) => ({ ...n, type: 'alert' })),
    ...data.my_violations.map((v: any) => ({ ...v, type: 'violation' })),
  ].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

  return (
    <div style={{ maxWidth: 600, margin: '0 auto' }}>
      <div style={{ padding: '20px 16px 12px', fontSize: 22, fontWeight: 800 }}>Notifications</div>

      {allNotifications.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🔔</div>
          <p style={{ fontSize: 18, fontWeight: 700, color: 'var(--text)', marginBottom: 8 }}>No notifications yet</p>
          <p>When someone interacts with your posts, you'll see it here.</p>
        </div>
      ) : (
        <div>
          {allNotifications.map((n: any) => (
            <div key={`${n.type}-${n.id}`} style={{
              display: 'flex', gap: 12, alignItems: 'flex-start',
              padding: '12px 16px',
              borderBottom: '1px solid var(--border)',
              background: n.type === 'alert' ? 'rgba(239,68,68,0.04)' : 'transparent'
            }}>
              <div style={{
                width: 44, height: 44, borderRadius: '50%', flexShrink: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20,
                background: n.type === 'alert' ? 'rgba(239,68,68,0.15)' : 'var(--surface2)',
              }}>
                {n.type === 'alert' ? '⛔' : '⚠️'}
              </div>
              <div style={{ flex: 1 }}>
                {n.type === 'alert' ? (
                  <p style={{ fontSize: 14, lineHeight: 1.5 }}>
                    <strong>Copyright Alert:</strong> User <strong>@{n.original_owner_name || 'unknown'}</strong> tried to steal your registered content.
                    {n.confidence_score && <span style={{ color: '#ef4444' }}> Detected with {n.confidence_score.toFixed(1)}% confidence.</span>}
                  </p>
                ) : (
                  <p style={{ fontSize: 14, lineHeight: 1.5 }}>
                    <strong>Violation blocked:</strong> You attempted to upload content belonging to <strong>@{n.original_owner_name}</strong>.
                    {n.confidence_score && <span style={{ color: '#f59e0b' }}> ({n.confidence_score.toFixed(1)}% match)</span>}
                  </p>
                )}
                <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                  {new Date(n.timestamp).toLocaleString()}
                </p>
                {n.tx_hash && (
                  <p style={{ fontSize: 11, color: '#818cf8', fontFamily: 'monospace', marginTop: 4, wordBreak: 'break-all' }}>
                    Tx: {n.tx_hash.substring(0, 40)}...
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
