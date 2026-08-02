import { useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const API_URL = 'http://127.0.0.1:8000';

export default function Login() {
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setMsg('');
    
    try {
      const formData = new FormData();
      formData.append('username', username);
      formData.append('password', password);

      if (isLogin) {
        const res = await axios.post(`${API_URL}/login`, formData);
        localStorage.setItem('token', res.data.access_token);
        navigate('/dashboard');
      } else {
        await axios.post(`${API_URL}/register`, formData);
        setMsg('Registration successful! Please login.');
        setIsLogin(true);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'An error occurred');
    }
  };

  return (
    <div className="max-w-md mx-auto mt-20 p-8 bg-gray-800 rounded-xl shadow-2xl border border-gray-700">
      <h2 className="text-3xl font-bold mb-6 text-center bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-500">
        {isLogin ? 'Welcome Back' : 'Create Account'}
      </h2>
      
      {error && <div className="mb-4 p-3 bg-red-900/50 border border-red-500 text-red-200 rounded-lg text-sm">{error}</div>}
      {msg && <div className="mb-4 p-3 bg-green-900/50 border border-green-500 text-green-200 rounded-lg text-sm">{msg}</div>}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-gray-400 text-sm font-bold mb-2">Username</label>
          <input
            type="text"
            className="w-full p-3 rounded-lg bg-gray-900 border border-gray-700 text-white focus:outline-none focus:border-blue-500 transition"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="block text-gray-400 text-sm font-bold mb-2">Password</label>
          <input
            type="password"
            className="w-full p-3 rounded-lg bg-gray-900 border border-gray-700 text-white focus:outline-none focus:border-blue-500 transition"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        <button
          type="submit"
          className="w-full bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white font-bold py-3 px-4 rounded-lg shadow-lg transform transition hover:-translate-y-0.5"
        >
          {isLogin ? 'Login' : 'Register'}
        </button>
      </form>
      
      <p className="mt-6 text-center text-gray-400 text-sm">
        {isLogin ? "Don't have an account? " : "Already have an account? "}
        <button 
          onClick={() => setIsLogin(!isLogin)}
          className="text-blue-400 hover:text-blue-300 font-semibold"
        >
          {isLogin ? 'Sign up' : 'Log in'}
        </button>
      </p>
    </div>
  );
}
