# Backend

Python API for the SuperAI Hackathon project.

## Tech Stack

- **Language:** Python 3.11+
- **Framework:** TODO (e.g. FastAPI / Flask)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running

```bash
# FastAPI
# uvicorn main:app --reload

# Flask
# flask run
```

The API runs at http://localhost:8000 by default.

## Environment Variables

Create a `.env` file in this directory:

```bash
# API_KEY=...
# DATABASE_URL=...
```

## Project Structure

```
backend/
├── main.py            # App entrypoint
├── requirements.txt   # Python dependencies
└── ...
```

## Tests

```bash
pytest
```
