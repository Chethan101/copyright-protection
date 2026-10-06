import { useState, useEffect, useCallback, useRef } from 'react';
import api from '../../api';
import { REGISTRY_SESSION_EVENT, getRegistryToken, setRegistryToken, clearRegistryToken } from '../../registryApi';
import RegistryAuth from './RegistryAuth';
import RegistryDashboard from './RegistryDashboard';
import RegistryAsset from './RegistryAsset';
import RegistryExplorer from './RegistryExplorer';

type View = 'dashboard' | 'asset' | 'explorer';

const VIEWS: { key: View; label: string }[] = [
  { key: 'dashboard', label: 'Dashboard' },
  { key: 'asset', label: 'Register Asset' },
  { key: 'explorer', label: 'Blockchain' },
];

/**
 * The CopyGuard Registry, embedded in VibeSocial's profile page.
 *
 * Standalone, this was its own app with a router and a top nav bar. Here the same
 * screens are driven by local view state so it lives inside the profile tab without
 * taking over the URL or the surrounding app chrome.
 */
export default function RegistryPortal() {
  const [token, setToken] = useState<string | null>(getRegistryToken());
  const [view, setView] = useState<View>('dashboard');
  const [status, setStatus] = useState<'connecting' | 'ready' | 'error'>('connecting');
  const [error, setError] = useState('');

  // Sign in to the registry as the current VibeSocial user, with no second login.
  const connect = useCallback(async () => {
    setStatus('connecting');
    try {
      const res = await api.post('/registry/session', {});
      setRegistryToken(res.data.access_token);
      setStatus('ready');
    } catch (err: any) {
      // Never fall back to a token already in storage: it may belong to whoever used
      // this browser before, and registrations would land in their account.
      clearRegistryToken();
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'The registry service is not reachable right now.');
      setStatus('error');
    }
  }, []);

  // Run on every mount (not only when no token is stored) so a session left over from a
  // different VibeSocial account is always replaced by one for whoever is signed in now.
  useEffect(() => { connect(); }, [connect]);

  // The api client clears the session on a 401 (e.g. it expired). Re-open it for the
  // same VibeSocial user instead of dropping them out of the tab.
  useEffect(() => {
    const sync = () => setToken(getRegistryToken());
    window.addEventListener(REGISTRY_SESSION_EVENT, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(REGISTRY_SESSION_EVENT, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);
  const lastAutoReconnect = useRef(0);
  useEffect(() => {
    if (status !== 'ready' || token) return;
    // At most one automatic retry per 15 s: if fresh sessions keep being rejected,
    // show the error instead of looping.
    if (Date.now() - lastAutoReconnect.current < 15000) {
      setError('Your registry session keeps being rejected. Please try again.');
      setStatus('error');
      return;
    }
    lastAutoReconnect.current = Date.now();
    connect();
  }, [status, token, connect]);

  if (status === 'error') {
    return (
      <div className="registry-scope">
        <RegistryAuth message={error} onRetry={connect} busy={false} />
      </div>
    );
  }

  if (status === 'connecting' || !token) {
    return (
      <div className="registry-scope">
        <div className="flex flex-col items-center justify-center py-24 text-gray-400 gap-4">
          <span className="w-8 h-8 border-2 border-teal-500/30 border-t-teal-400 rounded-full animate-spin"></span>
          Connecting to CopyGuard Registry...
        </div>
      </div>
    );
  }

  return (
    <div className="registry-scope">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-8 pb-4 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-teal-400 flex items-center justify-center">
            <span className="font-bold text-white text-lg">C</span>
          </div>
          <span className="text-lg font-bold tracking-wide">CopyGuard<span className="text-teal-400">Registry</span></span>
        </div>

        <div className="flex items-center gap-2 text-sm font-medium flex-wrap">
          {VIEWS.map(v => (
            <button
              key={v.key}
              onClick={() => setView(v.key)}
              className={`px-3 py-2 rounded-lg transition-colors cursor-pointer ${
                view === v.key ? 'bg-teal-500/20 text-teal-300' : 'text-gray-400 hover:text-teal-400'
              }`}
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>

      {view === 'dashboard' && <RegistryDashboard onNavigate={(v) => setView(v as View)} />}
      {view === 'asset' && <RegistryAsset />}
      {view === 'explorer' && <RegistryExplorer />}
    </div>
  );
}
