/**
 * Authentication Context for Yennifer App
 * 
 * Provides user authentication state and methods throughout the app.
 */

import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';

// API base URL
const API_URL = import.meta.env.VITE_YENNIFER_API_URL || (import.meta.env.PROD ? '' : 'http://localhost:8000');

interface User {
  email: string;
  name: string;
  picture?: string;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: () => void;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Token storage keys
const TOKEN_KEY = 'yennifer_auth_token';

/**
 * Get the stored auth token
 */
export function getAuthToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

/**
 * Set the auth token
 */
export function setAuthToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

/**
 * Clear the auth token
 */
export function clearAuthToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

/**
 * Get auth headers for API requests
 */
export function getAuthHeaders(): HeadersInit {
  const token = getAuthToken();
  if (token) {
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    };
  }
  return {
    'Content-Type': 'application/json',
  };
}

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  /**
   * Check if user is authenticated
   */
  const checkAuth = async () => {
    const token = getAuthToken();
    
    if (!token) {
      setUser(null);
      setIsLoading(false);
      return;
    }

    try {
      const response = await fetch(`${API_URL}/api/v1/auth/me`, {
        headers: getAuthHeaders(),
      });

      if (response.ok) {
        const data = await response.json();
        setUser({
          email: data.email,
          name: data.name,
          picture: data.picture,
        });
      } else {
        // Token is invalid or expired
        clearAuthToken();
        setUser(null);
      }
    } catch (error) {
      console.error('Auth check failed:', error);
      clearAuthToken();
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Initiate login flow
   */
  const login = () => {
    // Redirect to backend login endpoint
    // The backend will redirect to Google OAuth
    const currentPath = window.location.pathname;
    const loginUrl = `${API_URL}/api/v1/auth/login?redirect_uri=${encodeURIComponent(window.location.origin + currentPath)}`;
    window.location.href = loginUrl;
  };

  /**
   * Log out the user
   */
  const logout = async () => {
    try {
      await fetch(`${API_URL}/api/v1/auth/logout`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
    } catch (error) {
      console.error('Logout request failed:', error);
    }
    
    clearAuthToken();
    setUser(null);
  };

  // Check for token in URL (after OAuth callback)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');
    
    if (token) {
      // Store the token and clean up the URL
      setAuthToken(token);
      
      // Remove token from URL
      const newUrl = window.location.pathname;
      window.history.replaceState({}, '', newUrl);
    }
  }, []);

  // Check auth status on mount and when token changes
  useEffect(() => {
    checkAuth();
  }, []);

  const value: AuthContextType = {
    user,
    isLoading,
    isAuthenticated: !!user,
    login,
    logout,
    checkAuth,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * Hook to use auth context
 */
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

