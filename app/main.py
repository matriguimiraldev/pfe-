import base64
import os
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from app.agent import run_dispatch_agent
from app.llm.openai_chat import generate_answer
from app.schemas import AgentAskResponse, TextAskRequest, TextToSpeechRequest, VoiceAskResponse
from app.tools.live_tools import (
    get_current_orders_in_zone,
    get_driver_by_id,
    get_driver_positions,
    get_drivers_by_status_in_zone,
    get_zone_live_load,
    live_tools_service,
)
from app.voice.local_speech_to_text import transcribe_audio_local
from app.voice.text_to_speech import synthesize_speech_local

app = FastAPI(
    title="Dispatch Voice Agent Local",
    description="Assistant vocal auto-dispatch avec Whisper local",
    version="0.1.0"
)

DEMO_INDEX_PATH = Path(__file__).resolve().parent / "demo" / "index.html"


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "dispatch-voice-agent",
        "speech_to_text": "faster-whisper-local"
    }


@app.on_event("startup")
def startup_event():
    live_tools_service.start()


@app.on_event("shutdown")
def shutdown_event():
    live_tools_service.stop()


@app.get("/demo")
def demo_page():
    if not DEMO_INDEX_PATH.exists():
        raise HTTPException(status_code=404, detail="Demo interface not found.")
    return FileResponse(DEMO_INDEX_PATH)




@app.get("/live/drivers")
def live_drivers(zone_id: int | None = None):
    return {"items": get_driver_positions(zone_id=zone_id)}


@app.get("/live/drivers/{dm_id}")
def live_driver_by_id(dm_id: int):
    item = get_driver_by_id(dm_id=dm_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Driver not found in live cache.")
    return item


@app.get("/live/zone-load")
def live_zone_load(zone_id: int | None = None):
    return get_zone_live_load(zone_id=zone_id)


@app.get("/live/drivers-by-status")
def live_drivers_by_status(zone_id: int | None = 1):
    return get_drivers_by_status_in_zone(zone_id=zone_id)


@app.get("/live/current-orders")
def live_current_orders(zone_id: int | None = 1):
    return get_current_orders_in_zone(zone_id=zone_id)


@app.post("/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(...)):
    transcript = await transcribe_audio_local(file)

    return {
        "transcript": transcript
    }


@app.post(
    "/voice/speak",
    responses={
        200: {
            "description": "WAV audio response",
            "content": {"audio/wav": {}},
        }
    },
)
def voice_speak(payload: TextToSpeechRequest):
    try:
        audio_path = synthesize_speech_local(text=payload.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return FileResponse(
        audio_path,
        media_type="audio/wav",
        filename="assistant-response.wav"
    )


@app.post("/llm/ask")
def llm_ask(payload: TextAskRequest):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Le texte est vide.")
    try:
        answer = generate_answer(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"question": text, "answer": answer}


@app.post("/agent/ask", response_model=AgentAskResponse)
def agent_ask(payload: TextAskRequest):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Le texte est vide.")

    result = run_dispatch_agent(text)
    return AgentAskResponse(
        question=text,
        intent=result.get("intent"),
        tool_name=result.get("tool_name"),
        tool_params=result.get("tool_params") or {},
        answer=result.get("answer"),
        tool_result=result.get("tool_result"),
    )


@app.post("/voice/ask", response_model=VoiceAskResponse)
async def voice_ask(file: UploadFile = File(...)):
    try:
        transcript = await transcribe_audio_local(file)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Audio invalide: {exc}") from exc

    if not transcript or not transcript.strip():
        raise HTTPException(
            status_code=400,
            detail="La transcription est vide. Verifiez la qualite de l'audio."
        )

    try:
        answer = generate_answer(transcript)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        audio_path = synthesize_speech_local(text=answer)
        with open(audio_path, "rb") as audio_file:
            audio_base64 = base64.b64encode(audio_file.read()).decode("utf-8")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if "audio_path" in locals() and os.path.exists(audio_path):
            os.remove(audio_path)

    return VoiceAskResponse(
        transcript=transcript,
        answer=answer,
        audio_base64=audio_base64,
        audio_mime_type="audio/wav",
    )
