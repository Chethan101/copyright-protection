import { Users, Camera, ShieldAlert, Sparkles } from 'lucide-react';

export default function Landing() {
  return (
    <div className="min-h-[85vh] flex flex-col justify-center">
      {/* Hero Section */}
      <div className="text-center space-y-8 max-w-4xl mx-auto py-20 relative">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-purple-500/20 rounded-full blur-[100px] -z-10"></div>
        <div className="absolute top-1/2 right-1/4 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-pink-500/20 rounded-full blur-[80px] -z-10"></div>
        
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-gray-800/80 border border-gray-700 text-sm font-medium text-purple-400">
          <span className="w-2 h-2 rounded-full bg-purple-400 animate-pulse"></span>
          Next-Gen Social Experience
        </div>
        
        <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight text-white leading-tight">
          Share your vibe, <span className="text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-500">safely.</span>
        </h1>
        
        <p className="text-xl text-gray-400 max-w-2xl mx-auto leading-relaxed">
          Welcome to VibeSocial. Connect with friends and share your life's moments.
          Powered by CopyGuard Registry to ensure true content authenticity and copyright protection.
        </p>
        
        <div className="flex items-center justify-center gap-6 pt-4">
          <a href="/register" className="px-8 py-4 rounded-xl bg-gradient-to-r from-purple-500 to-pink-600 hover:from-purple-400 hover:to-pink-500 text-white font-bold transition-all flex items-center gap-2 shadow-xl shadow-purple-500/20">
            Join the Community <Sparkles className="w-5 h-5" />
          </a>
          <a href="/login" className="px-8 py-4 rounded-xl glass text-white font-medium hover:bg-gray-800/80 transition-all">
            Log In
          </a>
        </div>
      </div>

      {/* Features Section */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-6xl mx-auto mt-12 pb-20">
        <div className="glass p-8 rounded-2xl hover:-translate-y-2 transition-transform duration-300 border-t-2 border-t-purple-500/50">
          <div className="w-14 h-14 bg-purple-500/20 rounded-2xl flex items-center justify-center mb-6">
            <Camera className="w-7 h-7 text-purple-400" />
          </div>
          <h3 className="text-xl font-bold mb-3">Share Instantly</h3>
          <p className="text-gray-400 leading-relaxed">
            Upload your favorite photos and share them with the world in a beautiful, distraction-free feed.
          </p>
        </div>
        
        <div className="glass p-8 rounded-2xl hover:-translate-y-2 transition-transform duration-300 border-t-2 border-t-pink-500/50">
          <div className="w-14 h-14 bg-pink-500/20 rounded-2xl flex items-center justify-center mb-6">
            <Users className="w-7 h-7 text-pink-400" />
          </div>
          <h3 className="text-xl font-bold mb-3">Connect Globally</h3>
          <p className="text-gray-400 leading-relaxed">
            Follow your friends, discover new creators, and engage with the community in real-time.
          </p>
        </div>
        
        <div className="glass p-8 rounded-2xl hover:-translate-y-2 transition-transform duration-300 border-t-2 border-t-indigo-500/50">
          <div className="w-14 h-14 bg-indigo-500/20 rounded-2xl flex items-center justify-center mb-6">
            <ShieldAlert className="w-7 h-7 text-indigo-400" />
          </div>
          <h3 className="text-xl font-bold mb-3">Zero Plagiarism</h3>
          <p className="text-gray-400 leading-relaxed">
            We partner with CopyGuard Registry to scan every single upload, ensuring nobody steals your intellectual property.
          </p>
        </div>
      </div>
    </div>
  );
}
