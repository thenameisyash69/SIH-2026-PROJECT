"""
Chatbot backend. Two modes:
  1. No ANTHROPIC_API_KEY set -> lightweight keyword-parsing over the DB
     (still fully functional for a demo, zero external dependency).
  2. ANTHROPIC_API_KEY set -> Claude phrases a natural-language answer
     from the same retrieved rows (retrieval-then-generate = RAG).
"""
from sqlalchemy.orm import Session
from app import models
from app.config import settings

INDIAN_STATES = [
    "gujarat", "maharashtra", "odisha", "jharkhand", "chhattisgarh", "west bengal",
    "punjab", "haryana", "uttar pradesh", "rajasthan", "tamil nadu", "karnataka",
    "andhra pradesh", "telangana", "bihar", "assam", "kerala", "madhya pradesh",
]

CATEGORY_KEYWORDS = {
    "alert": "industrial_alert",
    "industrial": "industrial_normal",
    "wildfire": "wildfire",
    "forest": "wildfire",
    "agricultural": "agricultural_burning",
    "farm": "agricultural_burning",
    "unknown": "unknown",
    "unclassified": "unknown",
}

RISK_KEYWORDS = {
    "critical": "CRITICAL",
    "high-risk": "HIGH",
    "high risk": "HIGH",
    "watch": "WATCH",
}


def _extract_filters(question: str) -> dict:
    q = question.lower()
    filters = {}
    for state in INDIAN_STATES:
        if state in q:
            filters["state"] = state.title()
            break
    for kw, category in CATEGORY_KEYWORDS.items():
        if kw in q:
            filters["category"] = category
            break
    for kw, level in RISK_KEYWORDS.items():
        if kw in q:
            filters["risk_level"] = level
            break
    return filters


def answer_query(question: str, db: Session) -> dict:
    filters = _extract_filters(question)

    query = db.query(models.Hotspot)
    if "state" in filters:
        query = query.filter(models.Hotspot.state == filters["state"])
    if "category" in filters:
        query = query.filter(models.Hotspot.category == filters["category"])
    if "risk_level" in filters:
        query = query.filter(models.Hotspot.risk_level == filters["risk_level"])

    results = query.order_by(models.Hotspot.acq_date.desc()).limit(20).all()

    summary = _build_summary(results, filters)

    if settings.anthropic_api_key:
        summary = _phrase_with_claude(question, summary)

    return {"answer": summary, "matched_count": len(results)}


def _build_summary(results, filters) -> str:
    if not results:
        scope = " ".join(f"{k}={v}" for k, v in filters.items()) or "your query"
        return f"No hotspots found matching {scope}."

    lines = [f"Found {len(results)} matching hotspot(s):"]
    for h in results[:5]:
        loc = h.facility.name if h.facility else f"({h.lat:.2f}, {h.lon:.2f})"
        flag = " ⚠ ANOMALY" if h.is_anomaly else ""
        source_tag = "[REAL]" if h.source == "nasa_firms" else "[DEMO]"
        lines.append(f"- {source_tag} {loc} — {h.category}, risk {h.risk_level} ({h.risk_score}){flag}")
    if len(results) > 5:
        lines.append(f"...and {len(results) - 5} more.")
    return "\n".join(lines)


def _phrase_with_claude(question: str, raw_summary: str) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": f"A user asked: \"{question}\"\n\nHere is the raw data retrieved from our "
                            f"thermal-monitoring database:\n{raw_summary}\n\n"
                            f"Rewrite this as a short, clear, natural-language answer for a control-room "
                            f"operator. Do not invent any data not present above."
            }],
        )
        return "".join(block.text for block in msg.content if block.type == "text")
    except Exception as e:
        print(f"[rag_engine] Claude call failed, falling back to raw summary: {e}")
        return raw_summary
