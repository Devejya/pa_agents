# Gmail LangChain Agent

AI-powered email assistant that connects to your Gmail account.

## Features

- 📬 **Read Emails** - Fetch and search emails
- 📋 **Daily Summary** - AI-generated summary of recent emails
- 🔴 **Priority Detection** - Identify urgent/important emails
- ✏️ **Draft Replies** - Generate draft responses (human-in-the-loop)

## Setup

### 1. Prerequisites

- Python 3.10+
- Google Cloud project with Gmail API enabled
- OAuth credentials downloaded (see Phase 1 setup)

### 2. Install Dependencies

```bash
cd agent
pip install -r requirements.txt
```

### 3. Configure Environment

Create a `.env` file in the `agent/` directory:

```bash
# OpenAI API Key
OPENAI_API_KEY=sk-your-key-here
```

### 4. Google OAuth Credentials

Ensure your OAuth credentials are at:
```
SECRETS/google_oath_credentials.json
```

### 5. Run the Agent

```bash
cd agent
python run.py
```

First run will open a browser for Google OAuth authentication.

## Usage Examples

```
You: Show me my unread emails
You: Summarize my emails from today
You: What are my priority emails?
You: Draft a reply to email ID xxx saying I'll be there
You: Find emails from john@example.com
```

## Security

- ✅ All data stays on your local machine
- ✅ OAuth tokens stored locally in `token.json`
- ✅ Drafts created but NOT sent automatically
- ✅ No email data sent to external servers (except OpenAI for LLM)

## Project Structure

```
agent/
├── requirements.txt     # Python dependencies
├── run.py              # CLI entry point
├── token.json          # OAuth token (auto-generated)
├── README.md
└── src/
    ├── __init__.py
    ├── auth.py         # Gmail OAuth handling
    ├── gmail_agent.py  # Main LangChain agent
    └── tools/
        ├── __init__.py
        ├── read_emails.py    # Email fetching
        ├── summarize.py      # Email summarization
        ├── priority.py       # Priority detection
        └── draft_reply.py    # Reply generation
```

## Troubleshooting

### "Credentials not found"
Ensure `SECRETS/google_oath_credentials.json` exists.

### "Access blocked" during OAuth
Add your email as a test user in Google Cloud Console.

### "OPENAI_API_KEY not set"
Create a `.env` file with your OpenAI API key.



