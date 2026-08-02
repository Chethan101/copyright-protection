import { useState, useEffect } from 'react';
import axios from 'axios';

const API_URL = 'http://127.0.0.1:8000';

export default function SocialMediaDashboard() {
  const [data, setData] = useState<any>(null);

  const fetchDashboard = async () => {
    try {
      const res = await axios.get(`${API_URL}/social/dashboard`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      setData(res.data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchDashboard();
  }, []);

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      <header className="mb-10">
        <h1 className="text-4xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-purple-400 to-indigo-400">
          Social Media Statistics
        </h1>
        <p className="text-gray-400 mt-2">Monitor your activity and protect your assets</p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        
        {/* Published Posts */}
        <div className="bg-gray-800 p-6 rounded-xl shadow-lg border border-gray-700">
          <h3 className="text-xl font-bold mb-4 text-white flex items-center">
            <svg className="w-5 h-5 mr-2 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
            Published Posts ({data?.posts?.length || 0})
          </h3>
          <div className="space-y-3">
            {data?.posts?.map((post: any) => (
              <div key={post.id} className="bg-gray-900 p-4 rounded-lg flex justify-between items-center border border-gray-700">
                <span className="font-semibold text-gray-300">{post.file_name}</span>
                <span className="text-xs text-gray-500">{new Date(post.timestamp).toLocaleString()}</span>
              </div>
            ))}
            {!data?.posts?.length && <p className="text-gray-500 text-sm">No published posts yet.</p>}
          </div>
        </div>

        {/* Blocked Upload Attempts by this user */}
        <div className="bg-gray-800 p-6 rounded-xl shadow-lg border border-gray-700">
          <h3 className="text-xl font-bold mb-4 text-white flex items-center">
            <svg className="w-5 h-5 mr-2 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
            My Blocked Upload Attempts ({data?.logs?.length || 0})
          </h3>
          <div className="space-y-3">
            {data?.logs?.map((log: any) => (
              <div key={log.id} className="bg-red-900/20 p-4 rounded-lg border border-red-900/50">
                <div className="flex justify-between items-start mb-1">
                  <span className="font-semibold text-red-400 text-sm">Attempt Blocked</span>
                  <span className="text-xs text-gray-500">{new Date(log.timestamp).toLocaleString()}</span>
                </div>
                <p className="text-xs text-gray-400 font-mono break-all mb-1">Hash: {log.image_hash}</p>
                <div className="flex justify-between items-center mt-2">
                  <p className="text-xs text-red-300">Reason: {log.reason}</p>
                  {log.confidence_score && (
                    <span className="bg-purple-900/50 text-purple-300 text-xs px-2 py-1 rounded border border-purple-500/50">
                      Match: {log.confidence_score.toFixed(1)}%
                    </span>
                  )}
                </div>
              </div>
            ))}
            {!data?.logs?.length && <p className="text-gray-500 text-sm">No blocked attempts. Good job!</p>}
          </div>
        </div>

        {/* Copyright Notifications (Someone else tried to upload YOUR image) */}
        <div className="lg:col-span-2 bg-gray-800 p-6 rounded-xl shadow-lg border border-gray-700 border-l-4 border-l-purple-500">
          <h3 className="text-xl font-bold mb-4 text-white flex items-center">
            <svg className="w-5 h-5 mr-2 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"></path></svg>
            Copyright Notifications ({data?.notifications?.length || 0})
          </h3>
          <p className="text-sm text-gray-400 mb-6">Alerts when other users attempt to upload your registered images.</p>
          
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-gray-400">
              <thead className="text-xs text-gray-300 uppercase bg-gray-700/50">
                <tr>
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3">Attempted By User</th>
                  <th className="px-4 py-3">Asset Hash</th>
                  <th className="px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {data?.notifications?.map((notif: any) => (
                  <tr key={notif.id} className="border-b border-gray-700 hover:bg-gray-750">
                    <td className="px-4 py-4">{new Date(notif.timestamp).toLocaleString()}</td>
                    <td className="px-4 py-4 font-bold text-red-400">{notif.attempted_by}</td>
                    <td className="px-4 py-4 font-mono text-xs">{notif.image_hash}</td>
                    <td className="px-4 py-4 space-y-1">
                      <span className="bg-red-500/20 text-red-500 px-2 py-1 rounded text-xs font-bold block w-fit">BLOCKED</span>
                      {notif.confidence && (
                        <span className="text-xs text-purple-400 block font-mono">Match: {notif.confidence.toFixed(1)}%</span>
                      )}
                    </td>
                  </tr>
                ))}
                {!data?.notifications?.length && (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-gray-500">
                      No unauthorized upload attempts detected for your assets.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </div>
  );
}
