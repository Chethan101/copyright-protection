import { useState } from 'react';
import axios from 'axios';

const API_URL = 'http://127.0.0.1:8000';

export default function SocialMedia() {
  const [file, setFile] = useState<File | null>(null);
  const [checking, setChecking] = useState(false);
  const [msg, setMsg] = useState('');
  const [errorObj, setErrorObj] = useState<any>(null);

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    
    setChecking(true);
    setErrorObj(null);
    setMsg('');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await axios.post(`${API_URL}/social/verify`, formData, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      setMsg(res.data.msg);
    } catch (err: any) {
      if (err.response?.data?.detail?.message) {
        setErrorObj(err.response.data.detail);
      } else {
        setErrorObj({ message: err.response?.data?.detail || 'Verification failed' });
      }
    } finally {
      setChecking(false);
      setFile(null);
    }
  };

  return (
    <div className="max-w-3xl mx-auto">
      <div className="bg-gradient-to-br from-indigo-900 to-purple-900 p-8 rounded-2xl shadow-2xl border border-indigo-500/30">
        <div className="text-center mb-8">
          <h2 className="text-3xl font-bold text-white mb-2">Social Media Demo Platform</h2>
          <p className="text-indigo-200">Simulate posting an image. Unauthorized uploads of copyrighted images will be blocked.</p>
        </div>

        <div className="bg-gray-900/80 p-6 rounded-xl backdrop-blur-sm">
          {errorObj && (
            <div className="mb-6 p-6 bg-red-900/40 border-2 border-red-500/50 rounded-xl">
              <div className="flex items-center mb-4">
                <svg className="w-8 h-8 mr-3 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                <h3 className="text-xl font-bold text-red-400">Copyright Protected Content Detected</h3>
              </div>
              
              <div className="space-y-2 text-red-100 bg-red-950/50 p-4 rounded-lg">
                <p>This image is registered on the blockchain.</p>
                {errorObj.owner_name && (
                  <div className="mt-4 space-y-1">
                    <p><span className="font-bold text-red-300">Owner Name:</span> {errorObj.owner_name}</p>
                    <p><span className="font-bold text-red-300">Owner ID:</span> {errorObj.owner_id}</p>
                    <p className="break-all"><span className="font-bold text-red-300">Blockchain Transaction ID:</span> {errorObj.tx_id}</p>
                  </div>
                )}
                <p className="mt-4 font-bold">Only the registered owner is permitted to upload or publish this protected content. The upload must be rejected.</p>
              </div>
            </div>
          )}
          
          {msg && (
            <div className="mb-6 p-4 bg-green-900/80 border-l-4 border-green-500 text-green-100 rounded flex items-start">
              <svg className="w-6 h-6 mr-3 text-green-400 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
              <div>
                <h4 className="font-bold">{msg.includes('Blockchain Verified') ? 'Ownership Verified' : 'Upload Approved'}</h4>
                <p className="text-sm">{msg}</p>
              </div>
            </div>
          )}

          <form onSubmit={handleUpload} className="space-y-6">
            <div className="border-2 border-dashed border-indigo-500/50 rounded-xl p-10 text-center hover:border-indigo-400 transition bg-indigo-900/20 relative">
              <input 
                type="file" 
                accept="image/*"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                required
              />
              <div className="text-indigo-200 pointer-events-none flex flex-col items-center">
                <svg className="w-12 h-12 mb-3 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                {file ? (
                  <span className="font-semibold text-white">{file.name}</span>
                ) : (
                  <span>Select an image to post</span>
                )}
              </div>
            </div>
            <button
              type="submit"
              disabled={checking || !file}
              className="w-full bg-gradient-to-r from-indigo-500 to-purple-500 hover:from-indigo-400 hover:to-purple-400 disabled:from-gray-600 disabled:to-gray-600 text-white font-bold py-3 px-4 rounded-xl shadow-lg transition"
            >
              {checking ? 'Verifying Copyright...' : 'Publish Post'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
