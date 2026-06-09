# SuperAI Hackathon

> _One-line description of what this project does._

## Overview

<!-- Describe the problem you're solving and your approach. -->

TODO: Add a short summary of the project, the problem it solves, and the key features.

## Tech Stack

- **Backend:** Python
- **Frontend:** Next.js (TypeScript)

## Project Structure

```
superai-hackathon/
├── backend/    # Python API
└── frontend/   # Next.js (TypeScript) app
```

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- pnpm

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# Run the server (adjust to your framework)
# uvicorn main:app --reload       # FastAPI
# flask run                       # Flask
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

The app will be available at http://localhost:3000.

## Environment Variables

Create a `.env` file in each package as needed:

```bash
# backend/.env
# API_KEY=...

# frontend/.env.local
# NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Scripts

| Location  | Command          | Description              |
| --------- | ---------------- | ------------------------ |
| frontend  | `pnpm dev`       | Start the dev server     |
| frontend  | `pnpm build`     | Build for production     |
| backend   | `uvicorn ...`    | Start the API server     |

## Team

<!-- List team members here. -->

## License

TODO: Choose a license (e.g. MIT).
