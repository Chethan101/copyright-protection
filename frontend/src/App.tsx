import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import SocialMedia from './pages/SocialMedia';
import SocialMediaDashboard from './pages/SocialMediaDashboard';
import BlockchainExplorer from './pages/BlockchainExplorer';

function App() {
  const token = localStorage.getItem('token');

  return (
    <Router>
      <div className="min-h-screen bg-gray-900 text-white font-sans">
        <nav className="bg-gray-800 p-4 shadow-md flex flex-wrap justify-between items-center border-b border-gray-700">
          <div className="text-xl font-bold tracking-wider text-blue-400 mr-4">
            CopyGuard<span className="text-white">.io</span>
          </div>
          <div className="space-x-2 md:space-x-4 flex flex-wrap items-center mt-2 md:mt-0">
            {token ? (
              <>
                <a href="/dashboard" className="text-gray-300 hover:text-white transition text-sm font-semibold">Owner Dashboard</a>
                <a href="/social-demo" className="text-gray-300 hover:text-white transition text-sm font-semibold">Upload Post</a>
                <a href="/social-dashboard" className="text-gray-300 hover:text-white transition text-sm font-semibold">Social Stats</a>
                <a href="/explorer" className="text-yellow-400 hover:text-yellow-300 transition text-sm font-mono font-bold bg-yellow-400/10 px-3 py-1 rounded">Blockchain</a>
                <button 
                  onClick={() => { localStorage.removeItem('token'); window.location.href = '/'; }}
                  className="bg-red-500/20 text-red-400 px-4 py-2 rounded-lg hover:bg-red-500/30 transition text-sm font-semibold ml-4"
                >
                  Logout
                </button>
              </>
            ) : (
              <a href="/" className="text-gray-300 hover:text-white transition">Login</a>
            )}
          </div>
        </nav>
        
        <main className="p-4 md:p-8">
          <Routes>
            <Route path="/" element={token ? <Navigate to="/dashboard" /> : <Login />} />
            <Route path="/dashboard" element={token ? <Dashboard /> : <Navigate to="/" />} />
            <Route path="/social-demo" element={token ? <SocialMedia /> : <Navigate to="/" />} />
            <Route path="/social-dashboard" element={token ? <SocialMediaDashboard /> : <Navigate to="/" />} />
            <Route path="/explorer" element={token ? <BlockchainExplorer /> : <Navigate to="/" />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
