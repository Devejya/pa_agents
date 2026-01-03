import { useState, useEffect } from 'react';
import { 
  getIntegrations, 
  enableIntegration, 
  disableIntegration,
  type Integration 
} from '../services/api';
import { useReauth } from '../contexts/ReauthContext';
import IntegrationCard from '../components/IntegrationCard';
import IntegrationDetail from '../components/IntegrationDetail';

export default function IntegrationsPage() {
  const { checkForScopeError } = useReauth();
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedIntegration, setSelectedIntegration] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  // Check for OAuth callback success/error
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const success = params.get('success');
    const oauthError = params.get('error');
    const integrationId = params.get('integration');

    if (success === 'true' && integrationId) {
      // Reload integrations after successful OAuth
      loadIntegrations();
      // Clean up URL
      window.history.replaceState({}, '', window.location.pathname);
    } else if (oauthError) {
      setError(`OAuth error: ${oauthError}`);
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, []);

  async function loadIntegrations() {
    try {
      setLoading(true);
      const data = await getIntegrations();
      setIntegrations(data);
      setError(null);
    } catch (err) {
      // Check for scope error and show reauth modal if needed
      if (!checkForScopeError(err)) {
        setError(err instanceof Error ? err.message : 'Failed to load integrations');
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadIntegrations();
  }, []);

  async function handleToggle(integrationId: string, currentEnabled: boolean) {
    setTogglingId(integrationId);
    try {
      if (currentEnabled) {
        // Disable
        const result = await disableIntegration(integrationId);
        if (result.success) {
          setIntegrations(prev => 
            prev.map(i => i.id === integrationId ? { ...i, is_enabled: false } : i)
          );
        }
      } else {
        // Enable
        const result = await enableIntegration(integrationId);
        if (result.needs_auth && result.auth_url) {
          // Redirect to OAuth
          window.location.href = result.auth_url;
          return;
        }
        if (result.success) {
          setIntegrations(prev => 
            prev.map(i => i.id === integrationId ? { ...i, is_enabled: true } : i)
          );
        }
      }
    } catch (err) {
      // Check for scope error and show reauth modal if needed
      if (!checkForScopeError(err)) {
        setError(err instanceof Error ? err.message : 'Failed to toggle integration');
      }
    } finally {
      setTogglingId(null);
    }
  }

  function handleManagePermissions(integrationId: string) {
    setSelectedIntegration(integrationId);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header - hidden on mobile since Layout shows a header */}
      <header className="hidden md:flex bg-white dark:bg-zinc-900 border-b border-gray-200 dark:border-zinc-800 px-4 lg:px-6 py-3 lg:py-4 items-center justify-between shrink-0">
        <h1 className="text-lg lg:text-xl font-semibold text-gray-900 dark:text-gray-100">Integrations</h1>
        <div className="w-8 h-8 lg:w-9 lg:h-9 bg-yennifer-600 rounded-full flex items-center justify-center">
          <span className="text-white text-sm font-bold">Y</span>
        </div>
      </header>

      {/* Mobile sub-header */}
      <div className="md:hidden bg-white dark:bg-zinc-900 border-b border-gray-200 dark:border-zinc-800 px-4 py-2 flex items-center justify-between shrink-0">
        <h1 className="text-base font-semibold text-gray-900 dark:text-gray-100">Integrations</h1>
        <div className="w-7 h-7 bg-yennifer-600 rounded-full flex items-center justify-center">
          <span className="text-white text-xs font-bold">Y</span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3 sm:p-4 md:p-6">
        <div className="max-w-4xl mx-auto">
          {/* Page title */}
          <div className="flex items-center gap-2 sm:gap-3 mb-2">
            <IntegrationsIcon className="w-5 h-5 sm:w-7 sm:h-7 text-gray-700 dark:text-gray-300" />
            <h2 className="text-lg sm:text-2xl font-bold text-gray-900 dark:text-gray-100">Integrations</h2>
          </div>
          <p className="text-gray-500 dark:text-gray-400 text-sm sm:text-base mb-4 sm:mb-6">
            Connect your accounts to unlock Yennifer's full capabilities
          </p>

          {/* Error state */}
          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/50 rounded-lg p-3 sm:p-4 text-red-700 dark:text-red-400 text-sm mb-4">
              {error}
              <button 
                onClick={() => setError(null)}
                className="ml-2 underline hover:no-underline"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* Loading state */}
          {loading && (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-yennifer-700 dark:border-yennifer-400"></div>
            </div>
          )}

          {/* Integrations list */}
          {!loading && integrations.length > 0 && (
            <div className="space-y-3 sm:space-y-4">
              {integrations.map((integration) => (
                <IntegrationCard
                  key={integration.id}
                  integration={integration}
                  isToggling={togglingId === integration.id}
                  onToggle={(enabled) => handleToggle(integration.id, enabled)}
                  onManagePermissions={() => handleManagePermissions(integration.id)}
                />
              ))}
            </div>
          )}

          {/* Empty state */}
          {!loading && integrations.length === 0 && !error && (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              <IntegrationsIcon className="w-10 h-10 sm:w-12 sm:h-12 mx-auto mb-4 text-gray-300 dark:text-gray-600" />
              <p className="text-sm sm:text-base">No integrations available</p>
            </div>
          )}
        </div>
      </div>

      {/* Integration detail modal */}
      {selectedIntegration && (
        <IntegrationDetail
          integrationId={selectedIntegration}
          onClose={() => setSelectedIntegration(null)}
          onUpdate={() => loadIntegrations()}
        />
      )}
    </div>
  );
}

function IntegrationsIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 4a2 2 0 114 0v1a1 1 0 001 1h3a1 1 0 011 1v3a1 1 0 01-1 1h-1a2 2 0 100 4h1a1 1 0 011 1v3a1 1 0 01-1 1h-3a1 1 0 01-1-1v-1a2 2 0 10-4 0v1a1 1 0 01-1 1H7a1 1 0 01-1-1v-3a1 1 0 00-1-1H4a2 2 0 110-4h1a1 1 0 001-1V7a1 1 0 011-1h3a1 1 0 001-1V4z" />
    </svg>
  );
}

