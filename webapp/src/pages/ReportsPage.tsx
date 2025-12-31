// Placeholder page for Research Reports
// Functionality to be implemented later

const mockReports = [
  {
    id: '1',
    title: 'Analysis of Magical Energy Fluctuations in Cintra',
    category: 'Magical Research',
    description: 'Detailed study of recent magical disturbances detected in the northern regions. Patterns suggest potential portal activity.',
    wordCount: 3450,
    date: '2025-12-26',
  },
  {
    id: '2',
    title: 'Historical Review: The Conjunction of the Spheres',
    category: 'Historical Analysis',
    description: 'Comprehensive analysis of historical records regarding the Conjunction and its implications for current events.',
    wordCount: 5200,
    date: '2025-12-24',
  },
  {
    id: '3',
    title: 'Elder Blood Lineage Tracking',
    category: 'Genealogy',
    description: 'Investigation into known carriers of Elder Blood and their current locations. Updated family tree included.',
    wordCount: 2800,
    date: '2025-12-22',
  },
];

function getCategoryColor(category: string) {
  const colors: Record<string, string> = {
    'Magical Research': 'bg-purple-100 text-purple-700',
    'Historical Analysis': 'bg-blue-100 text-blue-700',
    'Genealogy': 'bg-emerald-100 text-emerald-700',
  };
  return colors[category] || 'bg-gray-100 text-gray-700';
}

export default function ReportsPage() {
  return (
    <div className="flex flex-col h-full">
      {/* Header - hidden on mobile since Layout shows a header */}
      <header className="hidden md:flex bg-white border-b border-gray-200 px-4 lg:px-6 py-3 lg:py-4 items-center justify-between shrink-0">
        <h1 className="text-lg lg:text-xl font-semibold text-gray-900">Research Reports</h1>
        <div className="w-8 h-8 lg:w-9 lg:h-9 bg-yennifer-600 rounded-full flex items-center justify-center">
          <span className="text-white text-sm font-bold">U</span>
        </div>
      </header>

      {/* Mobile sub-header */}
      <div className="md:hidden bg-white border-b border-gray-200 px-4 py-2 flex items-center justify-between shrink-0">
        <h1 className="text-base font-semibold text-gray-900">Reports</h1>
        <div className="w-7 h-7 bg-yennifer-600 rounded-full flex items-center justify-center">
          <span className="text-white text-xs font-bold">U</span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3 sm:p-4 md:p-6">
        <div className="max-w-4xl mx-auto">
          {/* Page title */}
          <div className="flex items-center gap-2 sm:gap-3 mb-2">
            <ReportsIcon className="w-5 h-5 sm:w-7 sm:h-7 text-gray-700" />
            <h2 className="text-lg sm:text-2xl font-bold text-gray-900">Research Reports</h2>
          </div>
          <p className="text-gray-500 text-sm sm:text-base mb-4 sm:mb-6">Detailed research and analysis compiled by Yennifer</p>

          {/* Reports list */}
          <div className="space-y-3 sm:space-y-4">
            {mockReports.map((report) => (
              <div
                key={report.id}
                className="bg-white border border-gray-200 rounded-xl p-3 sm:p-5 hover:shadow-md transition-shadow cursor-pointer"
              >
                <div className="flex items-start justify-between gap-3 sm:gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-2">
                      <span className={`px-2 sm:px-3 py-0.5 sm:py-1 rounded-full text-xs font-medium whitespace-nowrap ${getCategoryColor(report.category)}`}>
                        {report.category}
                      </span>
                      <span className="text-xs sm:text-sm text-gray-500">{report.wordCount.toLocaleString()} words</span>
                    </div>
                    <h3 className="font-semibold text-gray-900 text-sm sm:text-lg line-clamp-2">{report.title}</h3>
                    <p className="text-gray-500 text-xs sm:text-base mt-1 sm:mt-2 line-clamp-2 sm:line-clamp-none">{report.description}</p>
                    <div className="flex items-center gap-2 mt-2 sm:mt-3 text-xs sm:text-sm text-gray-500">
                      <CalendarIcon className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                      <span>{report.date}</span>
                    </div>
                  </div>
                  <button className="text-gray-400 hover:text-gray-600 shrink-0 p-1">
                    <EyeIcon className="w-4 h-4 sm:w-5 sm:h-5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Help button */}
      <button className="fixed bottom-4 sm:bottom-6 right-4 sm:right-6 w-9 h-9 sm:w-10 sm:h-10 bg-gray-800 text-white rounded-full flex items-center justify-center shadow-lg hover:bg-gray-700 transition-colors z-30 text-sm sm:text-base">
        ?
      </button>
    </div>
  );
}

function ReportsIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );
}

function CalendarIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
    </svg>
  );
}

function EyeIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
    </svg>
  );
}
