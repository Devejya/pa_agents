import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

interface ReauthContextType {
  needsReauth: boolean;
  showReauthModal: () => void;
  hideReauthModal: () => void;
  checkForScopeError: (error: unknown) => boolean;
}

const ReauthContext = createContext<ReauthContextType | undefined>(undefined);

export function ReauthProvider({ children }: { children: ReactNode }) {
  const [needsReauth, setNeedsReauth] = useState(false);

  const showReauthModal = useCallback(() => {
    setNeedsReauth(true);
  }, []);

  const hideReauthModal = useCallback(() => {
    setNeedsReauth(false);
  }, []);

  /**
   * Check if an error indicates insufficient OAuth scopes.
   * If so, show the reauth modal and return true.
   */
  const checkForScopeError = useCallback((error: unknown): boolean => {
    if (!error) return false;
    
    const errorMessage = error instanceof Error ? error.message : String(error);
    
    // Check for scope-related errors
    const scopeErrorPatterns = [
      'insufficient authentication scopes',
      'ACCESS_TOKEN_SCOPE_INSUFFICIENT',
      'insufficient scopes',
      'Request had insufficient authentication',
      'Insufficient Permission',
    ];
    
    const isScopeError = scopeErrorPatterns.some(pattern => 
      errorMessage.toLowerCase().includes(pattern.toLowerCase())
    );
    
    if (isScopeError) {
      setNeedsReauth(true);
      return true;
    }
    
    return false;
  }, []);

  return (
    <ReauthContext.Provider value={{ 
      needsReauth, 
      showReauthModal, 
      hideReauthModal,
      checkForScopeError,
    }}>
      {children}
    </ReauthContext.Provider>
  );
}

export function useReauth() {
  const context = useContext(ReauthContext);
  if (context === undefined) {
    throw new Error('useReauth must be used within a ReauthProvider');
  }
  return context;
}

