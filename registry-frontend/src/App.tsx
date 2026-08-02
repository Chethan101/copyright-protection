import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import RegisterCopyright from './pages/RegisterCopyright';
import Explorer from './pages/Explorer';
import Landing from './pages/Landing';

function App() {
  const token = localStorage.getItem('registry_token');

  return (
    <Router>
      <div className="min-h-screen bg-gray-900 text-gray-100 font-sans">
        <nav className="glass sticky top-0 z-50 flex items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-teal-400 flex items-center justify-center">
              <span className="font-bold text-white text-lg">C</span>
            </div>
            <span className="text-xl font-bold tracking-wide">CopyGuard<span className="text-teal-400">Registry</span></span>
          </div>
          
          <div className="flex items-center gap-6 text-sm font-medium">
            {token ? (
              <>
                <a href="/dashboard" className="hover:text-teal-400 transition-colors">Dashboard</a>
                <a href="/register-copyright" className="hover:text-teal-400 transition-colors">Register Asset</a>
                <a href="/explorer" className="hover:text-teal-400 transition-colors">Blockchain</a>
                <button 
                  onClick={() => { localStorage.removeItem('registry_token'); window.location.href = '/login'; }}
                  className="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded-lg transition-colors"
                >
                  Sign Out
                </button>
              </>
            ) : (
              <>
                <a href="/login" className="hover:text-teal-400 transition-colors">Sign In</a>
                <a href="/register" className="bg-teal-500 hover:bg-teal-600 text-white px-4 py-2 rounded-lg transition-colors">Sign Up</a>
              </>
            )}
          </div>
        </nav>
        
        <main className="p-6 md:p-12 max-w-7xl mx-auto">
          <Routes>
            <Route path="/" element={token ? <Navigate to="/dashboard" /> : <Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/dashboard" element={token ? <Dashboard /> : <Navigate to="/login" />} />
            <Route path="/register-copyright" element={token ? <RegisterCopyright /> : <Navigate to="/login" />} />
            <Route path="/explorer" element={token ? <Explorer /> : <Navigate to="/login" />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
