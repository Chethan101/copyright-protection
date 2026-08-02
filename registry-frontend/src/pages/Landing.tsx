import { Shield, Lock, FileCheck, ArrowRight } from 'lucide-react';

export default function Landing() {
  return (
    <div className="min-h-[85vh] flex flex-col justify-center">
      {/* Hero Section */}
      <div className="text-center space-y-8 max-w-4xl mx-auto py-20 relative">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-teal-500/20 rounded-full blur-[100px] -z-10"></div>
        <div className="absolute top-1/2 left-1/4 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-indigo-500/20 rounded-full blur-[80px] -z-10"></div>
        
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-gray-800/80 border border-gray-700 text-sm font-medium text-teal-400">
          <span className="w-2 h-2 rounded-full bg-teal-400 animate-pulse"></span>
          V4 Rebuild is Live
        </div>
        
        <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight text-white leading-tight">
          The Ultimate Standard for <span className="text-transparent bg-clip-text bg-gradient-to-r from-teal-400 to-indigo-500">Copyright Protection</span>
        </h1>
        
        <p className="text-xl text-gray-400 max-w-2xl mx-auto leading-relaxed">
          Secure your digital assets immutably on the Ganache blockchain. 
          Our hybrid DWT-DCT watermark engine guarantees ownership verification anywhere on the internet.
        </p>
        
        <div className="flex items-center justify-center gap-6 pt-4">
          <a href="/register" className="px-8 py-4 rounded-xl bg-white text-gray-900 font-bold hover:bg-gray-100 transition-all flex items-center gap-2 shadow-xl shadow-white/10">
            Start Protecting <ArrowRight className="w-5 h-5" />
          </a>
          <a href="/explorer" className="px-8 py-4 rounded-xl glass text-white font-medium hover:bg-gray-800/80 transition-all">
            View Blockchain Explorer
          </a>
        </div>
      </div>

      {/* Features Section */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-6xl mx-auto mt-12 pb-20">
        <div className="glass p-8 rounded-2xl hover:-translate-y-2 transition-transform duration-300">
          <div className="w-14 h-14 bg-teal-500/20 rounded-2xl flex items-center justify-center mb-6">
            <Lock className="w-7 h-7 text-teal-400" />
          </div>
          <h3 className="text-xl font-bold mb-3">Immutable Security</h3>
          <p className="text-gray-400 leading-relaxed">
            Every registered asset is permanently hashed and stored on our decentralized Ganache blockchain ledger, preventing any tampering or unauthorized claims.
          </p>
        </div>
        
        <div className="glass p-8 rounded-2xl hover:-translate-y-2 transition-transform duration-300">
          <div className="w-14 h-14 bg-indigo-500/20 rounded-2xl flex items-center justify-center mb-6">
            <Shield className="w-7 h-7 text-indigo-400" />
          </div>
          <h3 className="text-xl font-bold mb-3">Invisible Watermarking</h3>
          <p className="text-gray-400 leading-relaxed">
            We use cutting-edge Hybrid DWT-DCT techniques to embed your Watermark ID directly into the image frequencies, imperceptible to the human eye.
          </p>
        </div>
        
        <div className="glass p-8 rounded-2xl hover:-translate-y-2 transition-transform duration-300">
          <div className="w-14 h-14 bg-purple-500/20 rounded-2xl flex items-center justify-center mb-6">
            <FileCheck className="w-7 h-7 text-purple-400" />
          </div>
          <h3 className="text-xl font-bold mb-3">Automated Enforcement</h3>
          <p className="text-gray-400 leading-relaxed">
            Our API seamlessly integrates with social media platforms like VibeSocial to scan, extract, and block copyrighted content automatically in real-time.
          </p>
        </div>
      </div>
    </div>
  );
}
