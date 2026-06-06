# Dispatch Voice Agent

Assistant vocal de dispatch pour livraison, avec architecture claire en 3 couches:
- STT local avec `faster-whisper`
- orchestrateur métier déterministe dans `app/agent.py`
- génération de fallback avec LangChain + OpenAI dans `app/llm/openai_chat.py`

## Architecture

- `app/main.py`: API FastAPI et points d'entrée
- `app/agent.py`: orchestration centrale des intents et des tools
- `app/intent_detector.py`: détection d'intention métier
- `app/tools/driver_tools.py`: matching de routes et lecture du cache live
- `app/tools/live_tools.py`: état live des livreurs
- `app/tools/map_tools.py`: payloads orientés carte
- `app/voice/local_speech_to_text.py`: transcription locale
- `app/voice/transcript_postprocess.py`: normalisation de routes après STT
- `app/voice/text_to_speech.py`: synthèse vocale locale
- `app/llm/openai_chat.py`: fallback LangChain pour les réponses non couvertes par les tools

## Installation Windows

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Installer FFmpeg si besoin:

```powershell
winget install Gyan.FFmpeg
```

## Lancer le service

```powershell
uvicorn app.main:app --reload
```

Swagger: <http://127.0.0.1:8000/docs>

## Variables d'environnement

- `OPENAI_API_KEY`: requis pour le fallback LangChain
- `OPENAI_MODEL`: optionnel, défaut `gpt-4o-mini`
- `REAL_TIME_ZIGZAG`: flux live des livreurs
- `REAL_TIME_ZIGZAG_CONNECT_TIMEOUT`
- `REAL_TIME_ZIGZAG_READ_TIMEOUT`
- `REAL_TIME_ZIGZAG_RECONNECT_DELAY`
- `ORS_DIRECTIONS_URL`: endpoint ORS driving-car
- `SFAX_CENTER_LNG`, `SFAX_CENTER_LAT`: centre kilométrique, Beb Jebli
- `ROUTE_KM_TOLERANCE_KM`: marge autour du kilomètre demandé, défaut `1`
- `ROUTE_KM_RADIUS_M`: distance maximale du livreur à la route, défaut `1000`
- `PIPER_EXE`: chemin explicite vers `piper.exe` si absent du PATH

## Tests à exécuter

1. Santé API

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

2. Agent métier explicite

```powershell
$body = @{ text = 'Donne moi la liste des livreurs et leurs routes' } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/agent/ask -Method Post -ContentType 'application/json' -Body $body
```

3. Route spécifique

```powershell
$body = @{ text = 'Donne-moi la liste des livreurs qui sont sur la route de Tunis.' } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/llm/ask -Method Post -ContentType 'application/json' -Body $body
```

4. Transcription seule

```powershell
curl.exe -X POST "http://127.0.0.1:8000/voice/transcribe" -F "file=@sample.wav"
```

5. Pipeline vocal complet

```powershell
curl.exe -X POST "http://127.0.0.1:8000/voice/ask" -F "file=@sample.wav"
```

6. Live tools

```powershell
Invoke-RestMethod http://127.0.0.1:8000/live/drivers?zone_id=1
Invoke-RestMethod http://127.0.0.1:8000/live/zone-load?zone_id=1
```

## Notes

- Le projet utilise désormais `.venv` à la racine.
- Le route matching est normalisé avant l'appel aux tools pour mieux absorber les erreurs STT.
