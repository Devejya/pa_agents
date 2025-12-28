# User Relationship Graph Module
# PostgreSQL-based graph implementation with migration path to Neptune

# HTTP Client (for microservice access) - always available
from .client import UserNetworkClient, UserNetworkClientError, create_client_from_env

# Models - always available
from .models import (
    Person,
    Relationship,
    Interest,
    ConnectionCounts,
    PersonStatus,
    RelationshipCategory,
)

# Local DB access (optional - requires asyncpg)
# Only import if asyncpg is available
try:
    from .repository import GraphRepository
    from .queries import GraphQueries
    _HAS_DB_ACCESS = True
except ImportError:
    GraphRepository = None
    GraphQueries = None
    _HAS_DB_ACCESS = False

__all__ = [
    # HTTP Client (for microservice access)
    "UserNetworkClient",
    "UserNetworkClientError",
    "create_client_from_env",
    # Models
    "Person",
    "Relationship", 
    "Interest",
    "ConnectionCounts",
    "PersonStatus",
    "RelationshipCategory",
    # Local DB access (optional)
    "GraphRepository",
    "GraphQueries",
]

