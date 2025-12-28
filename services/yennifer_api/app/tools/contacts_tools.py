"""
Google Contacts Tools

Functions for accessing Google Contacts (People API).
"""

from typing import Optional

from ..core.google_services import get_contacts_service


def list_contacts(
    user_email: str,
    max_results: int = 100,
) -> list[dict]:
    """
    List contacts from Google Contacts.
    
    Args:
        user_email: User's email for authentication
        max_results: Maximum number of contacts to return
        
    Returns:
        List of contact dictionaries
    """
    service = get_contacts_service(user_email)
    
    results = service.people().connections().list(
        resourceName="people/me",
        pageSize=max_results,
        personFields="names,emailAddresses,phoneNumbers,organizations,addresses,birthdays,biographies",
    ).execute()
    
    connections = results.get("connections", [])
    
    contacts = []
    for person in connections:
        names = person.get("names", [{}])
        emails = person.get("emailAddresses", [])
        phones = person.get("phoneNumbers", [])
        orgs = person.get("organizations", [])
        
        contact = {
            "resource_name": person.get("resourceName"),
            "name": names[0].get("displayName") if names else "",
            "given_name": names[0].get("givenName") if names else "",
            "family_name": names[0].get("familyName") if names else "",
            "emails": [e.get("value") for e in emails],
            "phones": [p.get("value") for p in phones],
            "organization": orgs[0].get("name") if orgs else "",
            "job_title": orgs[0].get("title") if orgs else "",
        }
        contacts.append(contact)
    
    return contacts


def search_contacts(
    user_email: str,
    query: str,
    max_results: int = 10,
) -> list[dict]:
    """
    Search contacts by name or email.
    
    Args:
        user_email: User's email for authentication
        query: Search query (name or email)
        max_results: Maximum results to return
        
    Returns:
        List of matching contact dictionaries
    """
    service = get_contacts_service(user_email)
    
    results = service.people().searchContacts(
        query=query,
        pageSize=max_results,
        readMask="names,emailAddresses,phoneNumbers,organizations",
    ).execute()
    
    people = results.get("results", [])
    
    contacts = []
    for result in people:
        person = result.get("person", {})
        names = person.get("names", [{}])
        emails = person.get("emailAddresses", [])
        phones = person.get("phoneNumbers", [])
        orgs = person.get("organizations", [])
        
        contact = {
            "resource_name": person.get("resourceName"),
            "name": names[0].get("displayName") if names else "",
            "emails": [e.get("value") for e in emails],
            "phones": [p.get("value") for p in phones],
            "organization": orgs[0].get("name") if orgs else "",
            "job_title": orgs[0].get("title") if orgs else "",
        }
        contacts.append(contact)
    
    return contacts


def get_contact(
    user_email: str,
    resource_name: str,
) -> dict:
    """
    Get a specific contact by resource name.
    
    Args:
        user_email: User's email for authentication
        resource_name: Contact resource name (e.g., "people/c12345")
        
    Returns:
        Contact dictionary
    """
    service = get_contacts_service(user_email)
    
    person = service.people().get(
        resourceName=resource_name,
        personFields="names,emailAddresses,phoneNumbers,organizations,addresses,birthdays,biographies",
    ).execute()
    
    names = person.get("names", [{}])
    emails = person.get("emailAddresses", [])
    phones = person.get("phoneNumbers", [])
    orgs = person.get("organizations", [])
    addresses = person.get("addresses", [])
    birthdays = person.get("birthdays", [])
    bios = person.get("biographies", [])
    
    return {
        "resource_name": person.get("resourceName"),
        "name": names[0].get("displayName") if names else "",
        "given_name": names[0].get("givenName") if names else "",
        "family_name": names[0].get("familyName") if names else "",
        "emails": [e.get("value") for e in emails],
        "phones": [{"value": p.get("value"), "type": p.get("type")} for p in phones],
        "organization": orgs[0].get("name") if orgs else "",
        "job_title": orgs[0].get("title") if orgs else "",
        "addresses": [a.get("formattedValue") for a in addresses],
        "birthday": birthdays[0].get("date") if birthdays else None,
        "bio": bios[0].get("value") if bios else "",
    }

