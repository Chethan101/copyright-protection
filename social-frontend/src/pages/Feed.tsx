import { useState, useEffect, useRef } from 'react';
import axios from 'axios';

const API = 'http://127.0.0.1:8001/api';
const token = () => localStorage.getItem('social_token');
const myUsername = () => localStorage.getItem('social_username') || '';

function timeAgo(iso: string) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function PostCard({ post, onLike, onComment, onRepost }: any) {
  const [showAllComments, setShowAllComments] = useState(false);
  const [commentText, setCommentText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [likeAnim, setLikeAnim] = useState(false);
  const [localLiked, setLocalLiked] = useState(post.liked);
  const [localLikes, setLocalLikes] = useState(post.likes_count);
  const [localComments, setLocalComments] = useState(post.comments);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleLike = async () => {
    setLikeAnim(true);
    setTimeout(() => setLikeAnim(false), 300);
    setLocalLiked(!localLiked);
    setLocalLikes((n: number) => localLiked ? n - 1 : n + 1);
    await onLike(post.id);
  };

  const handleComment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!commentText.trim()) return;
    setSubmitting(true);
    const newComment = await onComment(post.id, commentText.trim());
    if (newComment) {
      setLocalComments((prev: any[]) => [...prev, newComment]);
      setCommentText('');
    }
    setSubmitting(false);
  };

  const handleRepost = async () => {
    await onRepost(post.id);
  };

  const visibleComments = showAllComments ? localComments : localComments.slice(-2);

  return (
    <div className="post-card">
      {/* Header */}
      <div className="post-header">
        <a className="post-user" href={`/profile/${post.uploader}`}>
          <div className="avatar">{post.uploader[0]?.toUpperCase()}</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 14 }}>{post.uploader}</div>
            {post.repost_of && <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Reposted</div>}
          </div>
        </a>
        <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text)', fontSize: 20, padding: '0 4px' }}>•••</button>
      </div>

      {/* Image */}
      <img src={post.image_url} alt="post" className="post-image" />

      {/* Action buttons */}
      <div className="post-actions">
        <button
          className={`action-btn ${localLiked ? 'liked' : ''} ${likeAnim ? 'like-anim' : ''}`}
          onClick={handleLike}
        >
          <svg viewBox="0 0 24 24" fill={localLiked ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2">
            <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
          </svg>
        </button>

        <button className="action-btn" onClick={() => inputRef.current?.focus()}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
        </button>

        <button className="action-btn" onClick={handleRepost} title="Repost">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>
          </svg>
        </button>

        <button className="action-btn save-btn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
          </svg>
        </button>
      </div>

      {/* Likes */}
      {localLikes > 0 && (
        <div className="post-likes">{localLikes.toLocaleString()} {localLikes === 1 ? 'like' : 'likes'}</div>
      )}

      {/* Caption */}
      {post.caption && (
        <div className="post-caption">
          <strong>{post.uploader}</strong>
          {post.caption}
        </div>
      )}

      {/* Comments */}
      <div className="comments-section">
        {localComments.length > 2 && !showAllComments && (
          <button className="view-comments-btn" onClick={() => setShowAllComments(true)}>
            View all {localComments.length} comments
          </button>
        )}
        {visibleComments.map((c: any) => (
          <div key={c.id} className="comment-row">
            <div>
              <strong>{c.username}</strong>
              {c.text}
              <div className="comment-time">{timeAgo(c.timestamp)}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Timestamp */}
      <div className="post-time">{timeAgo(post.timestamp)}</div>

      {/* Comment input */}
      <form className="comment-input-row" onSubmit={handleComment}>
        <div className="avatar" style={{ width: 28, height: 28, fontSize: 11 }}>
          {myUsername()[0]?.toUpperCase()}
        </div>
        <input
          ref={inputRef}
          className="comment-input"
          placeholder="Add a comment..."
          value={commentText}
          onChange={e => setCommentText(e.target.value)}
        />
        <button className="comment-submit" type="submit" disabled={!commentText.trim() || submitting}>
          Post
        </button>
      </form>
    </div>
  );
}

function StoriesBar({ posts }: { posts: any[] }) {
  const users = Array.from(new Map(posts.map(p => [p.uploader, p])).values()).slice(0, 12);
  if (!users.length) return null;
  return (
    <div className="stories-bar">
      {users.map(u => (
        <a key={u.uploader} className="story-item" href={`/profile/${u.uploader}`} style={{ textDecoration: 'none' }}>
          <div className="story-ring">
            <div className="story-inner">{u.uploader[0]?.toUpperCase()}</div>
          </div>
          <span className="story-name">{u.uploader}</span>
        </a>
      ))}
    </div>
  );
}

export default function Feed({ onOpenUpload }: { onOpenUpload: () => void }) {
  const [posts, setPosts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchFeed = async () => {
    try {
      const res = await axios.get(`${API}/feed`, { headers: { Authorization: `Bearer ${token()}` } });
      setPosts(res.data.posts);
    } catch (err: any) {
      if (err.response?.status === 401) window.location.href = '/login';
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchFeed(); }, []);

  const handleLike = async (postId: number) => {
    await axios.post(`${API}/posts/${postId}/like`, {}, { headers: { Authorization: `Bearer ${token()}` } });
  };

  const handleComment = async (postId: number, text: string) => {
    try {
      const res = await axios.post(`${API}/posts/${postId}/comment`, { text }, { headers: { Authorization: `Bearer ${token()}` } });
      return res.data;
    } catch { return null; }
  };

  const handleRepost = async (postId: number) => {
    try {
      await axios.post(`${API}/posts/${postId}/repost`, {}, { headers: { Authorization: `Bearer ${token()}` } });
      fetchFeed();
    } catch (err: any) {
      if (err.response?.data?.detail === 'Already reposted') alert('You already reposted this!');
    }
  };

  if (loading) return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '80vh' }}>
      <div className="spinner" style={{ width: 36, height: 36, borderWidth: 3 }} />
    </div>
  );

  if (!posts.length) return (
    <div style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--text-muted)' }}>
      <svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" style={{ margin: '0 auto 20px', display: 'block', opacity: 0.3 }}>
        <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
      </svg>
      <p style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)', marginBottom: 8 }}>No Posts Yet</p>
      <p style={{ marginBottom: 24 }}>Be the first to share something!</p>
      <button onClick={onOpenUpload} style={{ background: 'var(--blue)', border: 'none', color: 'white', padding: '10px 24px', borderRadius: 8, fontWeight: 700, cursor: 'pointer', fontSize: 14 }}>
        Share a Photo
      </button>
    </div>
  );

  return (
    <div>
      <StoriesBar posts={posts} />
      {posts.map(post => (
        <PostCard
          key={post.id}
          post={post}
          onLike={handleLike}
          onComment={handleComment}
          onRepost={handleRepost}
        />
      ))}
    </div>
  );
}
