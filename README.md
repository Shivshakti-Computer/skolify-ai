---
title: Skolify AI
emoji: 🎓
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
app_port: 7860
---

# Skolify AI Backend

RAG-based AI chatbot for Skolify School Management System.

## Features
- 🤖 Groq LLM (Llama 3.3 70B)
- 🔍 Semantic search (ChromaDB + sentence-transformers)
- 💬 Conversation memory (SQLite/Turso)
- 🏫 Multi-tenant support (Portal mode)

## API Endpoints
- `POST /api/chat` - Chat endpoint
- `GET /api/health` - Health check
- `GET /api/stats` - Statistics (admin only)

## Environment Variables
Set in Hugging Face Spaces Settings:

```env
GROQ_API_KEY=your_groq_key_here
ADMIN_API_KEY=your_admin_key_here
APP_ENV=production

# Optional - Turso for production DB
CONV_STORAGE=sqlite
# TURSO_DATABASE_URL=libsql://...
# TURSO_AUTH_TOKEN=...