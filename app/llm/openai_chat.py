import os
from typing import Any, Optional

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.agent import run_dispatch_agent

load_dotenv()


DEFAULT_MODEL = "gpt-4o-mini"
SYSTEM_PROMPT = """
Tu es ZigZag Delivery Specialist.

Mission:
- analyser les flux de livraison
- suivre les chauffeurs, les zones, les retards et les ETA
- produire des réponses courtes, exactes et orientées action

Contraintes:
- ne traite que la logistique livraison/dispatch
- si l'information manque, demande une précision
- si la question est hors sujet, refuse poliment
- réponds en français, en une seule phrase concise
"""


def is_role_or_greeting_question(question: str) -> bool:
    """Detects user greetings and role-definition questions."""
    text = question.lower().strip()
    live_keywords = [
        "zone",
        "livreur",
        "driver",
        "position",
        "positions",
        "charge",
        "flux",
        "retard",
        "eta",
        "commande",
        "commandes",
        "route",
    ]
    if any(keyword in text for keyword in live_keywords):
        return False

    triggers = [
        "bonjour",
        "bonsoir",
        "salut",
        "qui es tu",
        "qui es-tu",
        "quel est ton role",
        "quel est votre role",
        "definis ton role",
        "definir ton role",
        "presente toi",
        "presente-toi",
    ]
    return any(trigger in text for trigger in triggers)


def is_simple_chat_question(question: str) -> bool:
    """Detects short polite or conversational messages that should get a simple reply."""
    text = (question or "").lower().strip()
    simple_triggers = [
        "merci",
        "merci beaucoup",
        "thanks",
        "salut",
        "bonjour",
        "bonsoir",
        "ça va",
        "ca va",
        "ok",
        "d'accord",
        "parfait",
        "super",
        "oui",
        "non",
    ]
    return any(trigger in text for trigger in simple_triggers)


def is_out_of_scope(question: str) -> bool:
    """Retourne True si la question semble hors domaine delivery/dispatch."""
    if not question or not question.strip():
        return True

    text = question.lower()
    allowed_keywords = [
        "livraison",
        "livrer",
        "dispatch",
        "livreur",
        "livreurs",
        "chauffeur",
        "driver",
        "coursier",
        "commande",
        "colis",
        "itineraire",
        "trajet",
        "route",
        "retard",
        "eta",
        "zone",
        "ceinture",
        "avenue",
        "quartier",
        "flux",
        "tracking",
        "suivi",
        "pickup",
        "dropoff",
    ]
    return not any(keyword in text for keyword in allowed_keywords)


def _build_llm_chain(model: str, api_key: str) -> Any:
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            (
                "system",
                "Contexte outil: {tool_context}\nRéponds uniquement sur la base de ce contexte si utile.",
            ),
            ("user", "{question}"),
        ]
    )
    llm = ChatOpenAI(model=model, temperature=0.2, openai_api_key=api_key)
    return prompt | llm | StrOutputParser()


def generate_answer(question: str) -> str:
    """Generate an answer from the transcribed user question via LangChain + local agent."""
    if not question or not question.strip():
        raise ValueError("Le texte a envoyer au LLM est vide.")

    agent_result = run_dispatch_agent(question)
    if agent_result.get("answer"):
        return str(agent_result["answer"])

    if is_role_or_greeting_question(question):
        return (
            "Bonjour, je suis ZigZag Delivery Specialist. "
            "Je peux répondre simplement sur les livreurs, les zones et les commandes."
        )

    if is_simple_chat_question(question):
        return (
            "Avec plaisir. "
            "Pose-moi une question simple sur les livreurs, les zones ou les commandes."
        )

    if is_out_of_scope(question):
        return (
            "Je suis ZigZag Delivery Specialist. "
            "Je traite uniquement les flux de livraison en temps reel. "
            "Si vous voulez, je peux vous aider sur le suivi chauffeurs, retards, ETA ou priorisation."
        )

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY est manquante.")

    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    try:
        tool_context = (
            f"intent={agent_result.get('intent')} | "
            f"tool={agent_result.get('tool_name')} | "
            f"params={agent_result.get('tool_params')} | "
            f"result={agent_result.get('tool_result')}"
        )
        chain = _build_llm_chain(model=model, api_key=api_key)
        answer = chain.invoke({"question": question.strip(), "tool_context": tool_context})
    except Exception as exc:
        raise RuntimeError(f"Erreur LangChain/OpenAI: {exc}") from exc

    answer = (answer or "").strip()
    if not answer:
        raise RuntimeError("Le LLM a retourne une reponse vide.")

    return answer
