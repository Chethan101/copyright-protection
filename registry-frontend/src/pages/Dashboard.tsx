import { useState, useEffect } from 'react';
import api from '../api';
import { API_BASE_URL } from '../config';
import { Shield, Activity, Image as ImageIcon, Download } from 'lucide-react';

export default function Dashboard() {
  const [data, setData] = useState<any>(null);
  const [imageTokens, setImageTokens] = useState<Record<number, string>>({});

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        const res = await api.get('/dashboard');
        setData(res.data);
      } catch {
        // 401s are already handled globally by the api client's response interceptor.
      }
    };
    fetchDashboard();
  }, []);

  useEffect(() => {
    if (!data || data.images.length === 0) return;
    let cancelled = false;
    const fetchTokens = async () => {
      const entries = await Promise.all(
        data.images.map(async (img: any) => {
          try {
            const res = await api.post(`/images/${img.id}/download-token`);
            return [img.id, res.data.token] as const;
          } catch {
            return [img.id, null] as const;
          }
        })
      );
      if (!cancelled) setImageTokens(Object.fromEntries(entries));
    };
    fetchTokens();
    return () => { cancelled = true; };
  }, [data]);

  const handleDownload = async (imageId: number) => {
    try {
      const res = await api.post(`/images/${imageId}/download-token`);
      window.open(`${API_BASE_URL}/api/images/${imageId}/download?token=${res.data.token}`, '_blank');
    } catch {
      // token mint failed (e.g. session expired) -- interceptor already redirects on 401
    }
  };

  if (!data) return <div className="text-center py-20">Loading dashboard...</div>;

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Welcome, {data.user.username}</h1>
        <a href="/register-copyright" className="bg-teal-500 hover:bg-teal-600 text-white px-6 py-3 rounded-lg font-medium transition-colors shadow-lg shadow-teal-500/20 flex items-center gap-2">
          <Shield className="w-5 h-5" />
          Protect New Asset
        </a>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="glass p-6 rounded-2xl relative overflow-hidden group">
          <div className="absolute -right-4 -top-4 w-24 h-24 bg-teal-500/10 rounded-full blur-2xl group-hover:bg-teal-500/20 transition-all"></div>
          <div className="flex items-center gap-4 mb-4">
            <div className="p-3 bg-teal-500/20 rounded-xl text-teal-400">
              <ImageIcon className="w-6 h-6" />
            </div>
            <h3 className="text-gray-400 font-medium">My Assets</h3>
          </div>
          <p className="text-4xl font-bold">{data.stats.my_images}</p>
        </div>

        <div className="glass p-6 rounded-2xl relative overflow-hidden group">
          <div className="absolute -right-4 -top-4 w-24 h-24 bg-indigo-500/10 rounded-full blur-2xl group-hover:bg-indigo-500/20 transition-all"></div>
          <div className="flex items-center gap-4 mb-4">
            <div className="p-3 bg-indigo-500/20 rounded-xl text-indigo-400">
              <Shield className="w-6 h-6" />
            </div>
            <h3 className="text-gray-400 font-medium">Network Assets</h3>
          </div>
          <p className="text-4xl font-bold">{data.stats.total_network_images}</p>
        </div>

        <div className="glass p-6 rounded-2xl relative overflow-hidden group">
          <div className="absolute -right-4 -top-4 w-24 h-24 bg-purple-500/10 rounded-full blur-2xl group-hover:bg-purple-500/20 transition-all"></div>
          <div className="flex items-center gap-4 mb-4">
            <div className="p-3 bg-purple-500/20 rounded-xl text-purple-400">
              <Activity className="w-6 h-6" />
            </div>
            <h3 className="text-gray-400 font-medium">Blocks Verified</h3>
          </div>
          <p className="text-4xl font-bold">{data.stats.blocks_verified}</p>
        </div>
      </div>

      <div className="glass rounded-2xl p-6">
        <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
          <ImageIcon className="w-5 h-5 text-teal-400" />
          My Protected Assets
        </h2>
        {data.images.length === 0 ? (
          <div className="text-center py-12 text-gray-400 border border-dashed border-gray-700 rounded-xl">
            You haven't registered any assets yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="text-gray-400 border-b border-gray-800">
                  <th className="pb-4 font-medium">Preview</th>
                  <th className="pb-4 font-medium">Watermark ID</th>
                  <th className="pb-4 font-medium">Transaction</th>
                  <th className="pb-4 font-medium">Timestamp</th>
                  <th className="pb-4 font-medium">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {data.images.map((img: any) => (
                  <tr key={img.id} className="hover:bg-gray-800/30 transition-colors">
                    <td className="py-4">
                      {imageTokens[img.id] ? (
                        <img
                          src={`${API_BASE_URL}/api/images/${img.id}/download?token=${imageTokens[img.id]}`}
                          alt="preview"
                          className="w-16 h-16 object-cover rounded-lg border border-gray-700"
                          onError={(e) => { e.currentTarget.src = 'https://via.placeholder.com/64?text=Protected' }}
                        />
                      ) : (
                        <div className="w-16 h-16 rounded-lg border border-gray-700 bg-gray-800/50 animate-pulse" />
                      )}
                    </td>
                    <td className="py-4">
                      <span className="font-mono text-sm bg-gray-800 px-2 py-1 rounded text-teal-400">{img.watermark_id}</span>
                    </td>
                    <td className="py-4">
                      <a href={`/explorer?tx=${img.tx_hash}`} className="font-mono text-sm text-indigo-400 hover:text-indigo-300">
                        {img.tx_hash.substring(0, 16)}...
                      </a>
                    </td>
                    <td className="py-4 text-sm text-gray-400">
                      {new Date(img.timestamp).toLocaleDateString()}
                    </td>
                    <td className="py-4">
                      <button
                        onClick={() => handleDownload(img.id)}
                        className="p-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300 transition-colors inline-block"
                      >
                        <Download className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
