import { useState, useRef } from 'react';
import axios from 'axios';

const API = 'http://127.0.0.1:8001/api';

export default function Upload({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState<'select' | 'caption' | 'loading' | 'blocked' | 'success'>('select');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState('');
  const [caption, setCaption] = useState('');
  const [blockInfo, setBlockInfo] = useState<any>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFile = (f: File) => {
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setStep('caption');
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
  };

  const handleShare = async () => {
    if (!file) return;
    setStep('loading');
    const formData = new FormData();
    formData.append('file', file);
    formData.append('caption', caption);
    try {
      const token = localStorage.getItem('social_token');
      await axios.post(`${API}/posts/upload`, formData, { headers: { Authorization: `Bearer ${token}` } });
      setStep('success');
      setTimeout(() => { onClose(); window.location.reload(); }, 1800);
    } catch (err: any) {
      if (err.response?.status === 403) {
        setBlockInfo(err.response.data.detail);
        setStep('blocked');
      } else {
        setStep('caption');
        alert(err.response?.data?.detail || 'Upload failed');
      }
    }
  };

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-box" style={{ maxWidth: step === 'select' ? 520 : 600 }}>

        {/* Header */}
        <div className="modal-header">
          {step !== 'select' && step !== 'blocked' && step !== 'success' && (
            <button className="modal-close" onClick={() => setStep('select')}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 5l-7 7 7 7"/></svg>
            </button>
          )}
          <span style={{ flex: 1, textAlign: 'center', fontSize: 16, fontWeight: 700 }}>
            {step === 'select' && 'Create new post'}
            {step === 'caption' && 'Add caption'}
            {step === 'loading' && 'Sharing...'}
            {step === 'blocked' && '⛔ Upload Blocked'}
            {step === 'success' && '✅ Posted!'}
          </span>
          <button className="modal-close" onClick={onClose}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        {/* Select file */}
        {step === 'select' && (
          <div
            style={{ padding: '60px 40px', textAlign: 'center', cursor: 'pointer' }}
            onDragOver={e => e.preventDefault()} onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}
          >
            <input type="file" ref={fileRef} accept="image/*,video/*" className="hidden" onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])} style={{ display: 'none' }} />
            <svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" style={{ margin: '0 auto 24px', display: 'block', opacity: 0.6 }}>
              <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
            </svg>
            <p style={{ fontSize: 22, fontWeight: 300, marginBottom: 16 }}>Drag photos or videos here</p>
            <button style={{ background: 'var(--blue)', color: 'white', border: 'none', padding: '10px 20px', borderRadius: 8, fontWeight: 700, fontSize: 14, cursor: 'pointer' }}>
              Select from computer
            </button>
          </div>
        )}

        {/* Caption step */}
        {step === 'caption' && (
          <div style={{ display: 'flex', minHeight: 320 }}>
            {file?.type.startsWith('video/') ? (
              <video src={preview} controls autoPlay loop muted style={{ width: 260, objectFit: 'cover', borderRadius: '0 0 0 16px' }} />
            ) : (
              <img src={preview} alt="" style={{ width: 260, objectFit: 'cover', borderRadius: '0 0 0 16px' }} />
            )}
            <div style={{ flex: 1, padding: 16, display: 'flex', flexDirection: 'column' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                <div className="avatar" style={{ width: 30, height: 30, fontSize: 12 }}>
                  {(localStorage.getItem('social_username') || 'U')[0].toUpperCase()}
                </div>
                <span style={{ fontWeight: 700, fontSize: 14 }}>{localStorage.getItem('social_username')}</span>
              </div>
              <textarea
                placeholder="Write a caption..."
                value={caption}
                onChange={e => setCaption(e.target.value)}
                style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: 'var(--text)', fontSize: 14, resize: 'none', fontFamily: 'inherit', lineHeight: 1.5 }}
                autoFocus
              />
              <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12, fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>
                🛡️ Your post will be scanned against the copyright registry
              </div>
              <button
                onClick={handleShare}
                style={{ background: 'var(--blue)', color: 'white', border: 'none', padding: '10px', borderRadius: 8, fontWeight: 700, fontSize: 14, cursor: 'pointer', width: '100%' }}
              >
                Share
              </button>
            </div>
          </div>
        )}

        {/* Loading */}
        {step === 'loading' && (
          <div style={{ padding: '60px 40px', textAlign: 'center' }}>
            <div className="spinner" style={{ width: 48, height: 48, borderWidth: 3, margin: '0 auto 20px' }} />
            <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>Checking copyright registry...</p>
          </div>
        )}

        {/* Success */}
        {step === 'success' && (
          <div style={{ padding: '60px 40px', textAlign: 'center' }}>
            <div style={{ fontSize: 64, marginBottom: 16 }}>🎉</div>
            <p style={{ fontSize: 20, fontWeight: 700 }}>Your post is live!</p>
          </div>
        )}

        {/* Blocked */}
        {step === 'blocked' && blockInfo && (
          <div style={{ padding: '32px', textAlign: 'center' }}>
            <div style={{ width: 72, height: 72, borderRadius: '50%', background: 'rgba(239,68,68,0.1)', border: '2px solid #ef4444', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px', fontSize: 32 }}>⛔</div>
            <h2 style={{ color: '#ef4444', fontSize: 20, fontWeight: 800, marginBottom: 8 }}>Copyright Violation Detected</h2>
            <p style={{ color: 'var(--text-muted)', fontSize: 14, marginBottom: 20 }}>
              This image belongs to another registered creator on the blockchain.
            </p>
            <div style={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 12, padding: 16, textAlign: 'left', marginBottom: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, fontSize: 14 }}>
                <span style={{ color: 'var(--text-muted)' }}>Original Owner</span>
                <span style={{ fontWeight: 700 }}>@{blockInfo.owner_name}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, fontSize: 14 }}>
                <span style={{ color: 'var(--text-muted)' }}>Confidence</span>
                <span style={{ fontWeight: 700, color: '#ef4444' }}>{blockInfo.confidence?.toFixed(1)}%</span>
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8, wordBreak: 'break-all' }}>
                <span style={{ color: 'var(--text-muted)' }}>Tx: </span>
                <span style={{ fontFamily: 'monospace', color: '#818cf8' }}>{blockInfo.tx_id?.substring(0, 32)}...</span>
              </div>
            </div>
            <button onClick={onClose} style={{ background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--text)', padding: '10px 24px', borderRadius: 8, fontWeight: 600, cursor: 'pointer', fontSize: 14 }}>
              Dismiss
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
