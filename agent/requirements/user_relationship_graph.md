# User Relationship Graph

## Goal

Building a user graph network where the core user is connected to their contacts, with edges representing relationships.

## Problem Statement

The agent has no information about the core user's contacts, their connections, aliases, addresses, and other info.

This leads to issues such as:
- Core user prompts the agent to message their sister "running 5 minutes late". The agent is unaware who the contact is that they are supposed to message, email, call, etc.

## Solution

Build a graph database to capture information about different people in the user's network, with relevant information for each person, along with how they are all connected to each other and the core user.

---

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Database | PostgreSQL (with migration path to Neptune) | Already have RDS, handles 100-200 contacts easily, built-in full-text search |
| Relationship Model | Single edge with role pair | No data duplication, atomic updates |
| Interest Storage | Denormalized (embedded in Person) | Fast reads, simple writes at low scale |
| Full-Text Search | PostgreSQL tsvector | Built-in, upgrade to vectors later |
| PII Encryption | AWS RDS encryption at rest | Transparent, no query impact |
| Audit Logging | Application-level to CloudWatch | Zero infrastructure overhead |
| Status Field | Enum (active/deceased/blocked/archived) | More expressive than boolean |
| Relationship History | New edge + `ended_at` timestamp | Preserves historical data |

---

## Schema

### Person Node

**Required Fields:**
- `id`: UUID (system generated)
- `name`: VARCHAR NOT NULL
- `country`: VARCHAR NOT NULL
- At least one of: `personal_cell`, `work_cell`, `work_email`, `personal_email`
- If `latest_title` is set, `company` is also required

**All Fields:**

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | Primary key, auto-generated |
| name | VARCHAR(200) | NOT NULL |
| aliases | TEXT[] | Stored lowercase |
| is_core_user | BOOLEAN | Default FALSE |
| status | ENUM | active, deceased, blocked, archived |
| work_email | VARCHAR(254) | Lowercase |
| personal_email | VARCHAR(254) | Lowercase, duplication allowed |
| work_cell | VARCHAR(20) | E.164 format: +15551234567 |
| personal_cell | VARCHAR(20) | E.164 format |
| secondary_cell | VARCHAR(20) | E.164 format |
| company | VARCHAR(200) | |
| latest_title | VARCHAR(200) | Requires company |
| expertise | VARCHAR(500) | |
| address | VARCHAR(500) | |
| country | VARCHAR(100) | NOT NULL |
| city | VARCHAR(100) | |
| state | VARCHAR(100) | |
| instagram_handle | VARCHAR(100) | |
| religion | VARCHAR(100) | |
| ethnicity | VARCHAR(100) | |
| country_of_birth | VARCHAR(100) | |
| city_of_birth | VARCHAR(100) | |
| interests | JSONB | Array of Interest objects |
| search_vector | tsvector | Auto-updated for full-text search |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### Interest Object (Embedded in Person)

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | |
| name | VARCHAR(100) | NOT NULL, lowercase |
| type | ENUM | sport, videogame, arts, crafts, reading, writing, fiction, travel, food, tv, movies, music, outdoors, technology, other |
| level | INT | 1-100 score |
| monthly_frequency | INT | Times per month (can be > 30) |
| sample_instance | VARCHAR(500) | Example of indulging in interest |
| sample_instance_date | DATE | When the sample instance occurred |

### Relationship Edge

Uses **single edge with role pair** for directionality.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | Primary key |
| from_person_id | UUID | FK to persons |
| to_person_id | UUID | FK to persons |
| category | ENUM | family, friends, work, acquaintance |
| from_role | VARCHAR(100) | What from_person is to to_person (e.g., "brother") |
| to_role | VARCHAR(100) | What to_person is to from_person (e.g., "sister") |
| connection_counts | JSONB | Communication frequency metrics |
| similar_interests | TEXT[] | Shared interest names |
| first_meeting_date | DATE | |
| length_of_relationship_years | INT | |
| length_of_relationship_days | INT | |
| is_active | BOOLEAN | Default TRUE |
| ended_at | TIMESTAMPTZ | Set when relationship ends |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

**Relationship Types by Category:**

| Category | Example Roles |
|----------|---------------|
| Family | sister, brother, mother, father, sister-in-law, brother-in-law, father-in-law, mother-in-law, step-father, step-mother, nephew, niece, grandfather, grandmother, granddaughter, grandson, uncle, aunt, cousin |
| Friends | friend, best-friend, childhood-friend |
| Work | coworker, manager, ex-manager, ex-coworker, ex-professor, professor, client, mentor, direct-report, skip-level-manager |
| Acquaintance | mutual-friend, neighbor, gym-buddy |

### ConnectionCounts Object (Embedded in Relationship)

| Field | Type | Notes |
|-------|------|-------|
| call_count_past_year | INT | |
| call_count_past_six_months | INT | |
| call_count_past_three_months | INT | |
| call_count_past_one_month | INT | |
| call_count_past_one_week | INT | |
| call_count_past_one_day | INT | |
| meet_count_past_six_months | INT | In-person meetings |
| meet_count_past_three_months | INT | |
| meet_count_past_one_month | INT | |
| meet_count_past_one_week | INT | |
| meet_count_past_one_day | INT | |
| text_count_past_six_months | INT | All platforms: WhatsApp, Messenger, iMessage, email, Instagram |
| text_count_past_three_months | INT | |
| text_count_past_one_month | INT | |
| text_count_past_one_week | INT | |
| text_count_past_one_day | INT | |
| last_call_at | TIMESTAMPTZ | |
| last_text_at | TIMESTAMPTZ | |
| last_meet_at | TIMESTAMPTZ | |

---

## Query Patterns

### Agent Request → Graph Query Mapping

| Agent Request | Graph Query |
|---------------|-------------|
| "Call my sister and let her know..." | `get_core_user_contact_by_role("sister")` |
| "Ask Rachel if she's coming to the party" | `get_contact_info_by_name("Rachel")` |
| "Buy Rachel a present for her brother" | `traverse_from_core_user(["Rachel's relationship", "brother"])` → interests |
| "I have a meeting with Rajesh, where is he from?" | `get_person_with_interests_by_name("Rajesh")` |
| "My mother's party is tonight, buy her a gift" | `get_core_user_contact_interests("mother")` |
| "Who is my sister's husband?" | `traverse_from_core_user(["sister", "husband"])` |

### Full-Text Search

The `search_vector` column enables queries like:
- "Find everyone interested in skiing"
- "Who works in engineering?"
- "Contacts at Google"

---

## Data Population

### Phase 1: Inference
- Inferred from emails, conversations, calendar events
- Agent extracts names, relationships, interests from communications

### Phase 2: Contact Integration
- Import from Google Contacts, LinkedIn, phone contacts
- Supplement and validate inferred data

### Interest Level Scoring (1-100)
- Manually inputted by core user
- Inferred by agent based on frequency of mentions in texts/emails

---

## Constraints

- **Scale**: 100-200 connections per core user (guidance, not hard limit)
- **Traversal**: Support multi-hop queries (e.g., "sister's husband's mother")
- **Aliases**: Multiple people can share an alias; agent handles disambiguation
- **Shared Contacts**: One node per person, multiple relationship edges

---

## Edge Cases

| Scenario | Handling |
|----------|----------|
| Two friends named "Mike" | Agent asks user to clarify |
| Ex-coworker becomes friend | Multiple relationship edges (preserves history) |
| Deceased contact | `status: deceased` (not deleted) |
| Same email for work/personal | Duplication allowed |
| Sub-graph relationships | Supported (e.g., "sister's husband" has own relationships) |

---

## Files

| File | Purpose |
|------|---------|
| `src/graph/__init__.py` | Module exports |
| `src/graph/models.py` | Pydantic models (Person, Relationship, Interest, etc.) |
| `src/graph/schema.sql` | PostgreSQL schema with indexes and triggers |
| `src/graph/repository.py` | CRUD operations with audit logging |
| `src/graph/queries.py` | Graph traversal queries using recursive CTEs |

---

## Migration Path to Neptune

When scale demands it (500+ contacts, complex traversals, latency issues):

1. **Data Model**: Already graph-ready (nodes = Person, edges = Relationship)
2. **Query Translation**: PostgreSQL CTEs → openCypher/Gremlin
3. **Export**: Use `pg_dump` or custom script to export as CSV/JSON
4. **Import**: Neptune bulk loader from S3

Example query translation:

**PostgreSQL (current):**
```sql
WITH RECURSIVE path AS (
    SELECT p2.* FROM persons p1
    JOIN relationships r ON p1.id = r.from_person_id
    JOIN persons p2 ON r.to_person_id = p2.id
    WHERE p1.is_core_user AND r.to_role = 'sister'
)
SELECT * FROM path;
```

**Neptune (openCypher):**
```cypher
MATCH (core:Person {is_core_user: true})-[r:RELATIONSHIP {to_role: 'sister'}]->(sister:Person)
RETURN sister
```

---

## Audit Logging

Application-level logging to CloudWatch:

```python
def log_pii_access(user_id, action, resource_type, resource_id, fields):
    audit_logger.info({
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": user_id,
        "action": action,  # "read", "write", "delete"
        "resource_type": resource_type,  # "person", "relationship"
        "resource_id": resource_id,
        "fields_accessed": fields,
    })
```

Also stored in `audit_logs` table for queryability.

---

## TODO

- [ ] Set up PostgreSQL schema in RDS
- [ ] Implement graph repository and queries
- [ ] Add agent tools to query the graph
- [ ] Build data inference from emails
- [ ] Integrate contact import
- [ ] Set up CloudWatch logging
- [ ] Add connection count update jobs
