# Yennifer - AI Executive Assistant

An AI-powered executive assistant that integrates with Google Workspace to help manage emails, calendar, contacts, documents, and more.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                  NGINX (Port 443)                               │
│                         yennifer.ai / www.yennifer.ai                           │
└───────────┬──────────────────────┬──────────────────────┬───────────────────────┘
            │                      │                      │
    ┌───────▼────────┐    ┌───────▼────────┐    ┌───────▼────────┐
    │   Webapp SPA   │    │  Yennifer API  │    │  User Network  │
    │  (Static Files)│    │   (Port 8000)  │    │   (Port 8001)  │
    │                │    │                │    │                │
    │   React/Vite   │    │   FastAPI      │    │   FastAPI      │
    │   Tailwind CSS │    │   Python 3.x   │    │   Python 3.x   │
    └────────────────┘    └───────┬────────┘    └───────┬────────┘
                                  │                      │
                                  │                      │
                    ┌─────────────▼──────────────────────▼─────────────┐
                    │                PostgreSQL (AWS RDS)              │
                    │                                                  │
                    │  ┌─────────────────┐  ┌──────────────────────┐   │
                    │  │  yennifer_chat  │  │    user_network      │   │
                    │  │  - users        │  │    - persons         │   │
                    │  │  - chat_*       │  │    - relationships   │   │
                    │  │  - memories     │  │    - audit_logs      │   │
                    │  │  - interests    │  └──────────────────────┘   │
                    │  │  - tasks        │                             │
                    │  │  - oauth_tokens │                             │
                    │  └─────────────────┘                             │
                    └──────────────────────────────────────────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │    External Services      │
                    │  - OpenAI API (GPT-4o)    │
                    │  - Google Workspace APIs  │
                    │  - AWS KMS (Encryption)   │
                    └───────────────────────────┘
```

## Project Structure

```
pa_agents/
├── webapp/                  # React + TypeScript + Vite + Tailwind
│   └── src/
│       ├── components/      # UI components (Layout, Sidebar, Chat, etc.)
│       ├── contexts/        # React contexts (AuthContext)
│       ├── pages/           # Page components (Chat, Contacts, Tasks, etc.)
│       └── services/        # API client layer
│
├── services/
│   ├── yennifer_api/        # Main AI Assistant API (FastAPI)
│   │   └── app/
│   │       ├── core/        # Agent, auth, encryption, scheduler
│   │       ├── db/          # Database connections, repositories
│   │       ├── jobs/        # Background jobs (sync, archival)
│   │       ├── routes/      # API endpoints
│   │       └── tools/       # Google Workspace integrations
│   │
│   └── user_network/        # Relationship Graph Service (FastAPI)
│       └── src/
│           ├── api/         # API routes (persons, relationships)
│           ├── core/        # Config, security
│           └── db/          # Schema, repository, migrations
│
├── agent/                   # Standalone CLI agent (legacy)
├── frontend/                # Waitlist landing page (legacy)
├── backend/                 # Waitlist API (Node.js, legacy)
├── deploy/                  # Deployment scripts and configs
│   ├── deploy.sh            # Deployment script
│   ├── ecosystem.config.cjs # PM2 configuration
│   └── nginx.conf           # Nginx reverse proxy config
└── SECRETS/                 # OAuth credentials (gitignored)
```

## Services

### 1. Yennifer Chat API (`yennifer_api`)

The core AI assistant service powered by GPT-4o.

**Port:** 8000

**Features:**
- Natural language conversation with context awareness
- Google Workspace integration (Gmail, Calendar, Drive, Docs, Sheets, Slides)
- Per-user encrypted data storage (memories, interests, tasks, dates)
- Background job scheduler for sync operations
- Audit logging for compliance

**API Routes:**

| Prefix | Description |
|--------|-------------|
| `/api/v1/auth` | Google OAuth authentication |
| `/api/v1/chat` | Conversational AI chat |
| `/api/v1/workspace` | Google Workspace tools |
| `/api/v1/contacts` | Contact management |
| `/api/v1/user-data` | User preferences & memories |
| `/api/v1/jobs` | Background job management |

### 2. User Network Service (`user_network`)

Microservice for managing user relationship graphs.

**Port:** 8001

**Features:**
- Person management with full-text search
- Relationship tracking (family, friends, work, acquaintance)
- Connection frequency tracking (calls, texts, meetings)
- Interest matching between persons

**API Routes:**

| Prefix | Description |
|--------|-------------|
| `/api/v1/persons` | Person CRUD operations |
| `/api/v1/relationships` | Relationship management |
| `/api/v1/queries` | Graph queries |
| `/api/v1/sync` | Sync with external services |

### 3. Webapp (React SPA)

Single-page application for interacting with Yennifer.

**Features:**
- Chat interface with the AI assistant
- Contact directory with relationship info
- Tasks, reminders, and upcoming events views
- Mobile-responsive design (iPhone, iPad, Android)
- Google OAuth login

**Pages:**
- `/` - Chat (main interface)
- `/contacts` - Contact directory
- `/tasks` - Task management
- `/reminders` - Important dates & reminders
- `/upcoming` - Upcoming events
- `/reports` - Reports & summaries

### 4. Legacy Services

- **frontend/** - Waitlist landing page (React + Vite)
- **backend/** - Signup API (Node.js + Express)
- **agent/** - Standalone CLI agent for testing

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS |
| **Backend** | FastAPI (Python 3.10+), Pydantic |
| **AI/LLM** | OpenAI GPT-4o, LangChain |
| **Database** | PostgreSQL 15 (AWS RDS) |
| **Authentication** | Google OAuth 2.0, JWT tokens |
| **Encryption** | AWS KMS (KEK), Fernet (DEK per user) |
| **Process Manager** | PM2 |
| **Reverse Proxy** | Nginx with SSL (Let's Encrypt) |
| **Hosting** | AWS EC2 |

## Database Schema

### Yennifer Chat Database

| Table | Description |
|-------|-------------|
| `users` | Core user identity with per-user encryption keys |
| `user_identities` | OAuth provider identities (Google, etc.) |
| `user_oauth_tokens` | Encrypted Google OAuth tokens |
| `chat_sessions` | Chat conversation sessions |
| `chat_messages` | Individual messages (encrypted) |
| `interests` | User interests and hobbies |
| `important_dates` | Birthdays, anniversaries, events |
| `user_tasks` | Scheduled and recurring tasks |
| `memories` | Facts the agent should remember |
| `audit_log` | Security audit trail |

### User Network Database

| Table | Description |
|-------|-------------|
| `persons` | People (nodes) with contact info |
| `relationships` | Connections between people (edges) |
| `audit_logs` | Graph access audit trail |

**Security Features:**
- Row-Level Security (RLS) for multi-tenant isolation
- Per-user encryption keys (DEK wrapped by AWS KMS KEK)
- OAuth tokens encrypted at rest

## API Endpoints

### Authentication

```
GET  /api/v1/auth/login            # Initiate Google OAuth
GET  /api/v1/auth/callback         # OAuth callback handler
POST /api/v1/auth/logout           # Clear session
GET  /api/v1/auth/me               # Get current user info
```

### Chat

```
POST   /api/v1/chat                # Send message to assistant
GET    /api/v1/chat/history        # Get chat history
DELETE /api/v1/chat/history        # Clear chat history
GET    /api/v1/chat/sessions       # List chat sessions
```

### Google Workspace

```
# Calendar
GET    /api/v1/workspace/calendar/events
POST   /api/v1/workspace/calendar/events
PUT    /api/v1/workspace/calendar/events/{id}
DELETE /api/v1/workspace/calendar/events/{id}

# Gmail
GET    /api/v1/workspace/gmail/emails
GET    /api/v1/workspace/gmail/emails/{id}
POST   /api/v1/workspace/gmail/send
GET    /api/v1/workspace/gmail/search

# Drive
GET    /api/v1/workspace/drive/files
GET    /api/v1/workspace/drive/files/{id}
GET    /api/v1/workspace/drive/search

# Docs, Sheets, Slides
GET    /api/v1/workspace/docs/{id}
GET    /api/v1/workspace/sheets/{id}
GET    /api/v1/workspace/slides/{id}
```

### User Data

```
# Interests
GET    /api/v1/user-data/interests
POST   /api/v1/user-data/interests
PUT    /api/v1/user-data/interests/{id}
DELETE /api/v1/user-data/interests/{id}

# Important Dates
GET    /api/v1/user-data/dates
POST   /api/v1/user-data/dates
PUT    /api/v1/user-data/dates/{id}
DELETE /api/v1/user-data/dates/{id}

# Tasks
GET    /api/v1/user-data/tasks
POST   /api/v1/user-data/tasks
PUT    /api/v1/user-data/tasks/{id}
DELETE /api/v1/user-data/tasks/{id}

# Memories
GET    /api/v1/user-data/memories
POST   /api/v1/user-data/memories
DELETE /api/v1/user-data/memories/{id}
```

### Contacts (Proxied to User Network)

```
GET    /api/v1/contacts              # List all contacts
GET    /api/v1/contacts/core-user    # Get core user
GET    /api/v1/contacts/{id}         # Get contact by ID
GET    /api/v1/contacts/search       # Search contacts
GET    /api/v1/contacts/{id}/relationships  # Get relationships
```

## Local Development

### Prerequisites

- Node.js 20.x
- Python 3.10+
- PostgreSQL 15+
- OpenAI API key
- Google Cloud project with OAuth configured

### Webapp

```bash
cd webapp
npm install
npm run dev
# Runs at http://localhost:5173
```

### Yennifer API

```bash
cd services/yennifer_api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env file
cat > .env << EOF
ENVIRONMENT=development
OPENAI_API_KEY=sk-your-key
DATABASE_URL=postgresql://user:pass@localhost:5432/yennifer
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
JWT_SECRET=your-jwt-secret
EOF

uvicorn app.main:app --reload --port 8000
```

### User Network Service

```bash
cd services/user_network
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env file
cat > .env << EOF
ENVIRONMENT=development
DATABASE_URL=postgresql://user:pass@localhost:5432/user_network
EOF

uvicorn src.main:app --reload --port 8001
```

### Database Migrations

```bash
# Yennifer API migrations
cd services/yennifer_api
psql -U postgres -d yennifer -f app/db/migrations/001_user_oauth_tokens.sql
psql -U postgres -d yennifer -f app/db/migrations/002_users_identity.sql
# ... run all migrations in order

# User Network migrations
cd services/user_network
psql -U postgres -d user_network -f src/db/schema.sql
psql -U postgres -d user_network -f src/db/migrations/001_add_sync_support.sql
```

## Deployment

### Deploy All Services

```bash
./deploy/deploy.sh
```

### Deploy Individual Services

```bash
./deploy/deploy.sh --webapp      # Deploy webapp only
./deploy/deploy.sh --chat-api    # Deploy Yennifer API only
./deploy/deploy.sh --user-network # Deploy User Network only
```

### EC2 Setup (First Time)

```bash
# SSH into EC2
ssh -i "./SECRETS/ai_pa_agent_ec2_instance_key_pair.pem" ec2-user@<ec2-ip>

# Run setup script
./deploy/setup-ec2.sh
```

### SSL Setup (First Time)

```bash
# After DNS propagation
sudo certbot --nginx -d yennifer.ai -d www.yennifer.ai
```

### PM2 Service Management

   ```bash
pm2 list                    # View all services
pm2 logs yennifer-chat      # View chat API logs
pm2 restart yennifer-chat   # Restart chat API
pm2 restart all             # Restart all services
```

## Environment Variables

### Yennifer API (`.env`)

   ```bash
ENVIRONMENT=production
PORT=8000
HOST=127.0.0.1

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Database
DATABASE_URL=postgresql://user:pass@host:5432/yennifer

# Google OAuth
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://yennifer.ai/api/v1/auth/callback

# JWT
JWT_SECRET=...
JWT_ALGORITHM=HS256

# AWS KMS (for encryption)
AWS_REGION=us-east-1
KMS_KEY_ID=...

# CORS
CORS_ORIGINS=https://yennifer.ai
```

### User Network (`.env`)

   ```bash
ENVIRONMENT=production
PORT=8001
HOST=127.0.0.1
DATABASE_URL=postgresql://user:pass@host:5432/user_network
CORS_ORIGINS=https://yennifer.ai,http://127.0.0.1:8000
```

## Security

- **Authentication:** Google OAuth 2.0 with JWT session tokens
- **Encryption at Rest:** Per-user AES-256 encryption keys wrapped by AWS KMS
- **Row-Level Security:** PostgreSQL RLS for multi-tenant data isolation
- **HTTPS:** TLS 1.2+ via Let's Encrypt
- **Rate Limiting:** Nginx rate limiting (10 req/s burst 10-20)
- **Audit Logging:** All data access logged for compliance

## Analytics

PostHog events tracked:
- `$pageview` - Page views
- `tier_selected` - Pricing tier selection
- `waitlist_signup` - Successful signup

## License

Proprietary - All rights reserved.
