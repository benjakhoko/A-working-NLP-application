# NLP Smart Analyzer

A Flask-based text analysis workspace for extracting keywords, summarising documents, detecting language, analysing sentiment, explaining content, and translating text. The project is packaged as a full web application with a server-rendered frontend and JSON API endpoints for authenticated users.

The app is built around a lightweight document workflow: users upload `.txt`, `.pdf`, or `.docx` files, the backend extracts text, and then NLP tools can analyse it directly in the browser or through API requests.

## Project overview

This application is designed for:

- academic or research text review
- document summarisation and extraction
- language identification and multilingual translation
- sentiment analysis
- easy history tracking of prior analyses
- admin management of registered users

The interface brand is “Verba”, and the application uses Flask, SQLAlchemy, Flask-Login-style session authentication, and a collection of NLP libraries.

## Key features

- Document upload and extraction from plain text, PDF, and DOCX files
- Keyword extraction with multiple algorithms:
  - TF-IDF
  - RAKE
  - YAKE
- Extractive and abstractive summarisation
- Language detection for supported languages
- Sentiment scoring with VADER and optional multilingual model support
- Text explanations using local models or OpenAI-compatible APIs
- Translation via MyMemory, LibreTranslate, OpenAI-compatible endpoints, or local models
- Per-user analysis history and recent activity dashboard
- Admin panel for managing user accounts
- Rate limiting, security headers, and request validation

## Technology stack

- Python 3
- Flask 3
- Flask-SQLAlchemy
- Flask-Migrate
- Flask-WTF
- PyMySQL
- SQLite default, MySQL-ready for production
- NLTK, spaCy, scikit-learn, YAKE, RAKE-NLTK, langdetect
- PyMuPDF, python-docx, reportlab
- Transformers + PyTorch for model-backed summarisation/explanation features
- pytest for automated tests

## Repository structure

```text
.
├── backend/
│   ├── __init__.py
│   ├── extensions.py
│   ├── models.py
│   ├── routes/
│   ├── services/
│   └── utils/
├── evaluation/
│   ├── datasets/
│   └── results/
├── frontend/
│   ├── static/
│   └── templates/
├── instance/
│   └── ita_dev.db
├── migrations/
├── scripts/
├── tests/
├── .env.example
├── config.py
├── requirements.txt
├── run.py
├── tailwind.config.js
└── README.md
```

## Getting started

### 1. Clone the repository

```bash
git clone https://github.com/benjakhoko/A- working- nlp-application.git
cd NLP-Smart-Analyzer
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

On Windows:

```powershell
.venv\Scripts\activate
```

On macOS/Linux:

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> Note: large NLP libraries like PyTorch and Hugging Face models may download additional resources on first use.

### 4. Configure environment variables

Copy the example environment file and adjust the values you need:

```bash
copy .env.example .env
```

or on Unix/macOS:

```bash
cp .env.example .env
```

Important settings include:

- `FLASK_ENV` (`development` or `production`)
- `SECRET_KEY`
- `DATABASE_URL` (defaults to SQLite)
- `SUMMARIZATION_MODEL`
- `EXPLANATION_PROVIDER`
- `OPENAI_API_KEY` for OpenAI-backed explanation or translation
- `TRANSLATION_PROVIDER`

The default configuration is intentionally usable without a dedicated database server and stores data in `instance/ita_dev.db`.

## Running the app

Start the development server with:

```bash
python run.py
```

Then open:

```text
http://127.0.0.1:5000
```

## Typical workflows

### User registration and login

- Create an account from the registration page
- Sign in to access the dashboard and workspace

### Document analysis

- Upload a `.txt`, `.pdf`, or `.docx` file
- Select a feature such as keywords, summarisation, or sentiment
- Run the analysis and view the result in the app

### Dashboard and history

- View recent analyses, activity, and statistics
- Review prior analysis results from the history page

### Admin functions

- Promote a user to admin via the application data or admin tools
- Manage user access in the admin interface

## API notes

The project exposes a JSON API under `/api/...` for authenticated interactions. Examples include:

- `/api/documents/upload`
- `/api/keywords/extract`
- `/api/summarization/extractive`
- `/api/summarization/abstractive`
- `/api/language/detect`
- `/api/sentiment/analyse`
- `/api/explanation/generate`
- `/api/translation/translate`
- `/api/auth/login`
- `/api/auth/me`

The frontend is served by Flask templates in `frontend/templates`, while the JavaScript uses static assets in `frontend/static/js`.

## Testing

Run the automated test suite with:

```bash
pytest
```

The project includes tests covering:

- authentication flows
- document upload and validation
- dashboard and page rendering
- analysis endpoints
- security expectations

## Security and production notes

- The project uses session-based authentication and rate limiting.
- Uploaded originals are extracted in memory and not persisted.
- Security headers are added globally for HTML responses.
- For production, set a strong `SECRET_KEY` and prefer a managed database such as MySQL.
- For external AI providers, configure the relevant API keys and provider settings in `.env`.

## License

This repository does not currently declare a license file. If you plan to distribute or publish it, add a suitable open-source license before release.

## Contributing

Contributions are welcome. A typical workflow is:

1. Create a feature branch
2. Add or update tests for the change
3. Run the relevant tests
4. Submit a pull request with a clear summary

## Useful commands

```bash
# Run the app
python run.py

# Run all tests
pytest

# Create database tables
flask --app run init-db

# Create an admin user
flask --app run create-admin
```

## Summary

NLP Smart Analyzer is a full-stack NLP application for document analysis and insight extraction. It combines a Flask backend, server-side NLP processing, and a browser-based interface to provide a practical text-analysis dashboard for users working with documents or writing samples.
