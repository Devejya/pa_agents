/**
 * Login Page for Yennifer App
 * 
 * Displays Google Sign-In button and handles auth errors.
 */

import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function LoginPage() {
  const { login, isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  
  const error = searchParams.get('error');
  const deniedEmail = searchParams.get('email');

  // Redirect if already authenticated
  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      navigate('/chat');
    }
  }, [isAuthenticated, isLoading, navigate]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-violet-950 to-slate-900">
        <div className="animate-pulse text-white text-xl">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-slate-900 via-violet-950 to-slate-900 px-4">
      {/* Logo and branding */}
      <div className="text-center mb-12">
        <div className="inline-flex items-center justify-center w-20 h-20 rounded-2xl bg-gradient-to-br from-violet-500 to-purple-600 shadow-2xl shadow-violet-500/30 mb-6">
          <span className="text-4xl font-bold text-white">Y</span>
        </div>
        <h1 className="text-4xl font-bold text-white mb-3 tracking-tight">
          Yennifer
        </h1>
        <p className="text-violet-200/70 text-lg">
          Your AI Personal Assistant
        </p>
      </div>

      {/* Login card */}
      <div className="w-full max-w-md bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-8 shadow-2xl">
        <h2 className="text-2xl font-semibold text-white text-center mb-6">
          Welcome Back
        </h2>

        {/* Error messages */}
        {error === 'access_denied' && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-xl">
            <p className="text-red-300 text-center text-sm">
              <span className="font-medium">Access Denied</span>
              {deniedEmail && (
                <>
                  <br />
                  <span className="text-red-300/70">
                    {deniedEmail} is not authorized to access this application.
                  </span>
                </>
              )}
            </p>
          </div>
        )}

        {error === 'user_creation_failed' && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-xl">
            <p className="text-red-300 text-center text-sm">
              <span className="font-medium">Account Setup Failed</span>
              <br />
              <span className="text-red-300/70">
                We couldn't set up your account. Please try again or contact support.
              </span>
            </p>
          </div>
        )}

        {error && error !== 'access_denied' && error !== 'user_creation_failed' && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-xl">
            <p className="text-red-300 text-center text-sm">
              Authentication failed: {error}
            </p>
          </div>
        )}

        {/* Google Sign-In button */}
        <button
          onClick={login}
          className="w-full flex items-center justify-center gap-3 bg-white hover:bg-gray-50 text-gray-800 font-medium py-3 px-6 rounded-xl transition-all duration-200 hover:shadow-lg hover:shadow-white/10 active:scale-[0.98]"
        >
          {/* Google icon */}
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path
              fill="#4285F4"
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
            />
            <path
              fill="#34A853"
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            />
            <path
              fill="#FBBC05"
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
            />
            <path
              fill="#EA4335"
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
            />
          </svg>
          Sign in with Google
        </button>

        <p className="mt-6 text-center text-sm text-violet-200/50">
          Only authorized users can access this application.
        </p>
      </div>

      {/* Footer */}
      <p className="mt-8 text-sm text-violet-200/30">
        © 2025 Yennifer. All rights reserved.
      </p>
    </div>
  );
}

