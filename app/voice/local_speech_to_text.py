import os
import tempfile

from fastapi import UploadFile
from mistralai.client import Mistral
from mistralai.client.models.file import File

from app.voice.transcript_postprocess import normalize_transcript_for_routes


# API KEY
client = Mistral(
    api_key=os.getenv("MISTRAL_API_KEY")
)


async def transcribe_audio_local(file: UploadFile) -> str:
    """
    Transcription audio avec Mistral STT (Voxtral).
    """

    suffix = ".webm"

    if file.filename and "." in file.filename:
        suffix = "." + file.filename.split(".")[-1]

    audio_bytes = await file.read()

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_audio:
        temp_audio.write(audio_bytes)
        temp_audio_path = temp_audio.name

    try:

        with open(temp_audio_path, "rb") as audio_file:
            audio_bytes = audio_file.read()

            # Determine content type from filename
            content_type = "audio/webm"
            if temp_audio_path.endswith(".mp3"):
                content_type = "audio/mpeg"
            elif temp_audio_path.endswith(".wav"):
                content_type = "audio/wav"
            elif temp_audio_path.endswith(".m4a"):
                content_type = "audio/mp4"

            transcription = client.audio.transcriptions.complete(
                model="voxtral-mini-transcribe-v2",
                file=File(
                    fileName=os.path.basename(temp_audio_path),
                    content=audio_bytes,
                    content_type=content_type
                )
            )

        transcript = transcription.text.strip()

        transcript = normalize_transcript_for_routes(
            transcript
        )

        return transcript

    finally:

        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)