/**
 * API client for Yennifer services
 */

import { getAuthHeaders, clearAuthToken } from '../contexts/AuthContext';

// In production, use relative URLs (same domain as webapp)
// In development, use localhost URLs
const isProduction = import.meta.env.PROD;
const YENNIFER_API_URL = import.meta.env.VITE_YENNIFER_API_URL || (isProduction ? '' : 'http://localhost:8000');
const USER_NETWORK_API_URL = import.meta.env.VITE_USER_NETWORK_API_URL || (isProduction ? '' : 'http://localhost:8001');
const USER_NETWORK_API_KEY = import.meta.env.VITE_USER_NETWORK_API_KEY || '';

/**
 * Handle API response, check for auth errors
 */
async function handleResponse(response: Response, errorMessage: string): Promise<Response> {
  if (response.status === 401) {
    // Token expired or invalid, clear and redirect to login
    clearAuthToken();
    window.location.href = '/login';
    throw new Error('Session expired. Please login again.');
  }
  
  if (!response.ok) {
    throw new Error(`${errorMessage}: ${response.statusText}`);
  }
  
  return response;
}

// ============== Chat API ==============

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatResponse {
  response: string;
}

export async function sendMessage(message: string): Promise<string> {
  const response = await fetch(`${YENNIFER_API_URL}/api/v1/chat`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ message }),
  });

  await handleResponse(response, 'Failed to send message');

  const data: ChatResponse = await response.json();
  return data.response;
}

export async function getChatHistory(): Promise<ChatMessage[]> {
  const response = await fetch(`${YENNIFER_API_URL}/api/v1/chat/history`, {
    headers: getAuthHeaders(),
  });

  await handleResponse(response, 'Failed to get chat history');

  const data = await response.json();
  return data.messages;
}

export async function setChatHistory(messages: ChatMessage[]): Promise<void> {
  const response = await fetch(`${YENNIFER_API_URL}/api/v1/chat/history`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(messages),
  });

  await handleResponse(response, 'Failed to set chat history');
}

export async function clearChatHistory(): Promise<void> {
  const response = await fetch(`${YENNIFER_API_URL}/api/v1/chat/history`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });

  await handleResponse(response, 'Failed to clear chat history');
}

// ============== User Network API ==============

export interface Interest {
  id: string;
  name: string;
  type: string;
  level: number;
}

export interface Contact {
  id: string;
  name: string;
  aliases: string[];
  personal_email: string | null;
  work_email: string | null;
  personal_cell: string | null;
  work_cell: string | null;
  company: string | null;
  latest_title: string | null;
  city: string | null;
  country: string | null;
  interests: Interest[];
  status: string;
  is_core_user: boolean;
  created_at: string;
  updated_at: string;
}

export interface Relationship {
  id: string;
  from_person_id: string;
  to_person_id: string;
  category: string;
  from_role: string;
  to_role: string;
  is_active: boolean;
}

export interface ContactWithRelationship extends Contact {
  relationship?: string;
}

const userNetworkHeaders = {
  'Content-Type': 'application/json',
  'X-API-Key': USER_NETWORK_API_KEY,
};

export async function getContacts(): Promise<Contact[]> {
  const response = await fetch(`${USER_NETWORK_API_URL}/api/v1/persons`, {
    headers: userNetworkHeaders,
  });

  if (!response.ok) {
    throw new Error(`Failed to get contacts: ${response.statusText}`);
  }

  return response.json();
}

export async function getCoreUser(): Promise<Contact> {
  const response = await fetch(`${USER_NETWORK_API_URL}/api/v1/persons/core-user`, {
    headers: userNetworkHeaders,
  });

  if (!response.ok) {
    throw new Error(`Failed to get core user: ${response.statusText}`);
  }

  return response.json();
}

export async function getContactById(id: string): Promise<Contact> {
  const response = await fetch(`${USER_NETWORK_API_URL}/api/v1/persons/${id}`, {
    headers: userNetworkHeaders,
  });

  if (!response.ok) {
    throw new Error(`Failed to get contact: ${response.statusText}`);
  }

  return response.json();
}

export async function getRelationshipsForPerson(personId: string): Promise<Relationship[]> {
  const response = await fetch(`${USER_NETWORK_API_URL}/api/v1/relationships/person/${personId}`, {
    headers: userNetworkHeaders,
  });

  if (!response.ok) {
    throw new Error(`Failed to get relationships: ${response.statusText}`);
  }

  return response.json();
}

export async function searchContacts(query: string): Promise<Contact[]> {
  const response = await fetch(`${USER_NETWORK_API_URL}/api/v1/persons/search?q=${encodeURIComponent(query)}`, {
    headers: userNetworkHeaders,
  });

  if (!response.ok) {
    throw new Error(`Failed to search contacts: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get all contacts with their relationships to the core user
 */
export async function getContactsWithRelationships(): Promise<ContactWithRelationship[]> {
  try {
    // Get core user first
    const coreUser = await getCoreUser();
    
    // Get all contacts
    const allContacts = await getContacts();
    
    // Get relationships for core user
    const relationships = await getRelationshipsForPerson(coreUser.id);
    
    // Create a map of person_id -> relationship role
    const relationshipMap = new Map<string, string>();
    for (const rel of relationships) {
      relationshipMap.set(rel.to_person_id, rel.to_role);
    }
    
    // Filter out core user and add relationship info
    const contactsWithRels: ContactWithRelationship[] = allContacts
      .filter(c => !c.is_core_user)
      .map(contact => ({
        ...contact,
        relationship: relationshipMap.get(contact.id),
      }));
    
    return contactsWithRels;
  } catch (error) {
    console.error('Error fetching contacts with relationships:', error);
    return [];
  }
}

