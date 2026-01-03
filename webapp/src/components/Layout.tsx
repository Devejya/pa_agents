import { useState, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import ReauthModal from './ReauthModal';
import { useReauth } from '../contexts/ReauthContext';

export default function Layout() {
  const { needsReauth, hideReauthModal } = useReauth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  // Detect screen size
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
      // Auto-close sidebar when switching to desktop
      if (window.innerWidth >= 768) {
        setSidebarOpen(false);
      }
    };

    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // Close sidebar when clicking outside on mobile
  const handleOverlayClick = () => {
    if (isMobile) {
      setSidebarOpen(false);
    }
  };

  return (
    <div className="flex h-dvh bg-gray-50 dark:bg-zinc-950 overflow-hidden">
      {/* Mobile overlay */}
      {isMobile && sidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/50 dark:bg-black/70 z-40 transition-opacity"
          onClick={handleOverlayClick}
        />
      )}

      {/* Sidebar */}
      <div
        className={`
          ${isMobile 
            ? `fixed inset-y-0 left-0 z-50 transform transition-transform duration-300 ease-in-out ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`
            : 'relative'
          }
        `}
      >
        <Sidebar 
          onClose={() => setSidebarOpen(false)} 
          isMobile={isMobile}
        />
      </div>

      {/* Main content */}
      <main className="flex-1 overflow-hidden flex flex-col min-w-0">
        {/* Mobile header with menu button */}
        {isMobile && (
          <div className="bg-white dark:bg-zinc-900 border-b border-gray-200 dark:border-zinc-800 px-4 py-3 flex items-center gap-3 shrink-0">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-2 -ml-2 rounded-lg hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors"
              aria-label="Open menu"
            >
              <MenuIcon className="w-6 h-6 text-gray-600 dark:text-gray-400" />
            </button>
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-yennifer-700 rounded-full flex items-center justify-center">
                <span className="text-white text-sm font-bold">Y</span>
              </div>
              <span className="font-semibold text-gray-900 dark:text-gray-100">Yennifer</span>
            </div>
          </div>
        )}
        <div className="flex-1 overflow-hidden">
          <Outlet />
        </div>
      </main>

      {/* Re-authentication modal */}
      <ReauthModal isOpen={needsReauth} onClose={hideReauthModal} />
    </div>
  );
}

function MenuIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
    </svg>
  );
}
