import { useState, useEffect } from 'react';
import ContactCard from '../components/ContactCard';
import { getContactsWithRelationships, type ContactWithRelationship } from '../services/api';

export default function ContactsPage() {
  const [contacts, setContacts] = useState<ContactWithRelationship[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedContact, setSelectedContact] = useState<ContactWithRelationship | null>(null);

  useEffect(() => {
    async function loadContacts() {
      try {
        const data = await getContactsWithRelationships();
        setContacts(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load contacts');
      } finally {
        setLoading(false);
      }
    }
    
    loadContacts();
  }, []);

  return (
    <div className="flex flex-col h-full">
      {/* Header - hidden on mobile since Layout shows a header */}
      <header className="hidden md:flex bg-white dark:bg-zinc-900 border-b border-gray-200 dark:border-zinc-800 px-4 lg:px-6 py-3 lg:py-4 items-center justify-between shrink-0">
        <h1 className="text-lg lg:text-xl font-semibold text-gray-900 dark:text-gray-100">Contacts</h1>
        <div className="w-8 h-8 lg:w-9 lg:h-9 bg-yennifer-600 rounded-full flex items-center justify-center">
          <span className="text-white text-sm font-bold">U</span>
        </div>
      </header>

      {/* Mobile sub-header */}
      <div className="md:hidden bg-white dark:bg-zinc-900 border-b border-gray-200 dark:border-zinc-800 px-4 py-2 flex items-center justify-between shrink-0">
        <h1 className="text-base font-semibold text-gray-900 dark:text-gray-100">Contacts</h1>
        <div className="w-7 h-7 bg-yennifer-600 rounded-full flex items-center justify-center">
          <span className="text-white text-xs font-bold">U</span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3 sm:p-4 md:p-6">
        <div className="max-w-6xl mx-auto">
          {/* Page title */}
          <div className="flex items-center gap-2 sm:gap-3 mb-2">
            <ContactsIcon className="w-5 h-5 sm:w-7 sm:h-7 text-gray-700 dark:text-gray-300" />
            <h2 className="text-lg sm:text-2xl font-bold text-gray-900 dark:text-gray-100">Contacts</h2>
          </div>
          <p className="text-gray-500 dark:text-gray-400 text-sm sm:text-base mb-4 sm:mb-6">People in your network managed by Yennifer</p>

          {/* Loading state */}
          {loading && (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-yennifer-700 dark:border-yennifer-400"></div>
            </div>
          )}

          {/* Error state */}
          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/50 rounded-lg p-3 sm:p-4 text-red-700 dark:text-red-400 text-sm">
              {error}
            </div>
          )}

          {/* Empty state */}
          {!loading && !error && contacts.length === 0 && (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              <ContactsIcon className="w-10 h-10 sm:w-12 sm:h-12 mx-auto mb-4 text-gray-300 dark:text-gray-600" />
              <p className="text-sm sm:text-base">No contacts found</p>
              <p className="text-xs sm:text-sm mt-1">Ask Yennifer to discover contacts from your emails</p>
            </div>
          )}

          {/* Contacts grid */}
          {!loading && !error && contacts.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
              {contacts.map((contact) => (
                <ContactCard
                  key={contact.id}
                  contact={contact}
                  onClick={() => setSelectedContact(contact)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Contact detail modal */}
      {selectedContact && (
        <ContactDetailModal
          contact={selectedContact}
          onClose={() => setSelectedContact(null)}
        />
      )}

      {/* Help button */}
      <button className="fixed bottom-4 sm:bottom-6 right-4 sm:right-6 w-9 h-9 sm:w-10 sm:h-10 bg-gray-800 dark:bg-zinc-700 text-white rounded-full flex items-center justify-center shadow-lg hover:bg-gray-700 dark:hover:bg-zinc-600 transition-colors z-30 text-sm sm:text-base">
        ?
      </button>
    </div>
  );
}

// Contact detail modal
function ContactDetailModal({
  contact,
  onClose,
}: {
  contact: ContactWithRelationship;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 bg-black/50 dark:bg-black/70 flex items-end sm:items-center justify-center z-50 p-0 sm:p-4" onClick={onClose}>
      <div
        className="bg-white dark:bg-zinc-900 rounded-t-2xl sm:rounded-2xl shadow-xl w-full sm:max-w-lg max-h-[85vh] sm:max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-4 sm:p-6 border-b border-gray-100 dark:border-zinc-800">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3 sm:gap-4">
              <div className="w-12 h-12 sm:w-16 sm:h-16 bg-yennifer-600 rounded-full flex items-center justify-center shrink-0">
                <span className="text-white text-lg sm:text-2xl font-bold">
                  {contact.name.charAt(0).toUpperCase()}
                </span>
              </div>
              <div className="min-w-0">
                <h2 className="text-lg sm:text-xl font-bold text-gray-900 dark:text-gray-100 truncate">{contact.name}</h2>
                {contact.relationship && (
                  <p className="text-gray-500 dark:text-gray-400 capitalize text-sm sm:text-base">{contact.relationship}</p>
                )}
              </div>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors p-1 shrink-0"
            >
              <CloseIcon className="w-5 h-5 sm:w-6 sm:h-6" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
          {/* Contact info */}
          <section>
            <h3 className="text-xs sm:text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2 sm:mb-3">
              Contact Information
            </h3>
            <div className="space-y-2 sm:space-y-3">
              {(() => {
                const phone = contact.personal_cell || contact.work_cell;
                const email = contact.personal_email || contact.work_email;
                const isPlaceholderPhone = contact.is_placeholder_phone || (phone && phone.startsWith('+0-000-000'));
                const isPlaceholderEmail = contact.is_placeholder_email || (email && email.includes('@fake.internal'));
                
                const hasRealContact = (email && !isPlaceholderEmail) || (phone && !isPlaceholderPhone);
                
                return (
                  <>
                    {contact.personal_email && !isPlaceholderEmail && (
                      <InfoRow icon={<MailIcon />} label="Personal Email" value={contact.personal_email} />
                    )}
                    {contact.work_email && !isPlaceholderEmail && (
                      <InfoRow icon={<MailIcon />} label="Work Email" value={contact.work_email} />
                    )}
                    {contact.personal_cell && !isPlaceholderPhone && (
                      <InfoRow icon={<PhoneIcon />} label="Personal Phone" value={contact.personal_cell} />
                    )}
                    {contact.work_cell && !isPlaceholderPhone && (
                      <InfoRow icon={<PhoneIcon />} label="Work Phone" value={contact.work_cell} />
                    )}
                    {!hasRealContact && (
                      <div className="text-rose-500 dark:text-rose-400 text-xs sm:text-sm italic flex items-center gap-2">
                        <WarningIcon />
                        No contact information on file. Ask Yennifer to add it.
                      </div>
                    )}
                  </>
                );
              })()}
            </div>
          </section>

          {/* Work info */}
          {(contact.company || contact.latest_title) && (
            <section>
              <h3 className="text-xs sm:text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2 sm:mb-3">
                Professional
              </h3>
              <div className="space-y-2 sm:space-y-3">
                {contact.latest_title && (
                  <InfoRow icon={<BriefcaseIcon />} label="Title" value={contact.latest_title} />
                )}
                {contact.company && (
                  <InfoRow icon={<BuildingIcon />} label="Company" value={contact.company} />
                )}
              </div>
            </section>
          )}

          {/* Location */}
          {(contact.city || contact.country) && (
            <section>
              <h3 className="text-xs sm:text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2 sm:mb-3">
                Location
              </h3>
              <InfoRow
                icon={<LocationIcon />}
                label="Location"
                value={[contact.city, contact.country].filter(Boolean).join(', ')}
              />
            </section>
          )}

          {/* Interests */}
          {contact.interests && contact.interests.length > 0 && (
            <section>
              <h3 className="text-xs sm:text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2 sm:mb-3">
                Interests
              </h3>
              <div className="flex flex-wrap gap-1.5 sm:gap-2">
                {contact.interests.map((interest) => (
                  <span
                    key={interest.id}
                    className="px-2 sm:px-3 py-0.5 sm:py-1 bg-yennifer-50 dark:bg-yennifer-900/30 text-yennifer-700 dark:text-yennifer-400 rounded-full text-xs sm:text-sm capitalize"
                  >
                    {interest.name}
                  </span>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

function InfoRow({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-2 sm:gap-3">
      <div className="w-4 h-4 sm:w-5 sm:h-5 text-gray-400 dark:text-gray-500 flex-shrink-0 mt-0.5">{icon}</div>
      <div className="min-w-0">
        <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
        <p className="text-gray-900 dark:text-gray-100 text-sm sm:text-base break-words">{value}</p>
      </div>
    </div>
  );
}

// Icons
function ContactsIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
    </svg>
  );
}

function CloseIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

function MailIcon() {
  return (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
    </svg>
  );
}

function PhoneIcon() {
  return (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
    </svg>
  );
}

function BriefcaseIcon() {
  return (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
    </svg>
  );
}

function BuildingIcon() {
  return (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
    </svg>
  );
}

function LocationIcon() {
  return (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  );
}

function WarningIcon() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
  );
}
