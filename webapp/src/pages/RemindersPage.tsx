// Placeholder page for Reminders
// Functionality to be implemented later

const mockReminders = [
  {
    id: '1',
    title: 'Daily Meditation',
    description: 'Morning meditation and magical energy alignment',
    time: '07:00',
    frequency: 'Daily',
    priority: 'normal',
    icon: 'bell',
  },
  {
    id: '2',
    title: 'Check Portal Stability',
    description: 'Monitor the stability of active portal connections',
    time: '09:00',
    frequency: 'Daily',
    priority: 'urgent',
    icon: 'alert',
  },
  {
    id: '3',
    title: 'Review Intelligence Reports',
    description: 'Analyze new information from network contacts',
    time: '11:00',
    frequency: 'Weekdays',
    priority: 'normal',
    icon: 'bell',
  },
  {
    id: '4',
    title: 'Potion Brewing Session',
    description: 'Prepare and refill essential potions inventory',
    time: '15:00',
    frequency: 'Weekly',
    priority: 'low',
    icon: 'bell',
  },
];

function getPriorityBadge(priority: string) {
  const styles: Record<string, string> = {
    urgent: 'bg-red-100 text-red-700 border-red-200',
    normal: 'bg-blue-100 text-blue-700 border-blue-200',
    low: 'bg-gray-100 text-gray-600 border-gray-200',
  };
  return styles[priority] || styles.normal;
}

function getReminderIcon(_icon: string, priority: string) {
  if (priority === 'urgent') {
    return (
      <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-full bg-red-100 flex items-center justify-center shrink-0">
        <AlertIcon className="w-4 h-4 sm:w-5 sm:h-5 text-red-600" />
      </div>
    );
  }
  return (
    <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-full bg-yennifer-100 flex items-center justify-center shrink-0">
      <BellIcon className="w-4 h-4 sm:w-5 sm:h-5 text-yennifer-600" />
    </div>
  );
}

export default function RemindersPage() {
  return (
    <div className="flex flex-col h-full">
      {/* Header - hidden on mobile since Layout shows a header */}
      <header className="hidden md:flex bg-white border-b border-gray-200 px-4 lg:px-6 py-3 lg:py-4 items-center justify-between shrink-0">
        <h1 className="text-lg lg:text-xl font-semibold text-gray-900">Reminders</h1>
        <div className="w-8 h-8 lg:w-9 lg:h-9 bg-yennifer-600 rounded-full flex items-center justify-center">
          <span className="text-white text-sm font-bold">U</span>
        </div>
      </header>

      {/* Mobile sub-header */}
      <div className="md:hidden bg-white border-b border-gray-200 px-4 py-2 flex items-center justify-between shrink-0">
        <h1 className="text-base font-semibold text-gray-900">Reminders</h1>
        <div className="w-7 h-7 bg-yennifer-600 rounded-full flex items-center justify-center">
          <span className="text-white text-xs font-bold">U</span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3 sm:p-4 md:p-6">
        <div className="max-w-4xl mx-auto">
          {/* Page title */}
          <div className="flex items-center gap-2 sm:gap-3 mb-2">
            <BellOutlineIcon className="w-5 h-5 sm:w-7 sm:h-7 text-gray-700" />
            <h2 className="text-lg sm:text-2xl font-bold text-gray-900">Reminders</h2>
          </div>
          <p className="text-gray-500 text-sm sm:text-base mb-4 sm:mb-6">Scheduled reminders and recurring tasks managed by Yennifer</p>

          {/* Reminders list */}
          <div className="space-y-3 sm:space-y-4">
            {mockReminders.map((reminder) => (
              <div
                key={reminder.id}
                className="bg-white border border-gray-200 rounded-xl p-3 sm:p-5 hover:shadow-md transition-shadow"
              >
                <div className="flex items-start gap-3 sm:gap-4">
                  {getReminderIcon(reminder.icon, reminder.priority)}
                  
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-gray-900 text-sm sm:text-base">{reminder.title}</h3>
                    <p className="text-xs sm:text-sm text-gray-500 mt-1 line-clamp-2">{reminder.description}</p>
                    
                    <div className="flex flex-wrap items-center gap-2 sm:gap-4 mt-2 sm:mt-3">
                      <div className="flex items-center gap-1.5 sm:gap-2 text-xs sm:text-sm text-gray-500">
                        <ClockIcon className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                        <span>{reminder.time}</span>
                      </div>
                      <span className="px-2 py-0.5 bg-yennifer-100 text-yennifer-700 rounded text-xs font-medium">
                        {reminder.frequency}
                      </span>
                    </div>
                  </div>
                  
                  <span className={`px-2 sm:px-3 py-0.5 sm:py-1 rounded-full text-xs font-medium border whitespace-nowrap shrink-0 ${getPriorityBadge(reminder.priority)}`}>
                    {reminder.priority}
                  </span>
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

function BellOutlineIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
    </svg>
  );
}

function BellIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
    </svg>
  );
}

function AlertIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
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
