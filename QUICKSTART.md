# Quick Start — Gemini Version

## 1. Backend

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Open `backend/.env` and replace `PASTE_YOUR_GEMINI_API_KEY_HERE` with your Google AI Studio API key.

Start FastAPI:

```powershell
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

## 2. Frontend

Open a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the URL printed by Vite, normally http://localhost:5173.

## 3. AI setup

This version uses **Google Gemini for all LLM and plant-image AI features**. Ollama is not required.

Default model: `gemini-3.7-flash`.

Keep the API key only in `backend/.env`; never commit it to GitHub.
