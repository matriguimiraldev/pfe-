import os
import tempfile
from fastapi import UploadFile
from faster_whisper import WhisperModel

from app.voice.transcript_postprocess import normalize_transcript_for_routes


# Chargement du modèle une seule fois au démarrage
# Pour V1 : small + CPU + int8 = bon compromis
model = WhisperModel(
    "small",
    device="cpu",
    compute_type="int8"
)


async def transcribe_audio_local(file: UploadFile) -> str:
    """
    Reçoit un fichier audio UploadFile depuis FastAPI,
    le sauvegarde temporairement,
    puis utilise faster-whisper pour le transcrire en français.
    """

    suffix = ".webm"

    if file.filename and "." in file.filename:
        suffix = "." + file.filename.split(".")[-1]

    audio_bytes = await file.read()

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_audio:
        temp_audio.write(audio_bytes)
        temp_audio_path = temp_audio.name

    try:
        segments, info = model.transcribe(
            temp_audio_path,
            language="fr",
            beam_size=5,
            vad_filter=True
        )

        transcript_parts = []

        for segment in segments:
            transcript_parts.append(segment.text.strip())

        transcript = " ".join(transcript_parts).strip()
        transcript = normalize_transcript_for_routes(transcript)

        return transcript

    finally:
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
