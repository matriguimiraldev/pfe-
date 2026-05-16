from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DriverPosition(BaseModel):
    id: int
    name: str
    status: str
    lat: float
    lng: float
    zone: str


class AssistantRequest(BaseModel):
    question: str
    latest_drivers: List[DriverPosition]


class AssistantResponse(BaseModel):
    answer: str
    intent: str
    action_type: Optional[str] = None
    map_payload: Optional[Dict[str, Any]] = None


class TextToSpeechRequest(BaseModel):
    text: str


class VoiceAskResponse(BaseModel):
    transcript: str
    answer: str
    audio_base64: str
    audio_mime_type: str = "audio/wav"


class TextAskRequest(BaseModel):
    text: str


class AgentAskResponse(BaseModel):
    question: str
    intent: Optional[str] = None
    tool_name: Optional[str] = None
    tool_params: Dict[str, Any] = Field(default_factory=dict)
    answer: Optional[str] = None
    tool_result: Optional[Any] = None
