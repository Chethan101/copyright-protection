import { useState, useEffect } from 'react';
import axios from 'axios';

const API_URL = 'http://127.0.0.1:8000';

export default function BlockchainExplorer() {
  const [blocks, setBlocks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchBlocks = async () => {
    try {
      const res = await axios.get(`${API_URL}/blockchain/blocks`);
      setBlocks(res.data.blocks);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBlocks();
    // Auto refresh every 5 seconds
    const interval = setInterval(fetchBlocks, 5000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="text-center mt-20 text-blue-400">Loading Ganache Blockchain...</div>;

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      <header className="mb-10 text-center">
        <h1 className="text-4xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-yellow-400 to-orange-500 font-mono tracking-wider">
          Blockchain Explorer
        </h1>
        <p className="text-gray-400 mt-2 font-mono">Live view of Ganache network blocks & transactions</p>
      </header>

      <div className="space-y-6">
        {blocks.map((block) => (
          <div key={block.hash} className="bg-gray-800 rounded-xl shadow-xl border border-gray-700 overflow-hidden">
            <div className="bg-gray-700/50 p-4 border-b border-gray-600 flex justify-between items-center">
              <div className="flex items-center space-x-3">
                <div className="bg-yellow-500/20 text-yellow-400 font-bold px-3 py-1 rounded text-sm font-mono">
                  Block #{block.number}
                </div>
                <div className="text-sm text-gray-400">
                  {new Date(block.timestamp * 1000).toLocaleString()}
                </div>
              </div>
              <div className="text-sm font-mono text-gray-400">
                {block.transactions.length} TXs
              </div>
            </div>
            
            <div className="p-6 space-y-4 text-sm font-mono break-all">
              <div>
                <span className="text-gray-500 font-bold">Block Hash:</span> 
                <span className="text-blue-300 ml-2">{block.hash}</span>
              </div>
              <div>
                <span className="text-gray-500 font-bold">Parent Hash:</span> 
                <span className="text-blue-300 ml-2">{block.parentHash}</span>
              </div>
              
              {block.transactions.length > 0 && (
                <div className="mt-4 pt-4 border-t border-gray-700">
                  <h4 className="text-white font-bold mb-3 font-sans">Transactions</h4>
                  <div className="space-y-3">
                    {block.transactions.map((tx: any) => (
                      <div key={tx.hash} className="bg-gray-900 p-4 rounded border border-gray-700">
                        <div><span className="text-gray-500">TX Hash:</span> <span className="text-green-400">{tx.hash}</span></div>
                        <div><span className="text-gray-500">From:</span> <span className="text-gray-300">{tx.from}</span></div>
                        <div><span className="text-gray-500">To:</span> <span className="text-gray-300">{tx.to}</span></div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
