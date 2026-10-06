import { useState, useRef } from 'react';
import registryApi from '../../registryApi';
import { REGISTRY_BASE_URL } from '../../config';
import { Upload, CheckCircle2, Copy, Shield, Download } from 'lucide-react';

export default function RegistryAsset() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setPreview(URL.createObjectURL(e.target.files[0]));
      setResult(null);
      setError('');
    }
  };

  const handleDragOver = (e: React.DragEvent) => e.preventDefault();

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
      setPreview(URL.createObjectURL(e.dataTransfer.files[0]));
      setResult(null);
      setError('');
    }
  };

  const handleSubmit = async () => {
    if (!file) return;
    setLoading(true);
    setError('');
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await registryApi.post('/images/register', formData);
      setResult(res.data);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Registration failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  const isVideo = file?.type.startsWith('video/') ?? false;

  const handleDownload = async () => {
    try {
      const tokenRes = await registryApi.post(`/images/${result.image_id}/download-token`);
      const url = `${REGISTRY_BASE_URL}/api/images/${result.image_id}/download?token=${tokenRes.data.token}`;
      const a = document.createElement('a');
      a.href = url;
      // The registry always hands back watermarked videos as MP4 (browser-playable
      // H.264), regardless of the container the original file was uploaded in.
      a.download = `watermarked_${result.watermark_id}.${isVideo ? 'mp4' : 'jpg'}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch {
      setError('Could not start download. Please try again.');
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold mb-2">Register Copyright Asset</h1>
        <p className="text-gray-400">Secure your digital media immutably on the blockchain.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* LEFT: Upload */}
        <div className="space-y-6">
          <div
            className={`border-2 border-dashed rounded-2xl p-6 sm:p-10 text-center transition-colors cursor-pointer
              ${preview ? 'border-teal-500/50 bg-teal-500/5' : 'border-gray-700 bg-gray-900/50 hover:border-gray-500 hover:bg-gray-800/50'}`}
            onDragOver={handleDragOver}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              style={{ display: 'none' }}
              accept="image/*,video/*"
            />
            {preview ? (
              <div className="space-y-4">
                {isVideo ? (
                  <video src={preview} controls className="max-h-64 mx-auto rounded-lg shadow-lg" />
                ) : (
                  <img src={preview} alt="Preview" className="max-h-64 mx-auto rounded-lg object-contain shadow-lg" />
                )}
                <p className="text-sm text-gray-400">Click or drag to change file</p>
              </div>
            ) : (
              <div className="space-y-4 py-8">
                <div className="w-16 h-16 bg-gray-800 rounded-full flex items-center justify-center mx-auto text-gray-400">
                  <Upload className="w-8 h-8" />
                </div>
                <div>
                  <p className="font-medium">Upload Image or Video</p>
                  <p className="text-sm text-gray-500 mt-1">PNG, JPG, MP4, MOV, WEBM up to 50MB</p>
                </div>
              </div>
            )}
          </div>

          <button
            onClick={handleSubmit}
            disabled={!file || loading || !!result}
            className={`w-full py-4 rounded-xl font-bold transition-all shadow-lg
              ${!file || loading || result ? 'bg-gray-800 text-gray-500 cursor-not-allowed' : 'bg-gradient-to-r from-teal-500 to-indigo-600 hover:from-teal-400 hover:to-indigo-500 text-white shadow-teal-500/25 cursor-pointer'}`}
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                Watermarking &amp; Minting on Blockchain...
              </span>
            ) : result ? '✅ Registered Successfully' : 'Register Asset on Blockchain'}
          </button>

          {error && (
            <div className="bg-red-500/20 text-red-400 p-4 rounded-xl border border-red-500/30">{error}</div>
          )}

          {result && (
            <button
              onClick={() => { setResult(null); setFile(null); setPreview(''); setError(''); }}
              className="w-full py-3 rounded-xl font-medium border border-gray-700 hover:border-gray-500 text-gray-400 hover:text-white transition-all cursor-pointer"
            >
              Register Another Asset
            </button>
          )}
        </div>

        {/* RIGHT: Result */}
        <div>
          {result ? (
            <div className="glass p-5 sm:p-8 rounded-2xl border-teal-500/30 relative overflow-hidden h-full">
              <div className="absolute top-0 right-0 w-32 h-32 bg-teal-500/10 rounded-bl-full"></div>
              <div className="flex items-center gap-3 mb-6">
                <div className="bg-teal-500/20 p-2 rounded-full text-teal-400">
                  <CheckCircle2 className="w-8 h-8" />
                </div>
                <h2 className="text-xl sm:text-2xl font-bold text-teal-400">Registration Complete!</h2>
              </div>

              <div className="space-y-5">
                <div>
                  <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Watermark ID</label>
                  <div className="flex items-center gap-2 mt-1">
                    <code className="bg-gray-900/80 px-3 py-2 rounded text-teal-300 font-mono text-sm flex-1">{result.watermark_id}</code>
                    <button onClick={() => copyToClipboard(result.watermark_id)} className="p-2 bg-gray-800 hover:bg-gray-700 rounded text-gray-400 cursor-pointer"><Copy className="w-4 h-4" /></button>
                  </div>
                </div>

                <div>
                  <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Blockchain Transaction Hash</label>
                  <div className="flex items-center gap-2 mt-1">
                    <code className="bg-gray-900/80 px-3 py-2 rounded text-indigo-300 font-mono text-xs flex-1 truncate" title={result.tx_hash}>{result.tx_hash}</code>
                    <button onClick={() => copyToClipboard(result.tx_hash)} className="p-2 bg-gray-800 hover:bg-gray-700 rounded text-gray-400 cursor-pointer"><Copy className="w-4 h-4" /></button>
                  </div>
                </div>

                <div>
                  <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Content Hash</label>
                  <code className="block bg-gray-900/80 px-3 py-2 rounded text-gray-300 font-mono text-xs mt-1 truncate">{result.image_hash}</code>
                </div>

                <div className="flex justify-between items-center bg-gray-900/50 p-4 rounded-xl">
                  <div>
                    <span className="block text-xs text-gray-500 mb-1">Block Number</span>
                    <span className="font-mono text-lg">{result.block_number || 'N/A'}</span>
                  </div>
                  <div>
                    <span className="block text-xs text-gray-500 mb-1">Owner ID</span>
                    <span className="font-mono text-lg">#{result.owner_id}</span>
                  </div>
                </div>

                {/* DOWNLOAD BUTTON */}
                <button
                  onClick={handleDownload}
                  className="w-full py-4 rounded-xl font-bold bg-gradient-to-r from-green-500 to-teal-500 hover:from-green-400 hover:to-teal-400 text-white transition-all shadow-lg shadow-green-500/25 flex items-center justify-center gap-3 text-lg cursor-pointer"
                >
                  <Download className="w-5 h-5" />
                  Download Watermarked {isVideo ? 'Video' : 'Image'}
                </button>
                <p className="text-xs text-center text-gray-500">Use this watermarked {isVideo ? 'video' : 'image'} when posting on social media. Any unauthorized use will be detected.</p>
              </div>
            </div>
          ) : (
            <div className="glass p-6 sm:p-8 rounded-2xl h-full flex flex-col items-center justify-center text-center text-gray-500 border-dashed border-2 border-gray-700/50">
              <Shield className="w-16 h-16 mb-4 text-gray-700" />
              <h3 className="text-lg font-medium text-gray-400 mb-2">Immutable Protection</h3>
              <p className="text-sm">When you register an image or video, we extract its unique features, generate a perceptual hash, embed an invisible DWT-DCT watermark, and register the metadata on the Ganache blockchain.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
