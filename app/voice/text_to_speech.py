import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


VOICE_DIR = Path("voices")
DEFAULT_VOICE_MODEL = VOICE_DIR / "fr_FR-siwis-medium.onnx"
DEFAULT_SPEAKER_ID = 1
DEFAULT_NOISE_SCALE = 0.28
DEFAULT_NOISE_W = 0.50
DEFAULT_LENGTH_SCALE = 1


def _resolve_piper_executable() -> str:
    """
    Resolve Piper executable from env var or PATH.
    """
    env_piper = os.getenv("PIPER_EXE", "").strip()
    if env_piper:
        piper_path = Path(env_piper)
        if piper_path.exists():
            return str(piper_path)
        raise FileNotFoundError(
            f"PIPER_EXE pointe vers un chemin introuvable: {env_piper}"
        )

    path_piper = shutil.which("piper")
    if path_piper:
        return path_piper

    raise FileNotFoundError(
        "La commande 'piper' est introuvable. Installez le binaire Piper et ajoutez-le au PATH, "
        "ou definissez PIPER_EXE avec le chemin complet vers piper.exe."
    )


def _resolve_voice_model_path() -> Path:
    """Return a usable French Piper model path from voices/."""
    if DEFAULT_VOICE_MODEL.exists():
        return DEFAULT_VOICE_MODEL

    fr_models = sorted(VOICE_DIR.glob("fr_FR*.onnx"))
    if fr_models:
        return fr_models[0]

    raise FileNotFoundError(
        "Aucun modele vocal trouve dans voices/. "
        "Ajoutez un fichier .onnx (ex: fr_FR-siwis-medium.onnx) et son .onnx.json."
    )


def _postprocess_with_ffmpeg(input_path: str) -> str:
    """
    Improve loudness and clarity with FFmpeg if available.
    """
    ffmpeg_executable = shutil.which("ffmpeg")
    if ffmpeg_executable is None:
        return input_path

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
        output_path = temp_audio.name

    command = [
        ffmpeg_executable,
        "-y",
        "-i",
        input_path,
        "-af",
        (
            "highpass=f=70,"
            "lowpass=f=9500,"
            "equalizer=f=180:t=q:w=1.0:g=1.2,"
            "equalizer=f=3200:t=q:w=1.0:g=2.0,"
            "acompressor=threshold=-18dB:ratio=2.2:attack=12:release=180:makeup=3,"
            "loudnorm=I=-16:TP=-1.5:LRA=9"
        ),
        "-ar",
        "24000",
        "-ac",
        "1",
        output_path,
    ]

    process = subprocess.run(command, capture_output=True, text=True)
    if process.returncode != 0:
        return input_path

    return output_path


def _prepare_text_for_tts(text: str) -> str:
    """
    Light normalization to improve articulation and pauses in TTS.
    """
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return cleaned

    # Add a final punctuation mark so Piper does not cut the ending abruptly.
    if cleaned[-1] not in ".!?":
        cleaned += "."

    # Add gentle pauses after commas/semicolons/colons when missing space.
    cleaned = re.sub(r"([,;:])([^\s])", r"\1 \2", cleaned)
    return cleaned


def synthesize_speech_local(text: str) -> str:
    """
    Convert text to WAV audio with local Piper.
    Returns the generated audio file path.
    """
    if not text or not text.strip():
        raise ValueError("Le texte est vide.")

    normalized_text = _prepare_text_for_tts(text)

    model_path = _resolve_voice_model_path()
    model_config_path = Path(str(model_path) + ".json")
    if not model_config_path.exists():
        raise FileNotFoundError(
            f"Fichier de configuration manquant: {model_config_path.name}"
        )

    piper_executable = _resolve_piper_executable()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
        output_path = temp_audio.name

    command = [
        piper_executable,
        "--model",
        str(model_path),
        "--speaker",
        str(DEFAULT_SPEAKER_ID),
        "--noise_scale",
        str(DEFAULT_NOISE_SCALE),
        "--noise_w",
        str(DEFAULT_NOISE_W),
        "--length_scale",
        str(DEFAULT_LENGTH_SCALE),
        "--output_file",
        output_path,
    ]

    process = subprocess.run(
        command,
        input=normalized_text,
        text=True,
        capture_output=True,
    )

    if process.returncode != 0:
        raise RuntimeError(f"Erreur Piper : {process.stderr}")

    return _postprocess_with_ffmpeg(output_path)
