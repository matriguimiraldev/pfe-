import os
import tempfile

from fastapi import UploadFile
from mistralai.client import Mistral
from mistralai.client.models.file import File

from app.voice.transcript_postprocess import (
    normalize_transcript_for_routes
)

# Client Mistral
client = Mistral(
    api_key=os.getenv("MISTRAL_API_KEY")
)

# Modèle officiel
MODEL_NAME = "voxtral-mini-latest"
async def transcribe_audio_local(
    file: UploadFile
) -> str:

    suffix = ".webm"

    if file.filename and "." in file.filename:
        suffix = "." + file.filename.split(".")[-1]

    audio_bytes = await file.read()

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix
    ) as temp_audio:

        temp_audio.write(audio_bytes)
        temp_audio_path = temp_audio.name

    try:

        with open(temp_audio_path, "rb") as audio_file:

            audio_bytes = audio_file.read()

            # Determine content type from suffix
            content_type = "audio/webm"
            if temp_audio_path.endswith(".mp3"):
                content_type = "audio/mpeg"
            elif temp_audio_path.endswith(".wav"):
                content_type = "audio/wav"
            elif temp_audio_path.endswith(".m4a"):
                content_type = "audio/mp4"

            file_obj = File(
                fileName=(file.filename or os.path.basename(temp_audio_path)),
                content=audio_bytes,
                content_type=content_type,
            )

            transcription_response = client.audio.transcriptions.complete(
                model=MODEL_NAME,
                file=file_obj,
                language="fr",
            )

        transcript = (
            transcription_response.text.strip()
        )

        transcript = normalize_transcript_for_routes(
            transcript
        )

        return transcript

    finally:

        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)