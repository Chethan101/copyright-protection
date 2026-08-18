import { useState, useEffect } from 'react';
import api from '../api';
import { Box, Hash, Clock, ArrowRight } from 'lucide-react';

export default function Explorer() {
  const [blocks, setBlocks] = useState<any[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const fetchBlocks = async () => {
      try {
        const res = await api.get('/blockchain/blocks');
        setBlocks(res.data.blocks);
      } catch {
        console.error("Failed to fetch blocks");
      } finally {
        setLoaded(true);
      }
    };
    fetchBlocks();
    const interval = setInterval(fetchBlocks, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold mb-2">Blockchain Explorer</h1>
        <p className="text-gray-400">View real-time Ganache network blocks and transactions.</p>
      </div>

      <div className="space-y-6">
        {!loaded ? (
          <div className="text-center py-20 text-gray-500">Loading blockchain data...</div>
        ) : blocks.length === 0 ? (
          <div className="text-center py-20 text-gray-500">
            No blockchain data available. Is the local Ganache node running?
          </div>
        ) : (
          blocks.map((block) => (
            <div key={block.number} className="glass rounded-xl overflow-hidden shadow-lg border border-gray-800">
              <div className="bg-gray-800/80 p-4 border-b border-gray-700 flex justify-between items-center">
                <div className="flex items-center gap-3">
                  <div className="bg-indigo-500/20 p-2 rounded-lg">
                    <Box className="w-5 h-5 text-indigo-400" />
                  </div>
                  <div>
                    <h3 className="font-bold">Block #{block.number}</h3>
                    <div className="flex items-center gap-1 text-xs text-gray-400 mt-1">
                      <Clock className="w-3 h-3" />
                      {new Date(block.timestamp * 1000).toLocaleString()}
                    </div>
                  </div>
                </div>
                <div className="bg-gray-900 px-3 py-1 rounded-full text-xs font-mono text-gray-400 border border-gray-700">
                  {block.transactions.length} Txn(s)
                </div>
              </div>

              <div className="p-4 space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-500 block mb-1">Block Hash</span>
                    <span className="font-mono text-teal-400 break-all">{block.hash}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 block mb-1">Parent Hash</span>
                    <span className="font-mono text-gray-400 break-all">{block.parentHash}</span>
                  </div>
                </div>

                {block.transactions.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-gray-800/50">
                    <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                      <Hash className="w-4 h-4 text-indigo-400" /> Transactions
                    </h4>
                    <div className="space-y-3">
                      {block.transactions.map((tx: any) => (
                        <div key={tx.hash} className="bg-gray-900/50 p-3 rounded-lg text-sm border border-gray-800">
                          <div className="font-mono text-indigo-300 break-all mb-2">{tx.hash}</div>
                          <div className="flex items-center gap-2 text-xs font-mono text-gray-500">
                            <span className="truncate w-32" title={tx.from}>{tx.from}</span>
                            <ArrowRight className="w-3 h-3" />
                            <span className="truncate w-32" title={tx.to}>{tx.to}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
