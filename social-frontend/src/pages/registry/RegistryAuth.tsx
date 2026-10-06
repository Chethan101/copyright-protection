import { Shield } from 'lucide-react';

/**
 * Shown when VibeSocial could not open your registry session.
 *
 * There is deliberately no username/password form: the registry account is the one
 * VibeSocial signs you into automatically, under your VibeSocial username. Signing in
 * by hand to some other registry account would register your content under a name that
 * does not match your VibeSocial account -- and then block you from posting your own work.
 */
export default function RegistryAuth({ message, onRetry, busy }: { message: string; onRetry: () => void; busy: boolean }) {
  return (
    <div className="flex items-center justify-center py-10">
      <div className="glass p-6 sm:p-10 rounded-2xl w-full max-w-md shadow-2xl relative overflow-hidden text-center">
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-teal-400 to-indigo-500"></div>
        <div className="flex flex-col items-center mb-5">
          <div className="bg-teal-500/20 p-3 rounded-full text-teal-400 mb-3">
            <Shield className="w-7 h-7" />
          </div>
          <h2 className="text-xl sm:text-2xl font-bold text-white">Couldn't connect to CopyGuard Registry</h2>
          <p className="text-sm text-gray-400 mt-3">{message}</p>
        </div>
        <button
          onClick={onRetry}
          disabled={busy}
          className="w-full bg-gradient-to-r from-teal-500 to-indigo-500 hover:from-teal-400 hover:to-indigo-400 text-white font-semibold py-3 rounded-lg transition-all disabled:opacity-60"
        >
          {busy ? 'Connecting...' : 'Try again'}
        </button>
      </div>
    </div>
  );
}
