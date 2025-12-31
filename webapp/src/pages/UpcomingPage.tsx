// Placeholder page for Upcoming Items
// Functionality to be implemented later

const mockItems = [
  {
    id: '1',
    title: 'Lodge of Sorceresses Meeting',
    type: 'meeting',
    date: '2025-12-28',
    time: '14:00',
    location: 'Aretuza',
    attendees: ['Philippa', 'Triss', 'Margarita'],
  },
  {
    id: '2',
    title: 'Portal Spell Research Deadline',
    type: 'deadline',
    date: '2025-12-29',
    time: '23:59',
  },
  {
    id: '3',
    title: 'Council of Mages Assembly',
    type: 'event',
    date: '2026-01-01',
    time: '10:00',
    location: 'Oxenfurt',
    attendees: ['Vilgefortz', 'Tissaia', 'Stregobor'],
  },
];

function getTypeBadge(type: string) {
  const colors: Record<string, string> = {
    meeting: 'bg-blue-100 text-blue-700',
    deadline: 'bg-red-100 text-red-700',
    event: 'bg-emerald-100 text-emerald-700',
  };
  return colors[type] || 'bg-gray-100 text-gray-700';
}

export default function UpcomingPage() {
  return (
    <div className="flex flex-col h-full">
      {/* Header - hidden on mobile since Layout shows a header */}
      <header className="hidden md:flex bg-white border-b border-gray-200 px-4 lg:px-6 py-3 lg:py-4 items-center justify-between shrink-0">
        <h1 className="text-lg lg:text-xl font-semibold text-gray-900">Upcoming Items</h1>
        <div className="w-8 h-8 lg:w-9 lg:h-9 bg-yennifer-600 rounded-full flex items-center justify-center">
          <span className="text-white text-sm font-bold">U</span>
        </div>
      </header>

      {/* Mobile sub-header */}
      <div className="md:hidden bg-white border-b border-gray-200 px-4 py-2 flex items-center justify-between shrink-0">
        <h1 className="text-base font-semibold text-gray-900">Upcoming</h1>
        <div className="w-7 h-7 bg-yennifer-600 rounded-full flex items-center justify-center">
          <span className="text-white text-xs font-bold">U</span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3 sm:p-4 md:p-6">
        <div className="max-w-4xl mx-auto">
          {/* Page title */}
          <div className="flex items-center gap-2 sm:gap-3 mb-2">
            <CalendarIcon className="w-5 h-5 sm:w-7 sm:h-7 text-gray-700" />
            <h2 className="text-lg sm:text-2xl font-bold text-gray-900">Upcoming Items</h2>
          </div>
          <p className="text-gray-500 text-sm sm:text-base mb-4 sm:mb-6">Your schedule and important dates tracked by Yennifer</p>

          {/* Items list */}
          <div className="space-y-3 sm:space-y-4">
            {mockItems.map((item) => (
              <div
                key={item.id}
                className="bg-white border border-gray-200 rounded-xl p-3 sm:p-5 hover:shadow-md transition-shadow"
              >
                <div className="flex items-start gap-3 sm:gap-4">
                  <div className="flex-1 min-w-0">
                    <span className={`px-2 sm:px-3 py-0.5 sm:py-1 rounded-full text-xs font-medium ${getTypeBadge(item.type)}`}>
                      {item.type}
                    </span>
                    <h3 className="font-semibold text-gray-900 text-sm sm:text-lg mt-2 line-clamp-2">{item.title}</h3>
                    
                    <div className="flex flex-wrap items-center gap-2 sm:gap-4 mt-2 sm:mt-3">
                      <div className="flex items-center gap-1.5 sm:gap-2 text-xs sm:text-sm text-gray-500">
                        <CalendarSmallIcon className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                        <span>{item.date}</span>
                      </div>
                      <div className="flex items-center gap-1.5 sm:gap-2 text-xs sm:text-sm text-gray-500">
                        <ClockIcon className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                        <span>{item.time}</span>
                      </div>
                    </div>
                    
                    {item.location && (
                      <div className="flex items-center gap-1.5 sm:gap-2 text-xs sm:text-sm text-gray-500 mt-1.5 sm:mt-2">
                        <LocationIcon className="w-3.5 h-3.5 sm:w-4 sm:h-4 shrink-0" />
                        <span className="truncate">{item.location}</span>
                      </div>
                    )}
                    
                    {item.attendees && item.attendees.length > 0 && (
                      <div className="flex items-center gap-1.5 sm:gap-2 text-xs sm:text-sm text-gray-500 mt-1.5 sm:mt-2">
                        <PeopleIcon className="w-3.5 h-3.5 sm:w-4 sm:h-4 shrink-0" />
                        <span className="truncate">{item.attendees.join(', ')}</span>
                      </div>
                    )}
                  </div>
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

function CalendarIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
    </svg>
  );
}

function CalendarSmallIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
    </svg>
  );
}

function ClockIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function LocationIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  );
}

function PeopleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
    </svg>
  );
}
