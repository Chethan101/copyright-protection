import { useState, useEffect } from 'react';
import axios from 'axios';

const API_URL = 'http://127.0.0.1:8000';

export default function Dashboard() {
  const [data, setData] = useState<any>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');
  const [selectedCert, setSelectedCert] = useState<any>(null);

  const fetchDashboard = async () => {
    try {
      const res = await axios.get(`${API_URL}/dashboard`, {
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

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    
    setUploading(true);
    setError('');
    setMsg('');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await axios.post(`${API_URL}/upload`, formData, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      setMsg(`Success! Hash: ${res.data.image_hash} | TX: ${res.data.tx_hash.substring(0,20)}...`);
      fetchDashboard();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
      setFile(null);
    }
  };

  const downloadImage = (id: number) => {
    window.open(`${API_URL}/download/${id}?token=${localStorage.getItem('token')}`);
  };

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      <header className="mb-10">
        <h1 className="text-4xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-green-400">
          Owner Dashboard
        </h1>
        <p className="text-gray-400 mt-2">Welcome, {data?.username}</p>
      </header>

      {selectedCert && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 p-8 rounded-2xl max-w-2xl w-full border border-gray-600 shadow-2xl">
            <div className="text-center mb-6">
              <h2 className="text-3xl font-bold text-white mb-2 font-serif">Certificate of Ownership</h2>
              <div className="h-1 w-32 bg-blue-500 mx-auto"></div>
            </div>
            
            <div className="space-y-4 text-gray-300">
              <p><span className="font-bold text-white">Owner Name:</span> {data?.username}</p>
              <p><span className="font-bold text-white">Owner ID:</span> {data?.user_id}</p>
              <p><span className="font-bold text-white">Registration Date:</span> {new Date(selectedCert.timestamp).toLocaleString()}</p>
              <div className="bg-gray-900 p-4 rounded-lg break-all">
                <p><span className="text-blue-400 font-semibold block mb-1">Image SHA-256 Hash:</span> {selectedCert.image_hash}</p>
                <p className="mt-4"><span className="text-green-400 font-semibold block mb-1">Blockchain TX ID:</span> {selectedCert.transaction_hash}</p>
                <p className="mt-4"><span className="text-purple-400 font-semibold block mb-1">Watermark ID:</span> {selectedCert.watermark_id}</p>
              </div>
            </div>

            <div className="mt-8 flex justify-end">
              <button onClick={() => setSelectedCert(null)} className="bg-gray-600 hover:bg-gray-500 text-white px-6 py-2 rounded-lg font-bold">Close</button>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 bg-gray-800 p-6 rounded-xl shadow-lg border border-gray-700 h-fit">
          <h3 className="text-xl font-bold mb-4 text-white">Register & Protect Image</h3>
          
          {error && <div className="mb-4 p-3 bg-red-900/50 border border-red-500 text-red-200 rounded-lg text-sm">{error}</div>}
          {msg && <div className="mb-4 p-3 bg-green-900/50 border border-green-500 text-green-200 rounded-lg text-sm">{msg}</div>}

          <form onSubmit={handleUpload} className="space-y-4">
            <div className="border-2 border-dashed border-gray-600 rounded-lg p-6 text-center hover:border-blue-400 transition cursor-pointer relative">
              <input 
                type="file" 
                accept="image/*"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                required
              />
              <div className="text-gray-400 pointer-events-none">
                {file ? (
                  <span className="text-blue-400 font-semibold">{file.name}</span>
                ) : (
                  <span>Drag & drop or click to select image</span>
                )}
              </div>
            </div>
            <button
              type="submit"
              disabled={uploading || !file}
              className="w-full bg-gradient-to-r from-blue-600 to-green-600 hover:from-blue-500 hover:to-green-500 disabled:from-gray-600 disabled:to-gray-600 text-white font-bold py-3 px-4 rounded-lg shadow-lg transition"
            >
              {uploading ? 'Processing & Registering...' : 'Upload & Watermark'}
            </button>
          </form>
        </div>

        <div className="lg:col-span-2 bg-gray-800 p-6 rounded-xl shadow-lg border border-gray-700">
          <h3 className="text-xl font-bold mb-4 text-white">Registered Assets & Upload History</h3>
          
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-gray-400">
              <thead className="text-xs text-gray-300 uppercase bg-gray-700/50">
                <tr>
                  <th className="px-4 py-3">ID / Date</th>
                  <th className="px-4 py-3">Asset Hash</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data?.images?.map((img: any) => (
                  <tr key={img.id} className="border-b border-gray-700 hover:bg-gray-750">
                    <td className="px-4 py-4">
                      <div className="font-bold text-white">#{img.id}</div>
                      <div className="text-xs">{new Date(img.timestamp).toLocaleDateString()}</div>
                    </td>
                    <td className="px-4 py-4 font-mono text-xs break-all w-1/2">
                      <span className="block">{img.image_hash}</span>
                      <span className="block text-green-400 mt-1">TX: {img.transaction_hash?.substring(0,25)}...</span>
                    </td>
                    <td className="px-4 py-4 text-right space-x-2">
                      <button 
                        onClick={() => setSelectedCert(img)}
                        className="bg-purple-600/20 text-purple-400 px-3 py-1 rounded hover:bg-purple-600/40 transition text-xs font-bold"
                      >
                        Certificate
                      </button>
                      <button 
                        onClick={() => downloadImage(img.id)}
                        className="bg-blue-600/20 text-blue-400 px-3 py-1 rounded hover:bg-blue-600/40 transition text-xs font-bold"
                      >
                        Download
                      </button>
                    </td>
                  </tr>
                ))}
                {!data?.images?.length && (
                  <tr>
                    <td colSpan={3} className="px-4 py-8 text-center text-gray-500">
                      No registered assets found. Upload an image to start.
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
