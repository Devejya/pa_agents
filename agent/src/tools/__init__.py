# Gmail Tools Package
from .read_emails import read_emails, get_email_by_id
from .summarize import summarize_daily_emails
from .priority import get_priority_emails
from .draft_reply import (
    create_draft_reply,
    generate_reply_preview,
    compose_reply_to_text,
    compose_new_email,
    create_new_draft,
)
from .learn_style import (
    analyze_writing_style,
    analyze_contextual_styles,
    get_style_profile,
    get_style_for_context,
    clear_style_profile,
    get_style_status,
    get_contextual_style_status,
    should_refresh_styles,
    auto_refresh_styles_if_needed,
    STYLE_CATEGORIES,
)
from .memory_tools import (
    extract_facts_from_conversation,
    store_user_fact,
    retrieve_relevant_facts,
    list_all_memories,
    forget_fact,
    forget_all_memories,
    should_remember_this,
    auto_extract_and_save_facts,
)
from .user_network import (
    # Read tools
    get_contact_by_relationship,
    get_contact_by_name,
    get_interests_by_relationship,
    get_interests_by_name,
    find_related_person,
    get_most_contacted_people,
    search_contacts,
    # Write tools
    add_new_contact,
    update_contact_info,
    add_relationship,
    add_interest_to_contact,
    deactivate_contact,
    # Tool collections
    USER_NETWORK_TOOLS,
    USER_NETWORK_READ_TOOLS,
    USER_NETWORK_WRITE_TOOLS,
)
from .profile_discovery import (
    analyze_emails_for_profile,
    save_discovered_profile,
    PROFILE_DISCOVERY_TOOLS,
)

__all__ = [
    "read_emails",
    "get_email_by_id", 
    "summarize_daily_emails",
    "get_priority_emails",
    "create_draft_reply",
    "generate_reply_preview",
    "compose_reply_to_text",
    "compose_new_email",
    "create_new_draft",
    # Style learning tools
    "analyze_writing_style",
    "analyze_contextual_styles",
    "get_style_profile",
    "get_style_for_context",
    "clear_style_profile",
    "get_style_status",
    "get_contextual_style_status",
    "STYLE_CATEGORIES",
    # Memory tools
    "extract_facts_from_conversation",
    "store_user_fact",
    "retrieve_relevant_facts",
    "list_all_memories",
    "forget_fact",
    "forget_all_memories",
    "should_remember_this",
    "auto_extract_and_save_facts",
    # User network read tools
    "get_contact_by_relationship",
    "get_contact_by_name",
    "get_interests_by_relationship",
    "get_interests_by_name",
    "find_related_person",
    "get_most_contacted_people",
    "search_contacts",
    # User network write tools
    "add_new_contact",
    "update_contact_info",
    "add_relationship",
    "add_interest_to_contact",
    "deactivate_contact",
    # Tool collections
    "USER_NETWORK_TOOLS",
    "USER_NETWORK_READ_TOOLS",
    "USER_NETWORK_WRITE_TOOLS",
    # Profile discovery tools
    "analyze_emails_for_profile",
    "save_discovered_profile",
    "PROFILE_DISCOVERY_TOOLS",
]

