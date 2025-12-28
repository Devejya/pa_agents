# User Network Service

A FastAPI microservice for managing user relationship graphs. This service stores and queries information about people in a user's network and their relationships.

## Features

- **Person Management**: CRUD operations for contacts with rich attributes (name, aliases, contact info, interests, etc.)
- **Relationship Management**: Track relationships between people with role pairs and connection metadata
- **Query API**: Optimized endpoints for agent queries like "What is my sister's phone number?"
- **Graph Traversal**: Multi-hop queries like "Who is my brother's wife?"
- **Full-Text Search**: Search across names, aliases, expertise, and interests
- **API Key Authentication**: Secure service-to-service communication

## Quick Start

### 1. Setup Environment

```bash
cd services/user_network

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env
# Edit .env with your database credentials and API key
```

### 2. Setup Database

```bash
# Create database
createdb user_network

# Run schema
psql -d user_network -f ../../agent/src/graph/schema.sql
```

### 3. Generate API Key

```python
from src.core.security import generate_api_key
print(generate_api_key())
# Output: un_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
```

Add the generated key to your `.env` file:
```
API_KEYS=un_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
```

### 4. Run the Service

```bash
# Development
uvicorn src.main:app --reload --port 8001

# Production
uvicorn src.main:app --host 0.0.0.0 --port 8001
```

### 5. Access API Docs

Open http://localhost:8001/docs for interactive API documentation.

## API Endpoints

### CRUD Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/persons` | Create a person |
| GET | `/api/v1/persons` | List all persons |
| GET | `/api/v1/persons/{id}` | Get a person |
| PATCH | `/api/v1/persons/{id}` | Update a person |
| DELETE | `/api/v1/persons/{id}` | Delete a person |
| GET | `/api/v1/persons/core-user` | Get the core user |
| GET | `/api/v1/persons/search?q=...` | Full-text search |
| GET | `/api/v1/persons/find?name=...` | Find by name/alias |
| POST | `/api/v1/relationships` | Create a relationship |
| GET | `/api/v1/relationships/{id}` | Get a relationship |
| GET | `/api/v1/relationships/person/{id}` | Get person's relationships |
| PATCH | `/api/v1/relationships/{id}` | Update a relationship |
| POST | `/api/v1/relationships/{id}/end` | End a relationship |
| DELETE | `/api/v1/relationships/{id}` | Delete a relationship |

### Query Endpoints (for Agent)

| Endpoint | Example Query | Description |
|----------|---------------|-------------|
| `/api/v1/query/contact-by-role?role=sister` | "What is my sister's phone number?" | Get contact info by relationship |
| `/api/v1/query/interests-by-role?role=mother` | "What does my mother like?" | Get interests by relationship |
| `/api/v1/query/contact-by-name?name=Rachel` | "What is Rachel's email?" | Get contact info by name |
| `/api/v1/query/interests-by-name?name=Rajesh` | "What does Rajesh like?" | Get interests by name |
| `/api/v1/query/traverse?path=sister,husband` | "Who is my sister's husband?" | Multi-hop traversal |
| `/api/v1/query/most-contacted?limit=10` | "Who have I talked to most?" | Connection frequency |

## Authentication

All endpoints require an API key in the `X-API-Key` header:

```bash
curl -H "X-API-Key: un_your_api_key" http://localhost:8001/api/v1/persons
```

## Docker

```bash
# Build
docker build -t user-network .

# Run
docker run -p 8001:8001 --env-file .env user-network
```

## Client SDK

Use the provided client in the agent:

```python
from agent.src.graph.client import UserNetworkClient

client = UserNetworkClient(
    base_url="http://localhost:8001",
    api_key="un_your_api_key"
)

# Get sister's contact info
contacts = await client.get_contact_by_role("sister")

# Get mother's interests (for gift suggestions)
interests = await client.get_interests_by_role("mother")

# Traverse: "Who is my brother's wife?"
results = await client.traverse(["brother", "wife"])
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Agent                                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  UserNetworkClient (HTTP + API Key)                     │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   User Network Service                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │ Persons  │  │Relations │  │ Queries  │  ← FastAPI Routes │
│  └──────────┘  └──────────┘  └──────────┘                   │
│         │            │            │                          │
│         └────────────┴────────────┘                          │
│                      │                                       │
│              ┌───────┴───────┐                               │
│              │  Repository   │  ← Database Operations        │
│              └───────────────┘                               │
│                      │                                       │
│              ┌───────┴───────┐                               │
│              │   asyncpg     │  ← Connection Pool            │
│              └───────────────┘                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    PostgreSQL (RDS)                          │
│  ┌──────────┐  ┌──────────────┐  ┌────────────┐             │
│  │ persons  │  │ relationships│  │ audit_logs │             │
│  └──────────┘  └──────────────┘  └────────────┘             │
└─────────────────────────────────────────────────────────────┘
```

## Migration to Neptune

When ready to migrate to Neptune:

1. Export data from PostgreSQL
2. Transform to Neptune bulk load format
3. Update client to use Neptune SDK
4. Deploy Neptune cluster

The data model is graph-ready and translates directly.

