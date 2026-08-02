import { useState } from 'react';
import axios from 'axios';

export default function Register() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const form = new FormData();
      form.append('username', username);
      form.append('password', password);
      
      await axios.post('http://127.0.0.1:8000/api/register', form);
      setSuccess('Account created! You can now login.');
      setError('');
      setUsername('');
      setPassword('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed');
      setSuccess('');
    }
  };

  return (
    <div className="flex items-center justify-center min-h-[80vh]">
      <div className="glass p-10 rounded-2xl w-full max-w-md shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-teal-400 to-indigo-500"></div>
        <h2 className="text-3xl font-bold mb-6 text-center text-white">Create Account</h2>
        {error && <div className="bg-red-500/20 text-red-400 p-3 rounded-lg mb-6 text-sm border border-red-500/30">{error}</div>}
        {success && <div className="bg-green-500/20 text-green-400 p-3 rounded-lg mb-6 text-sm border border-green-500/30">{success}</div>}
        
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">Username</label>
            <input 
              type="text" 
              value={username}
              onChange={e => setUsername(e.target.value)}
              className="w-full bg-gray-900/50 border border-gray-700 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-teal-500 transition-colors"
              required 
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">Password</label>
            <input 
              type="password" 
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="w-full bg-gray-900/50 border border-gray-700 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-teal-500 transition-colors"
              required 
            />
          </div>
          <button type="submit" className="w-full bg-gradient-to-r from-teal-500 to-indigo-600 hover:from-teal-400 hover:to-indigo-500 text-white font-bold py-3 rounded-lg transition-all shadow-lg hover:shadow-teal-500/20 mt-6">
            Sign Up
          </button>
        </form>
        <p className="mt-6 text-center text-gray-400 text-sm">
          Already have an account? <a href="/login" className="text-teal-400 hover:text-teal-300">Login here</a>
        </p>
      </div>
    </div>
  );
}
