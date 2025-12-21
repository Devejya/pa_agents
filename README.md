# Yennifer - AI Executive Assistant

A waitlist landing page for Yennifer, an AI-powered executive assistant service targeting high-net-worth individuals.

## Project Structure

```
pa_agents/
├── frontend/          # React + TypeScript + Vite
│   ├── src/
│   │   ├── components/   # Reusable UI components
│   │   ├── pages/        # Page components (Home, Checkout)
│   │   ├── hooks/        # Custom React hooks
│   │   ├── services/     # API service layer
│   │   ├── data/         # Static data (tier information)
│   │   └── types/        # TypeScript type definitions
│   └── public/           # Static assets
├── backend/           # Node.js + Express API
│   └── src/
│       ├── config/       # Database configuration
│       ├── routes/       # API routes
│       └── scripts/      # Database initialization
├── deploy/            # Deployment scripts and configs
└── SECRETS/           # SSH keys (gitignored)
```

## Tech Stack

- **Frontend**: React 18, TypeScript, Vite, CSS Modules
- **Backend**: Node.js, Express, TypeScript
- **Database**: PostgreSQL (AWS RDS)
- **Analytics**: PostHog
- **Hosting**: AWS EC2 + Nginx
- **SSL**: Let's Encrypt (Certbot)

## Local Development

### Prerequisites

- Node.js 20.x
- npm

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5173`

### Backend

1. Create the environment file:

```bash
cd backend
cp .env.example .env
# Edit .env with your database credentials
```

2. Install and run:

```bash
npm install
npm run dev
```

The API runs at `http://localhost:3001`

### Initialize Database

```bash
cd backend
npm run db:init
```

## Environment Variables

### Frontend (.env)

```
VITE_PUBLIC_POSTHOG_KEY=your_posthog_key
VITE_PUBLIC_POSTHOG_HOST=https://us.i.posthog.com
VITE_API_URL=               # Leave empty for same-origin in production
```

### Backend (.env)

```
PORT=3001
NODE_ENV=development
DB_HOST=your-rds-endpoint.rds.amazonaws.com
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your_password
CORS_ORIGINS=http://localhost:5173,https://yennifer.ai
```

## Deployment

### First-time EC2 Setup

```bash
# SSH into EC2
ssh -i "./SECRETS/ai_pa_agent_ec2_instance_key_pair.pem" ec2-user@ec2-44-210-105-146.compute-1.amazonaws.com

# Run setup script (uploaded separately or copy contents)
# This installs Node.js, Nginx, Certbot, PM2
```

### Deploy Updates

From your local machine:

```bash
chmod +x deploy/deploy.sh
./deploy/deploy.sh
```

### SSL Setup (One-time)

After DNS propagation (check with `dig yennifer.ai`):

```bash
# SSH into EC2, then:
sudo certbot --nginx -d yennifer.ai -d www.yennifer.ai
```

### Manual Deployment Steps

If the script doesn't work:

1. Build locally:
   ```bash
   cd frontend && npm run build
   cd ../backend && npm run build
   ```

2. Upload to EC2:
   ```bash
   scp -i "./SECRETS/ai_pa_agent_ec2_instance_key_pair.pem" -r frontend/dist backend/dist backend/package.json ec2-user@ec2-44-210-105-146.compute-1.amazonaws.com:/var/www/yennifer/
   ```

3. SSH and restart:
   ```bash
   ssh -i "./SECRETS/ai_pa_agent_ec2_instance_key_pair.pem" ec2-user@ec2-44-210-105-146.compute-1.amazonaws.com
   cd /var/www/yennifer/backend
   npm install --omit=dev
   pm2 restart yennifer-api
   ```

## Database Schema

### signups

| Column | Type | Description |
|--------|------|-------------|
| event_id | UUID | Primary key |
| signup_created_at_est | TIMESTAMPTZ | Signup timestamp (EST) |
| user_email_id | VARCHAR(255) | User's email (unique) |
| user_tier | INTEGER | Selected tier (1, 2, or 3) |

## Pricing Tiers

1. **Essential** ($150/month): Calendar management, travel arrangements, email prioritization
2. **Premier** ($230/month): + Adaptive learning, gift suggestions, draft communications
3. **Private** ($400/month): + Voice calls, incoming call management, priority support

## API Endpoints

- `POST /api/signup` - Submit waitlist signup
- `GET /api/health` - Health check endpoint

## Analytics

PostHog events tracked:
- `$pageview` - Page views with page name
- `tier_selected` - When user clicks on a tier
- `waitlist_signup` - Successful signup
- `waitlist_signup_error` - Failed signup attempt
