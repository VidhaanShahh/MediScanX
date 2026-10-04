# MediScanX

Online-Based Multimodal AI Diagnostic System for Thoracic and Cardiac Disease Detection.

> **Academic prototype** — not a medical device. Sardar Patel Institute of Technology, Mumbai.

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+ (or use SQLite for development)

### Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env       # then edit .env with your values
```

### Run (development)

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/docs for the interactive API documentation.

### Run Tests

```bash
cd backend
pytest ../tests/ -v
```

## Project Structure

```
MediScanX/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── core/                # Config, security, exceptions
│   │   ├── db/                  # SQLAlchemy engine and base
│   │   ├── models/              # ORM models (10 tables)
│   │   ├── schemas/             # Pydantic request/response
│   │   ├── api/                 # Route handlers
│   │   ├── services/            # Business logic
│   │   │   └── preprocessing/   # Image and ECG preprocessing
│   │   └── utils/
│   ├── .env.example
│   └── requirements.txt
├── data/
│   ├── ChestX-ray14/
│   └── PTB-XL/
├── models/
├── tests/
├── PROJECT_SPEC.md
└── README.md
```

## API Endpoints

| Method | Endpoint | Module |
|--------|----------|--------|
| POST | `/api/auth/register` | M1 |
| POST | `/api/auth/login` | M1 |
| POST | `/api/patients/` | M2 |
| GET | `/api/patients/` | M2 |
| GET | `/api/patients/{id}` | M2 |
| POST | `/api/cases` | M2 |
| GET | `/api/cases` | M2 |
| GET | `/api/cases/{id}` | M2 |
| DELETE | `/api/cases/{id}` | M2 |
| GET | `/api/patients/{id}/cases` | M2 |
| POST | `/api/cases/{id}/upload` | M3 |
| POST | `/api/cases/{id}/analyze` | M5–M8 (placeholder) |

## Team

| Name | UID | Role |
|------|-----|------|
| Vidhaan Shah | 2024300212 | Pipeline and database |
| Gaurang Satone | 2024300205 | Frontend and UI |
| Jay Pradhan | 2024300184 | Integration and planning |

Guide: Prof. Anand Godbole
