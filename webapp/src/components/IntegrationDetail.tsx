import { useState, useEffect } from 'react';
import {
  getIntegrationDetail,
  enableScope,
  disableScope,
  enableAllScopes,
  enableIntegration,
  disableIntegration,
  type IntegrationDetail as IntegrationDetailType,
  type IntegrationScope,
} from '../services/api';

interface IntegrationDetailProps {
  integrationId: string;
  onClose: () => void;
  onUpdate: () => void;
}

export default function IntegrationDetail({
  integrationId,
  onClose,
  onUpdate,
}: IntegrationDetailProps) {
  const [integration, setIntegration] = useState<IntegrationDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [togglingScope, setTogglingScope] = useState<string | null>(null);
  const [togglingAll, setTogglingAll] = useState(false);

  useEffect(() => {
    loadIntegration();
  }, [integrationId]);

  async function loadIntegration() {
    try {
      setLoading(true);
      const data = await getIntegrationDetail(integrationId);
      setIntegration(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load integration');
    } finally {
      setLoading(false);
    }
  }

  async function handleScopeToggle(scope: IntegrationScope) {
    if (!integration) return;
    
    setTogglingScope(scope.id);
    try {
      if (scope.is_enabled) {
        const result = await disableScope(integration.id, scope.id);
        if (result.success) {
          setIntegration(prev => prev ? {
            ...prev,
            scopes: prev.scopes.map(s => 
              s.id === scope.id ? { ...s, is_enabled: false } : s
            ),
          } : null);
        }
      } else {
        const result = await enableScope(integration.id, scope.id);
        if (result.needs_auth && result.auth_url) {
          window.location.href = result.auth_url;
          return;
        }
        if (result.success) {
          setIntegration(prev => prev ? {
            ...prev,
            scopes: prev.scopes.map(s => 
              s.id === scope.id ? { ...s, is_enabled: result.is_enabled, is_granted: result.is_granted } : s
            ),
          } : null);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle scope');
    } finally {
      setTogglingScope(null);
    }
  }

  async function handleEnableAll() {
    if (!integration) return;
    
    setTogglingAll(true);
    try {
      const result = await enableAllScopes(integration.id);
      if (result.needs_auth && result.auth_url) {
        window.location.href = result.auth_url;
        return;
      }
      if (result.success) {
        await loadIntegration();
        onUpdate();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to enable all scopes');
    } finally {
      setTogglingAll(false);
    }
  }

  async function handleMasterToggle() {
    if (!integration) return;
    
    setTogglingAll(true);
    try {
      if (integration.is_enabled) {
        const result = await disableIntegration(integration.id);
        if (result.success) {
          setIntegration(prev => prev ? { ...prev, is_enabled: false } : null);
          onUpdate();
        }
      } else {
        const result = await enableIntegration(integration.id);
        if (result.needs_auth && result.auth_url) {
          window.location.href = result.auth_url;
          return;
        }
        if (result.success) {
          await loadIntegration();
          onUpdate();
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle integration');
    } finally {
      setTogglingAll(false);
    }
  }

  // Check if all scopes are enabled
  const allScopesEnabled = integration?.scopes.every(s => s.is_enabled) ?? false;

  return (
    <div 
      className="fixed inset-0 bg-black/50 dark:bg-black/70 flex items-end sm:items-center justify-center z-50 p-0 sm:p-4" 
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-zinc-900 rounded-t-2xl sm:rounded-2xl shadow-xl w-full sm:max-w-lg max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-4 sm:p-6 border-b border-gray-100 dark:border-zinc-800 shrink-0">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              {integration && (
                <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-xl bg-gray-100 dark:bg-zinc-800 flex items-center justify-center">
                  <IntegrationIcon iconId={integration.icon_url || integration.id} />
                </div>
              )}
              <div>
                <h2 className="text-lg sm:text-xl font-bold text-gray-900 dark:text-gray-100">
                  {integration?.name || 'Loading...'}
                </h2>
                {integration && (
                  <p className="text-gray-500 dark:text-gray-400 text-sm">
                    {integration.is_enabled ? 'Enabled' : 'Disabled'}
                  </p>
                )}
              </div>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors p-1"
            >
              <CloseIcon className="w-5 h-5 sm:w-6 sm:h-6" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6">
          {/* Loading */}
          {loading && (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-yennifer-700 dark:border-yennifer-400"></div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/50 rounded-lg p-3 text-red-700 dark:text-red-400 text-sm mb-4">
              {error}
            </div>
          )}

          {/* Integration content */}
          {!loading && integration && (
            <div className="space-y-6">
              {/* Master toggle */}
              <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-zinc-800 rounded-xl">
                <div>
                  <p className="font-medium text-gray-900 dark:text-gray-100">
                    Enable {integration.name}
                  </p>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Turn on all permissions for this integration
                  </p>
                </div>
                <button
                  onClick={handleMasterToggle}
                  disabled={togglingAll}
                  className={`
                    toggle-switch relative inline-flex h-7 w-12 items-center rounded-full transition-colors
                    ${togglingAll ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
                    ${integration.is_enabled 
                      ? 'bg-emerald-500' 
                      : 'bg-gray-300 dark:bg-zinc-600'
                    }
                  `}
                  aria-label={integration.is_enabled ? 'Disable' : 'Enable'}
                >
                  <span
                    className={`
                      inline-block h-5 w-5 transform rounded-full bg-white shadow-sm transition-transform
                      ${integration.is_enabled ? 'translate-x-6' : 'translate-x-1'}
                    `}
                  />
                </button>
              </div>

              {/* Permissions section */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                    Permissions
                  </h3>
                  {integration.scopes.length > 1 && (
                    <button
                      onClick={handleEnableAll}
                      disabled={togglingAll || allScopesEnabled}
                      className={`
                        text-xs font-medium px-3 py-1 rounded-full transition-colors
                        ${allScopesEnabled 
                          ? 'text-gray-400 dark:text-gray-600 cursor-not-allowed'
                          : 'text-yennifer-600 dark:text-yennifer-400 hover:bg-yennifer-50 dark:hover:bg-yennifer-900/20'
                        }
                      `}
                    >
                      Enable all
                    </button>
                  )}
                </div>

                <div className="space-y-3">
                  {integration.scopes.map((scope) => (
                    <ScopeToggle
                      key={scope.id}
                      scope={scope}
                      isToggling={togglingScope === scope.id}
                      onToggle={() => handleScopeToggle(scope)}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

interface ScopeToggleProps {
  scope: IntegrationScope;
  isToggling: boolean;
  onToggle: () => void;
}

function ScopeToggle({ scope, isToggling, onToggle }: ScopeToggleProps) {
  return (
    <div className="flex items-start gap-3 p-3 rounded-lg bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-700">
      {/* Toggle */}
      <button
        onClick={onToggle}
        disabled={isToggling}
        className={`
          toggle-switch relative inline-flex h-5 w-9 items-center rounded-full transition-colors shrink-0 mt-0.5
          ${isToggling ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
          ${scope.is_enabled 
            ? 'bg-emerald-500' 
            : 'bg-gray-300 dark:bg-zinc-600'
          }
        `}
        aria-label={scope.is_enabled ? 'Disable scope' : 'Enable scope'}
      >
        <span
          className={`
            inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform
            ${scope.is_enabled ? 'translate-x-4' : 'translate-x-0.5'}
          `}
        />
      </button>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="font-medium text-gray-900 dark:text-gray-100 text-sm">
            {scope.name}
          </p>
          {scope.is_required && (
            <span className="text-xs px-1.5 py-0.5 bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 rounded">
              Required
            </span>
          )}
          {scope.is_enabled && !scope.is_granted && (
            <span className="text-xs px-1.5 py-0.5 bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400 rounded">
              Needs OAuth
            </span>
          )}
        </div>
        <p className="text-gray-500 dark:text-gray-400 text-xs mt-0.5">
          {scope.description}
        </p>
      </div>
    </div>
  );
}

// Icons
function IntegrationIcon({ iconId }: { iconId: string }) {
  switch (iconId) {
    case 'gmail':
      return <GmailIcon className="w-6 h-6" />;
    case 'calendar':
      return <CalendarIcon className="w-6 h-6" />;
    case 'contacts':
      return <ContactsIcon className="w-6 h-6" />;
    case 'drive':
      return <DriveIcon className="w-6 h-6" />;
    case 'sheets':
      return <SheetsIcon className="w-6 h-6" />;
    case 'docs':
      return <DocsIcon className="w-6 h-6" />;
    case 'slides':
      return <SlidesIcon className="w-6 h-6" />;
    default:
      return <DefaultIcon className="w-6 h-6" />;
  }
}

function CloseIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

function GmailIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none">
      <path d="M4 6L12 12L20 6" stroke="#EA4335" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
      <rect x="2" y="4" width="20" height="16" rx="2" stroke="#4285F4" strokeWidth="2"/>
    </svg>
  );
}

function CalendarIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none">
      <rect x="3" y="4" width="18" height="18" rx="2" stroke="#4285F4" strokeWidth="2"/>
      <path d="M3 10H21" stroke="#4285F4" strokeWidth="2"/>
      <path d="M8 2V6" stroke="#4285F4" strokeWidth="2" strokeLinecap="round"/>
      <path d="M16 2V6" stroke="#4285F4" strokeWidth="2" strokeLinecap="round"/>
    </svg>
  );
}

function ContactsIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="8" r="4" stroke="#4285F4" strokeWidth="2"/>
      <path d="M4 20C4 16.6863 7.58172 14 12 14C16.4183 14 20 16.6863 20 20" stroke="#34A853" strokeWidth="2" strokeLinecap="round"/>
    </svg>
  );
}

function DriveIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none">
      <path d="M8 4L3 13H10L15 22L20 13L12 4H8Z" stroke="#4285F4" strokeWidth="2" strokeLinejoin="round"/>
    </svg>
  );
}

function SheetsIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none">
      <rect x="4" y="3" width="16" height="18" rx="2" stroke="#34A853" strokeWidth="2"/>
      <path d="M4 9H20" stroke="#34A853" strokeWidth="2"/>
      <path d="M12 9V21" stroke="#34A853" strokeWidth="2"/>
    </svg>
  );
}

function DocsIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none">
      <rect x="4" y="3" width="16" height="18" rx="2" stroke="#4285F4" strokeWidth="2"/>
      <path d="M8 8H16" stroke="#4285F4" strokeWidth="2" strokeLinecap="round"/>
      <path d="M8 12H16" stroke="#4285F4" strokeWidth="2" strokeLinecap="round"/>
      <path d="M8 16H12" stroke="#4285F4" strokeWidth="2" strokeLinecap="round"/>
    </svg>
  );
}

function SlidesIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none">
      <rect x="3" y="5" width="18" height="14" rx="2" stroke="#FBBC05" strokeWidth="2"/>
      <circle cx="12" cy="12" r="3" stroke="#FBBC05" strokeWidth="2"/>
    </svg>
  );
}

function DefaultIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 4a2 2 0 114 0v1a1 1 0 001 1h3a1 1 0 011 1v3a1 1 0 01-1 1h-1a2 2 0 100 4h1a1 1 0 011 1v3a1 1 0 01-1 1h-3a1 1 0 01-1-1v-1a2 2 0 10-4 0v1a1 1 0 01-1 1H7a1 1 0 01-1-1v-3a1 1 0 00-1-1H4a2 2 0 110-4h1a1 1 0 001-1V7a1 1 0 011-1h3a1 1 0 001-1V4z" />
    </svg>
  );
}

