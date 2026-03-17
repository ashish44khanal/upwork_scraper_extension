# Scraper API

A robust FastAPI-based backend for the Scraping Extension.

## Project Structure

The project follows a modular structure for scalability:

```text
scraper_api/
├── src/
│   ├── api/                # API route handlers
│   │   └── v1/             # Version 1 of the API
│   │       ├── endpoints/  # Specific route logic (e.g., health, scraper)
│   │       └── api.py      # Main router including all v1 endpoints
│   ├── core/               # Global configuration and settings
│   ├── schemas/            # Pydantic models for request/response validation
│   ├── services/           # Business logic and external integrations
│   └── main.py             # Application entry point
├── pyproject.toml          # Project dependencies and metadata
└── README.md               # Project documentation
```

## Getting Started

### Prerequisites

- Python 3.12+
- `uv` (recommended for dependency management)

### Installation

1. Clone the repository.
2. Install dependencies:
   ```bash
   uv sync
   ```

### Running the API

You can run the API in development mode with auto-reload:

```bash
# Recommended way (as a module)
python -m src.main

# Or directly
python src/main.py
```

The API will be available at `http://127.0.0.1:8000`.

### API Documentation

Once the server is running, you can access the interactive API documentation:

- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

## API Endpoints

### Health Check

- **URL**: `/api/v1/health`
- **Method**: `GET`
- **Response**: `{"status": "ok"}`
