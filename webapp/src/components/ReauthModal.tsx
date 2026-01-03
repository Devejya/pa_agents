import { useAuth } from '../contexts/AuthContext';

interface ReauthModalProps {
  isOpen: boolean;
  onClose?: () => void;
}

export default function ReauthModal({ isOpen, onClose }: ReauthModalProps) {
  const { logout } = useAuth();

  if (!isOpen) return null;

  const handleSignOut = async () => {
    await logout();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      
      {/* Modal */}
      <div className="relative bg-white dark:bg-zinc-900 rounded-2xl shadow-2xl max-w-md w-full mx-4 p-6 sm:p-8 border border-gray-200 dark:border-zinc-700">
        {/* Icon */}
        <div className="flex justify-center mb-6">
          <div className="w-16 h-16 rounded-full bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
            <RefreshIcon className="w-8 h-8 text-amber-600 dark:text-amber-400" />
          </div>
        </div>

        {/* Title */}
        <h2 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100 text-center mb-3">
          Re-authentication Required
        </h2>

        {/* Description */}
        <p className="text-gray-600 dark:text-gray-400 text-center mb-6 leading-relaxed">
          We've updated Yennifer's integration system to give you more control over your data. 
          Please sign out and sign back in to restore full functionality.
        </p>

        {/* What's new section */}
        <div className="bg-gray-50 dark:bg-zinc-800 rounded-xl p-4 mb-6">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
            What's new:
          </h3>
          <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1.5">
            <li className="flex items-start gap-2">
              <CheckIcon className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
              <span>Control which integrations Yennifer can access</span>
            </li>
            <li className="flex items-start gap-2">
              <CheckIcon className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
              <span>Enable or disable Gmail, Calendar, Drive, and more</span>
            </li>
            <li className="flex items-start gap-2">
              <CheckIcon className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
              <span>Granular permission controls for each service</span>
            </li>
          </ul>
        </div>

        {/* Buttons */}
        <div className="flex flex-col gap-3">
          <button
            onClick={handleSignOut}
            className="w-full py-3 px-4 bg-yennifer-600 hover:bg-yennifer-700 text-white font-semibold rounded-xl transition-colors flex items-center justify-center gap-2"
          >
            <LogoutIcon className="w-5 h-5" />
            Sign Out & Re-authenticate
          </button>
          
          {onClose && (
            <button
              onClick={onClose}
              className="w-full py-3 px-4 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 font-medium transition-colors text-sm"
            >
              Remind me later
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function RefreshIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  );
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
    </svg>
  );
}

function LogoutIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
    </svg>
  );
}

