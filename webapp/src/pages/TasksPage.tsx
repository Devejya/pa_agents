// Placeholder page for Yennifer's Tasks
// Functionality to be implemented later

const mockTasks = [
  {
    id: '1',
    title: 'Research ancient magical artifacts',
    description: 'Investigate the history and properties of Elder Blood',
    dueDate: '2025-12-29',
    priority: 'high',
    status: 'in_progress',
  },
  {
    id: '2',
    title: 'Prepare spell components',
    description: 'Gather materials for teleportation spells',
    dueDate: '2025-12-30',
    priority: 'medium',
    status: 'pending',
  },
  {
    id: '3',
    title: 'Council meeting notes',
    description: 'Summarize decisions from the Lodge of Sorceresses',
    dueDate: '2025-12-26',
    priority: 'high',
    status: 'completed',
  },
  {
    id: '4',
    title: 'Update grimoire',
    description: 'Document new spell variations discovered this week',
    dueDate: '2026-01-05',
    priority: 'low',
    status: 'pending',
  },
];

function getStatusIcon(status: string) {
  switch (status) {
    case 'completed':
      return (
        <div className="w-5 h-5 rounded-full bg-green-500 flex items-center justify-center">
          <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
          </svg>
        </div>
      );
    case 'in_progress':
      return (
        <div className="w-5 h-5 rounded-full border-2 border-yennifer-500 flex items-center justify-center">
          <div className="w-2 h-2 rounded-full bg-yennifer-500" />
        </div>
      );
    default:
      return <div className="w-5 h-5 rounded-full border-2 border-gray-300" />;
  }
}

function getPriorityBadge(priority: string) {
  const colors = {
    high: 'bg-red-100 text-red-700 border-red-200',
    medium: 'bg-amber-100 text-amber-700 border-amber-200',
    low: 'bg-gray-100 text-gray-600 border-gray-200',
  };
  return colors[priority as keyof typeof colors] || colors.low;
}

export default function TasksPage() {
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">Yennifer's Tasks</h1>
        <div className="w-9 h-9 bg-yennifer-600 rounded-full flex items-center justify-center">
          <span className="text-white text-sm font-bold">U</span>
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto">
          {/* Page title */}
          <div className="flex items-center gap-3 mb-2">
            <TasksIcon className="w-7 h-7 text-gray-700" />
            <h2 className="text-2xl font-bold text-gray-900">Yennifer's Tasks</h2>
          </div>
          <p className="text-gray-500 mb-6">Active tasks and projects I'm managing for you</p>

          {/* Tasks list */}
          <div className="space-y-4">
            {mockTasks.map((task) => (
              <div
                key={task.id}
                className="bg-white border border-gray-200 rounded-xl p-5 hover:shadow-md transition-shadow"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-4">
                    {getStatusIcon(task.status)}
                    <div>
                      <h3 className="font-semibold text-gray-900">{task.title}</h3>
                      <p className="text-sm text-gray-500 mt-1">{task.description}</p>
                      <div className="flex items-center gap-2 mt-3 text-sm text-gray-500">
                        <ClockIcon className="w-4 h-4" />
                        <span>Due: {task.dueDate}</span>
                      </div>
                    </div>
                  </div>
                  <span
                    className={`px-3 py-1 rounded-full text-xs font-medium border ${getPriorityBadge(task.priority)}`}
                  >
                    {task.priority}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Help button */}
      <button className="fixed bottom-6 right-6 w-10 h-10 bg-gray-800 text-white rounded-full flex items-center justify-center shadow-lg hover:bg-gray-700 transition-colors">
        ?
      </button>
    </div>
  );
}

function TasksIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
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

