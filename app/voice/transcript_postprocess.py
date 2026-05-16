import re

from app.tools.driver_tools import find_route_by_query


def normalize_transcript_for_routes(transcript: str) -> str:
    """Replace fuzzy route mentions with canonical route names from the CSV catalog."""
    if not transcript or not transcript.strip():
        return transcript

    text = transcript.strip()
    patterns = [
        r"\b(?:route|ceinture|avenue)\s+(?:de|du|des|d')?\s*[\w\u00C0-\u024F\u0600-\u06FF\- ]+",
        r"\b(?:bab|medina)\s+[\w\u00C0-\u024F\u0600-\u06FF\- ]+",
    ]

    def _replace(match: re.Match[str]) -> str:
        candidate = match.group(0).strip(" .,!?:;\n\t")
        if not candidate:
            return match.group(0)
        route = find_route_by_query(candidate)
        route_name = (route or {}).get("name")
        return route_name or match.group(0)

    for pattern in patterns:
        text = re.sub(pattern, _replace, text, flags=re.IGNORECASE)

    return text
