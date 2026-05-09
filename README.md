# GenAI Debate Twin — Multi-Agent Debate System

A professional-grade multi-agent debate system powered by LangGraph, FastAPI, ChromaDB, and Next.js.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Next.js Frontend                        │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│   │  Arena.tsx   │  │ Scoreboard   │  │  Debate Feed     │  │
│   └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
└──────────┼─────────────────┼───────────────────┼────────────┘
           │         WebSocket /ws/debate          │
┌──────────▼─────────────────▼───────────────────▼────────────┐
│                      FastAPI Backend                          │
│   ┌──────────────────────────────────────────────────────┐   │
│   │              LangGraph Orchestrator                   │   │
│   │  ┌─────────────┐  ┌────────────────┐  ┌──────────┐  │   │
│   │  │ User Twin   │→ │   Challenger   │→ │  Judge   │  │   │
│   │  │   Node      │  │     Node       │  │   Node   │  │   │
│   │  └──────┬──────┘  └────────────────┘  └──────────┘  │   │
│   │         │ RAG Query                                   │   │
│   │  ┌──────▼──────────────────────────────────────────┐ │   │
│   │  │         ChromaDB Vector Store                    │ │   │
│   │  │  (Persona embeddings + debate knowledge base)    │ │   │
│   │  └─────────────────────────────────────────────────┘ │   │
│   └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

## Stack
- **Backend**: Python 3.10+, FastAPI, LangGraph, ChromaDB
- **LLM**: Claude 3.5 Sonnet (via Anthropic SDK)
- **Frontend**: Next.js 14, Tailwind CSS, Shadcn/UI, Lucide React
- **Comms**: WebSockets for real-time streaming

## Quick Start

### Backend
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Add your ANTHROPIC_API_KEY
uvicorn api.main:app --reload --port 8000
```

### Ingest Persona Data
```bash
python -m rag.ingest --file ../data/personas/my_bio.txt --persona default
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000
