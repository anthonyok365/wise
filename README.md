# Hiring Signal Detection System

A production-ready, async system for tracking company career pages, extracting job listings, classifying job status using AI, and computing hiring activity scores.

## 🎯 Features

- **Career Page Scraping**: Async Playwright-based scraper with flexible parsing strategies
- **AI Classification**: Job status classification using Ollama (Mistral/LLaMA3) with HuggingFace fallback
- **Keyword Fallback**: Mandatory keyword-based detection when AI is unavailable
- **Hiring Signals**: Computes hiring activity scores for companies
- **Background Jobs**: APScheduler for periodic scraping and validation
- **RESTful API**: FastAPI backend with async endpoints
- **Database**: PostgreSQL with async SQLAlchemy

## 🏗️ Architecture

```
/app
├── api/              # FastAPI routes and schemas
│   ├── routes.py     # API endpoints
│   └── schemas.py    # Pydantic models
├── core/             # Core configuration
│   ├── config.py     # Settings management
│   └── logging.py    # Logging setup
├── db/               # Database layer
│   ├── models.py    # SQLAlchemy models
│   └── database.py  # Connection management
├── scraper/          # Playwright scraper
│   ├── browser.py   # Browser management
│   ├── parser.py    # Job listing parser
│   └── scraper.py   # Main scraper class
├── services/         # Business logic
│   ├── ai_classifier.py       # AI classification
│   └── hiring_signal_engine.py # Scoring engine
└── tasks/            # Background jobs
    ├── scheduler.py # Task definitions
    └── runner.py    # APScheduler integration
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+ (optional, for Celery)
- Ollama (optional, for local AI)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd hiring-signal-detector
```

2. Create virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .
```

3. Install Playwright browsers:
```bash
playwright install chromium --with-deps
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your settings
```

5. Start the application:
```bash
# Using Docker Compose (recommended)
docker-compose up -d

# Or locally
uvicorn app.main:app --reload
```

### Docker Deployment

```bash
# Start all services
docker-compose up -d

# With Ollama for AI
docker-compose --profile ai up -d
```

## ⚙️ Configuration

All settings are managed via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DEBUG` | Enable debug mode | `false` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `DB_HOST` | PostgreSQL host | `localhost` |
| `DB_PORT` | PostgreSQL port | `5432` |
| `DB_USER` | Database user | `hiring_signal` |
| `DB_PASSWORD` | Database password | - |
| `DB_NAME` | Database name | `hiring_signal_db` |
| `AI_PROVIDER` | AI provider (`ollama`, `huggingface`) | `ollama` |
| `OLLAMA_URL` | Ollama API URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Ollama model name | `mistral` |
| `HUGGINGFACE_TOKEN` | HuggingFace API token | - |
| `SCHEDULER_ENABLED` | Enable background scheduler | `true` |
| `SCHEDULER_SCRAPER_INTERVAL_HOURS` | Scraper interval | `6` |
| `SCHEDULER_VALIDATOR_INTERVAL_HOURS` | Validator interval | `24` |

## 📡 API Endpoints

### Jobs

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/jobs` | List all jobs (paginated) |
| `GET` | `/api/v1/jobs/{id}` | Get job details |
| `POST` | `/api/v1/jobs` | Create a job |
| `PATCH` | `/api/v1/jobs/{id}` | Update a job |
| `DELETE` | `/api/v1/jobs/{id}` | Delete a job |

### Companies

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/companies` | List all companies |
| `GET` | `/api/v1/companies/{id}` | Get company details |
| `GET` | `/api/v1/companies/{id}/jobs` | Get company's jobs |
| `POST` | `/api/v1/companies` | Create a company |
| `PATCH` | `/api/v1/companies/{id}` | Update a company |
| `DELETE` | `/api/v1/companies/{id}` | Delete a company |

### Statistics

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/stats` | Get overall hiring statistics |

### Scheduler

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/scheduler/status` | Get job status |
| `POST` | `/api/v1/scheduler/trigger/{job_id}` | Trigger a job |
| `POST` | `/api/v1/jobs/trigger` | Manually run scraper |
| `POST` | `/api/v1/jobs/validate` | Manually validate jobs |
| `POST` | `/api/v1/signals/recalculate` | Recalculate signals |

### Documentation

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 🤖 AI Classification

The system uses a tiered approach for job classification:

1. **Ollama** (Primary): Local LLM for fast, private inference
2. **HuggingFace** (Fallback): Remote inference API
3. **Keyword Detection** (Always): Fallback to pattern matching

### Closed Job Keywords

- "no longer accepting applications"
- "position filled"
- "job expired"
- "this role is no longer available"
- "application closed"
- "we've filled this position"

## 📊 Hiring Signal Scoring

| Action | Score Change |
|--------|--------------|
| New job detected | +5 |
| More than 3 new jobs | +10 bonus |
| Job updated | +3 |
| Job closed | -5 |

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/test_ai_classifier.py -v
```

## 🔧 Development

### Code Quality

```bash
# Format code
ruff format .

# Lint code
ruff check .

# Type checking
mypy app/
```

### Adding New Companies

```bash
# Via API
curl -X POST http://localhost:8000/api/v1/companies \
  -H "Content-Type: application/json" \
  -d '{"company_name": "Acme Corp", "career_page_url": "https://acme.com/careers"}'
```

### Site-Specific Configuration

```bash
# Add custom selectors for a company
curl -X POST http://localhost:8000/api/v1/companies/1/config \
  -H "Content-Type: application/json" \
  -d '{
    "job_listing_selector": "div.job-card",
    "job_title_selector": "h3.job-title",
    "pagination_type": "load_more"
  }'
```

## 🚢 Production Deployment

### Environment Variables

```bash
# Set secure credentials
export DB_PASSWORD=$(openssl rand -base64 32)
export HUGGINGFACE_TOKEN=your_token_here
```

### Docker Swarm

```bash
docker stack deploy -c docker-compose.yml hiring-signal
```

### Health Checks

```bash
# Check service health
curl http://localhost:8000/api/v1/health

# Check scheduler status
curl http://localhost:8000/api/v1/scheduler/status
```

## 📝 License

MIT License - see LICENSE file for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## 🔗 Related Projects

- [Playwright](https://playwright.dev/) - Browser automation
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [SQLAlchemy](https://www.sqlalchemy.org/) - ORM
- [Ollama](https://ollama.ai/) - Local LLM inference
