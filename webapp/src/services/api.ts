/**
 * API client for Yennifer services
 */

import { getAuthHeaders, clearAuthToken } from '../contexts/AuthContext';

// In production, use relative URLs (same domain as webapp)
// In development, use localhost URLs
const isProduction = import.meta.env.PROD;
const YENNIFER_API_URL = import.meta.env.VITE_YENNIFER_API_URL || (isProduction ? '' : 'http://localhost:8000');

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
  is_placeholder_phone?: boolean;
  is_placeholder_email?: boolean;
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

// Contacts API - Now proxied through Yennifer API for proper authentication

export async function getContacts(): Promise<Contact[]> {
  const response = await fetch(`${YENNIFER_API_URL}/api/v1/contacts`, {
    headers: getAuthHeaders(),
  });

  await handleResponse(response, 'Failed to get contacts');
  return response.json();
}

export async function getCoreUser(): Promise<Contact> {
  const response = await fetch(`${YENNIFER_API_URL}/api/v1/contacts/core-user`, {
    headers: getAuthHeaders(),
  });

  await handleResponse(response, 'Failed to get core user');
  return response.json();
}

export async function getContactById(id: string): Promise<Contact> {
  const response = await fetch(`${YENNIFER_API_URL}/api/v1/contacts/${id}`, {
    headers: getAuthHeaders(),
  });

  await handleResponse(response, 'Failed to get contact');
  return response.json();
}

export async function getRelationshipsForPerson(personId: string): Promise<Relationship[]> {
  const response = await fetch(`${YENNIFER_API_URL}/api/v1/contacts/${personId}/relationships`, {
    headers: getAuthHeaders(),
  });

  await handleResponse(response, 'Failed to get relationships');
  return response.json();
}

export async function searchContacts(query: string): Promise<Contact[]> {
  const response = await fetch(`${YENNIFER_API_URL}/api/v1/contacts/search?q=${encodeURIComponent(query)}`, {
    headers: getAuthHeaders(),
  });

  await handleResponse(response, 'Failed to search contacts');
  return response.json();
}

/**
 * Get all contacts with their relationships to the core user
 */
export async function getContactsWithRelationships(): Promise<ContactWithRelationship[]> {
  try {
    // Get all contacts first
    const allContacts = await getContacts();
    
    // Filter out core user
    const contactsWithRels: ContactWithRelationship[] = allContacts
      .filter(c => !c.is_core_user)
      .map(contact => ({
        ...contact,
        relationship: undefined,
      }));
    
    // Try to get core user for relationships (optional)
    try {
      const coreUser = await getCoreUser();
      if (coreUser?.id) {
        const relationships = await getRelationshipsForPerson(coreUser.id);
        
        // Create a map of person_id -> relationship role
        const relationshipMap = new Map<string, string>();
        for (const rel of relationships) {
          relationshipMap.set(rel.to_person_id, rel.to_role);
        }
        
        // Add relationship info to contacts
        return contactsWithRels.map(contact => ({
          ...contact,
          relationship: relationshipMap.get(contact.id),
        }));
      }
    } catch {
      // Core user doesn't exist yet - that's okay, just return contacts without relationships
      console.log('No core user found, showing contacts without relationship info');
    }
    
    return contactsWithRels;
  } catch (error) {
    console.error('Error fetching contacts with relationships:', error);
    return [];
  }
}

// ============== Integrations API ==============

export interface IntegrationScope {
  id: string;
  scope_uri: string;
  name: string;
  description: string | null;
  is_required: boolean;
  display_order: number;
  is_enabled: boolean;
  is_granted: boolean;
  granted_at: string | null;
}

export interface Integration {
  id: string;
  provider: string;
  name: string;
  description: string | null;
  capability_summary: string | null;
  icon_url: string | null;
  display_order: number;
  is_enabled: boolean;
  enabled_at: string | null;
  disabled_at: string | null;
}

export interface IntegrationDetail extends Integration {
  scopes: IntegrationScope[];
}

export interface EnableResponse {
  success: boolean;
  needs_auth: boolean;
  auth_url: string | null;
  integration: IntegrationDetail | null;
}

export interface ScopeToggleResponse {
  success: boolean;
  needs_auth: boolean;
  auth_url: string | null;
  scope_id: string;
  is_enabled: boolean;
  is_granted: boolean;
}

/**
 * Get all integrations with user's enabled status
 */
export async function getIntegrations(): Promise<Integration[]> {
  const response = await fetch(`${YENNIFER_API_URL}/api/v1/integrations`, {
    headers: getAuthHeaders(),
  });

  await handleResponse(response, 'Failed to get integrations');
  const data = await response.json();
  return data.integrations;
}

/**
 * Get integration details with all scopes
 */
export async function getIntegrationDetail(integrationId: string): Promise<IntegrationDetail> {
  const response = await fetch(`${YENNIFER_API_URL}/api/v1/integrations/${integrationId}`, {
    headers: getAuthHeaders(),
  });

  await handleResponse(response, 'Failed to get integration');
  return response.json();
}

/**
 * Enable an integration
 */
export async function enableIntegration(integrationId: string): Promise<EnableResponse> {
  const response = await fetch(`${YENNIFER_API_URL}/api/v1/integrations/${integrationId}/enable`, {
    method: 'POST',
    headers: getAuthHeaders(),
  });

  await handleResponse(response, 'Failed to enable integration');
  return response.json();
}

/**
 * Disable an integration
 */
export async function disableIntegration(integrationId: string): Promise<EnableResponse> {
  const response = await fetch(`${YENNIFER_API_URL}/api/v1/integrations/${integrationId}/disable`, {
    method: 'POST',
    headers: getAuthHeaders(),
  });

  await handleResponse(response, 'Failed to disable integration');
  return response.json();
}

/**
 * Enable a specific scope
 */
export async function enableScope(integrationId: string, scopeId: string): Promise<ScopeToggleResponse> {
  const response = await fetch(`${YENNIFER_API_URL}/api/v1/integrations/${integrationId}/scopes/${scopeId}/enable`, {
    method: 'POST',
    headers: getAuthHeaders(),
  });

  await handleResponse(response, 'Failed to enable scope');
  return response.json();
}

/**
 * Disable a specific scope
 */
export async function disableScope(integrationId: string, scopeId: string): Promise<ScopeToggleResponse> {
  const response = await fetch(`${YENNIFER_API_URL}/api/v1/integrations/${integrationId}/scopes/${scopeId}/disable`, {
    method: 'POST',
    headers: getAuthHeaders(),
  });

  await handleResponse(response, 'Failed to disable scope');
  return response.json();
}

/**
 * Enable all scopes for an integration
 */
export async function enableAllScopes(integrationId: string): Promise<EnableResponse> {
  const response = await fetch(`${YENNIFER_API_URL}/api/v1/integrations/${integrationId}/enable-all-scopes`, {
    method: 'POST',
    headers: getAuthHeaders(),
  });

  await handleResponse(response, 'Failed to enable all scopes');
  return response.json();
}

