import { type Integration } from '../services/api';

interface IntegrationCardProps {
  integration: Integration;
  isToggling: boolean;
  onToggle: (currentEnabled: boolean) => void;
  onManagePermissions: () => void;
}

export default function IntegrationCard({
  integration,
  isToggling,
  onToggle,
  onManagePermissions,
}: IntegrationCardProps) {
  return (
    <div className="bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-700 rounded-xl p-4 sm:p-5 transition-all hover:shadow-md dark:hover:border-zinc-600">
      <div className="flex items-start gap-3 sm:gap-4">
        {/* Integration Icon */}
        <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-xl bg-gray-100 dark:bg-zinc-800 flex items-center justify-center shrink-0">
          <IntegrationIcon iconId={integration.icon_url || integration.id} />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2 mb-1">
            <h3 className="text-base sm:text-lg font-semibold text-gray-900 dark:text-gray-100 truncate">
              {integration.name}
            </h3>
            
            {/* Toggle Switch */}
            <button
              onClick={() => onToggle(integration.is_enabled)}
              disabled={isToggling}
              className={`
                relative inline-flex h-6 w-11 items-center rounded-full transition-colors
                ${isToggling ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
                ${integration.is_enabled 
                  ? 'bg-emerald-500' 
                  : 'bg-gray-300 dark:bg-zinc-600'
                }
              `}
              aria-label={integration.is_enabled ? 'Disable integration' : 'Enable integration'}
            >
              <span
                className={`
                  inline-block h-5 w-5 transform rounded-full bg-white shadow-sm transition-transform
                  ${integration.is_enabled ? 'translate-x-5' : 'translate-x-0.5'}
                `}
              />
              {isToggling && (
                <span className="absolute inset-0 flex items-center justify-center">
                  <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                </span>
              )}
            </button>
          </div>

          <p className="text-gray-600 dark:text-gray-400 text-sm mb-2 line-clamp-1">
            {integration.description}
          </p>

          <div className="flex items-center justify-between">
            <p className="text-gray-500 dark:text-gray-500 text-xs sm:text-sm">
              {integration.capability_summary}
            </p>

            <button
              onClick={onManagePermissions}
              className="text-yennifer-600 dark:text-yennifer-400 hover:text-yennifer-700 dark:hover:text-yennifer-300 text-xs sm:text-sm font-medium flex items-center gap-1 shrink-0"
            >
              Manage permissions
              <ChevronRightIcon className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function IntegrationIcon({ iconId }: { iconId: string }) {
  // Map icon IDs to SVG icons
  switch (iconId) {
    case 'gmail':
      return <GmailIcon className="w-6 h-6 sm:w-7 sm:h-7" />;
    case 'calendar':
      return <CalendarIcon className="w-6 h-6 sm:w-7 sm:h-7" />;
    case 'contacts':
      return <ContactsIcon className="w-6 h-6 sm:w-7 sm:h-7" />;
    case 'drive':
      return <DriveIcon className="w-6 h-6 sm:w-7 sm:h-7" />;
    case 'sheets':
      return <SheetsIcon className="w-6 h-6 sm:w-7 sm:h-7" />;
    case 'docs':
      return <DocsIcon className="w-6 h-6 sm:w-7 sm:h-7" />;
    case 'slides':
      return <SlidesIcon className="w-6 h-6 sm:w-7 sm:h-7" />;
    default:
      return <DefaultIcon className="w-6 h-6 sm:w-7 sm:h-7" />;
  }
}

// Icons
function ChevronRightIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
    </svg>
  );
}

function GmailIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none">
      <path d="M4 6L12 12L20 6" stroke="#EA4335" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
      <rect x="2" y="4" width="20" height="16" rx="2" stroke="#4285F4" strokeWidth="2"/>
      <path d="M2 6L12 14L22 6" stroke="#34A853" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
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
      <circle cx="12" cy="16" r="2" fill="#EA4335"/>
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
      <path d="M3 13H21" stroke="#FBBC05" strokeWidth="2"/>
      <path d="M10 13L15 22H21L16 13" stroke="#34A853" strokeWidth="2" strokeLinejoin="round"/>
    </svg>
  );
}

function SheetsIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none">
      <rect x="4" y="3" width="16" height="18" rx="2" stroke="#34A853" strokeWidth="2"/>
      <path d="M4 9H20" stroke="#34A853" strokeWidth="2"/>
      <path d="M4 15H20" stroke="#34A853" strokeWidth="2"/>
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

