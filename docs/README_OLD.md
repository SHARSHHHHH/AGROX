# Sustainable Agriculture AI Advisory Platform — Gemini Edition

An AI-driven precision agriculture platform combining farm profiles, soil analysis, weather, IoT sensor simulation, irrigation recommendations, pest/disease image analysis, government schemes and a multilingual AI advisor.

## AI architecture

This rewritten version uses **Google Gemini as the single cloud AI provider**:

- **Gemini 3.7 Flash** — conversational AI, agent reasoning, NLP/translation
- **Gemini 3.7 Flash Vision** — plant disease and pest image analysis
- **Whisper/browser speech** — voice input remains independent of the LLM
- Knowledge bases and deterministic services continue to ground agricultural recommendations
- **Ollama has been removed from the runtime path**

Gemini 3.7 Flash is a current generally available model and supports text and image inputs. See Google's current model documentation for model availability and limits. urlGemini model documentationhttps://ai.google.dev/gemini-api/docs/models

## Requirements

- Python 3.9+
- Node.js 18+
- A Google AI Studio Gemini API key
- Internet access for Gemini and weather requests

Create a Gemini API key from urlGoogle AI Studio API keyshttps://aistudio.google.com/apikey.

## Run the project

### Backend

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `backend/.env`:

```env
GEMINI_API_KEY="YOUR_REAL_GEMINI_API_KEY"
GEMINI_MODEL="gemini-3.7-flash"
VISION_MODEL="gemini-3.7-flash"
```

Start the API:

```powershell
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/docs.

### Frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL, normally http://localhost:5173.

## Demo accounts

- Farmer: `farmer@demo.com` / `demo123`
- Balcony grower: `balcony@demo.com` / `demo123`
- Government officer: `admin@agri.gov` / `admin123`

## Important security note

Never put your Gemini API key inside the React frontend. The frontend calls the FastAPI backend, and only the backend communicates with Gemini. Keep the real key in `backend/.env` and do not commit that file.

## Gemini request flow

```text
React frontend
      |
      v
FastAPI backend
      |
      +---- Agent / NLP ----> Gemini 3.7 Flash
      |
      +---- Plant/Pest image -> Gemini 3.7 Flash Vision
      |
      +---- Soil / Weather / IoT / Knowledge Base
```

The agricultural knowledge base remains responsible for disease/pest facts and recommendations; Gemini is used to interpret the user's request, reason over supplied context and analyze uploaded images.
