import type { ContactWithRelationship } from '../services/api';

interface ContactCardProps {
  contact: ContactWithRelationship;
  onClick?: () => void;
}

function getInitials(name: string): string {
  const parts = name.split(' ');
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

function getAvatarColor(name: string): string {
  // Generate consistent color based on name
  const colors = [
    'bg-yennifer-600',
    'bg-emerald-600',
    'bg-amber-600',
    'bg-rose-600',
    'bg-sky-600',
    'bg-indigo-600',
    'bg-teal-600',
    'bg-orange-600',
  ];
  
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  
  return colors[Math.abs(hash) % colors.length];
}

export default function ContactCard({ contact, onClick }: ContactCardProps) {
  const email = contact.personal_email || contact.work_email;
  const phone = contact.personal_cell || contact.work_cell;
  const initials = getInitials(contact.name);
  const avatarColor = getAvatarColor(contact.name);
  
  // Check if contact info is placeholder (fake)
  const isPlaceholderPhone = contact.is_placeholder_phone || (phone && phone.startsWith('+0-000-000'));
  const isPlaceholderEmail = contact.is_placeholder_email || (email && email.includes('@fake.internal'));

  return (
    <div
      onClick={onClick}
      className="bg-white border border-gray-200 rounded-xl p-3 sm:p-5 hover:shadow-md hover:border-yennifer-300 transition-all cursor-pointer active:bg-gray-50"
    >
      <div className="flex items-start gap-3 sm:gap-4">
        {/* Avatar */}
        <div
          className={`w-10 h-10 sm:w-12 sm:h-12 ${avatarColor} rounded-full flex items-center justify-center flex-shrink-0`}
        >
          <span className="text-white font-semibold text-sm sm:text-base">{initials}</span>
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-gray-900 truncate text-sm sm:text-base">{contact.name}</h3>
          {contact.relationship && (
            <p className="text-xs sm:text-sm text-gray-500 capitalize">{contact.relationship}</p>
          )}
          {contact.latest_title && contact.company && (
            <p className="text-xs sm:text-sm text-gray-500 truncate">
              {contact.latest_title} at {contact.company}
            </p>
          )}
        </div>
      </div>

      {/* Contact info */}
      <div className="mt-3 sm:mt-4 space-y-1.5 sm:space-y-2">
        {email && !isPlaceholderEmail && (
          <div className="flex items-center gap-2 text-xs sm:text-sm text-gray-600">
            <MailIcon className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-gray-400 shrink-0" />
            <span className="truncate">{email}</span>
          </div>
        )}
        {isPlaceholderEmail && (
          <div className="flex items-center gap-2 text-xs sm:text-sm text-rose-500">
            <MailIcon className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-rose-400 shrink-0" />
            <span className="italic">No email on file</span>
          </div>
        )}
        {phone && !isPlaceholderPhone && (
          <div className="flex items-center gap-2 text-xs sm:text-sm text-gray-600">
            <PhoneIcon className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-gray-400 shrink-0" />
            <span>{phone}</span>
          </div>
        )}
        {isPlaceholderPhone && (
          <div className="flex items-center gap-2 text-xs sm:text-sm text-rose-500">
            <PhoneIcon className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-rose-400 shrink-0" />
            <span className="italic">No phone on file</span>
          </div>
        )}
        {!email && !phone && !isPlaceholderPhone && !isPlaceholderEmail && (
          <div className="flex items-center gap-2 text-xs sm:text-sm text-gray-400 italic">
            No contact info
          </div>
        )}
      </div>
    </div>
  );
}

function MailIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
    </svg>
  );
}

function PhoneIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
    </svg>
  );
}
