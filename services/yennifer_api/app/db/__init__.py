"""
Database module for Yennifer API.

Handles database connections, migrations, and token storage.
"""

from .connection import init_db, close_db, get_db_pool, set_rls_user, RLSConnection
from .crypto import encrypt_token, decrypt_token
from .token_repository import TokenRepository
from .user_repository import UserRepository
from .chat_repository import ChatRepository
from .persons_repository import PersonsRepository
from .user_data_repository import (
    InterestsRepository,
    ImportantDatesRepository,
    UserTasksRepository,
    MemoriesRepository,
)
from .integrations_repository import IntegrationsRepository

__all__ = [
    "init_db",
    "close_db", 
    "get_db_pool",
    "set_rls_user",
    "RLSConnection",
    "encrypt_token",
    "decrypt_token",
    "TokenRepository",
    "UserRepository",
    "ChatRepository",
    "PersonsRepository",
    "InterestsRepository",
    "ImportantDatesRepository",
    "UserTasksRepository",
    "MemoriesRepository",
    "IntegrationsRepository",
]

