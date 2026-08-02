import { useState, useEffect } from 'react';
import axios from 'axios';
import { Shield, Activity, Image as ImageIcon, Download } from 'lucide-react';

export default function Dashboard() {
  const [data, setData] = useState<any>(null);
  
  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        const token = localStorage.getItem('registry_token');
        const res = await axios.get('http://127.0.0.1:8000/api/dashboard', {
          headers: { Authorization: `Bearer ${token}` }
        });
        setData(res.data);
      } catch (err) {
        if (err.response?.status === 401) {
          localStorage.removeItem('registry_token');
          window.location.href = '/login';
        }
      }
    };
    fetchDashboard();
  }, []);

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
                      <img src={`http://127.0.0.1:8000/api/images/${img.id}/download?token=${localStorage.getItem('registry_token')}`} alt="preview" className="w-16 h-16 object-cover rounded-lg border border-gray-700" onError={(e) => { e.currentTarget.src = 'https://via.placeholder.com/64?text=Protected' }} />
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
                      <a 
                        href={`http://127.0.0.1:8000/api/images/${img.id}/download`} 
                        download
                        className="p-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300 transition-colors inline-block"
                        onClick={(e) => {
                          e.preventDefault();
                          const token = localStorage.getItem('registry_token');
                          window.open(`http://127.0.0.1:8000/api/images/${img.id}/download?token=${token}`, '_blank');
                        }}
                      >
                        <Download className="w-4 h-4" />
                      </a>
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
