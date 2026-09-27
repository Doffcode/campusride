"""Turn what a student said into {pickup, drop}. Sarvam LLM first, offline alias rules as fallback."""

import json
import re
from pathlib import Path

from mvp import sarvam

CAMPUS = json.loads((Path(__file__).parent / "campus.json").read_text(encoding="utf-8"))
PLACES = {n["id"]: n for n in CAMPUS["nodes"]}
# Sent to Saaras v4 so place names are transcribed correctly.
KEYTERMS = list(dict.fromkeys([n["name"] for n in CAMPUS["nodes"]] + ["LHC", "SAC", "NIT Trichy"]))  # Saaras rejects duplicates

# Words right after a place that mark it as the pickup ("X se", Tamil "X-லிருந்து").
_PICKUP_AFTER = ("se ", "से", "லிருந்து", "இருந்து")
_PICKUP_BEFORE = ("from ", "from the ")


def _aliases(node: dict) -> list[str]:
    return sorted({a.lower() for a in node["aliases"]} | {node["name"].lower()}, key=len, reverse=True)


def build_messages(text: str, lang: str) -> list[dict]:
    places = "\n".join(f"- {n['id']}: {n['name']} (also called: {', '.join(n['aliases'])})" for n in CAMPUS["nodes"])
    system = (
        "You extract campus EV ride bookings at NIT Trichy from what a student said.\n"
        "The request may be in English, Hindi, Tamil, Telugu, or a mix (e.g. Hinglish).\n"
        f"Valid places (use ONLY these ids):\n{places}\n\n"
        "Rules:\n"
        "- pickup = where the student is now. drop = where they want to go.\n"
        '- Hindi "X se Y" / "X से Y" means pickup X, drop Y. Tamil "X-லிருந்து Y" means pickup X, drop Y. English "from X to Y".\n'
        "- If only one place is mentioned, it is the drop and pickup is null.\n"
        "- If unsure or the place is not in the list, use null. Never invent ids.\n"
        "- confidence: 0.0 to 1.0 for BOTH fields together.\n"
        'Reply with ONLY a JSON object: {"pickup": "<id or null>", "drop": "<id or null>", "confidence": <number>}'
    )
    return [{"role": "system", "content": system},
            {"role": "user", "content": f"Language: {lang}\nStudent said: {text}"}]


def parse_llm_json(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("not an object")
    return data


def _matches(t: str) -> list[tuple[int, int, str]]:
    found = []
    for pid, node in PLACES.items():
        for a in _aliases(node):
            i = t.find(a)
            while i != -1:
                end = i + len(a)
                # ASCII aliases must be whole words ("gate" must not match inside "agate").
                ok = not a.isascii() or (
                    (i == 0 or not t[i - 1].isalnum()) and (end == len(t) or not t[end].isalnum()))
                if ok:
                    found.append((i, end, pid))
                i = t.find(a, i + 1)
    found.sort(key=lambda m: (m[0], -(m[1] - m[0])))
    kept, last_end = [], -1
    for m in found:
        if m[0] >= last_end:
            kept.append(m)
            last_end = m[1]
    return kept


def rule_based(text: str) -> tuple[str | None, str | None]:
    t = " ".join(text.lower().split())
    kept = _matches(t)
    order = []
    for _, _, pid in kept:
        if not order or order[-1] != pid:
            order.append(pid)
    if not order:
        return None, None
    if len(set(order)) == 1:
        return None, order[0]
    for start, end, pid in kept:
        after = t[end:end + 12]
        if (after.lstrip(" -").startswith(_PICKUP_AFTER) or after.lstrip(" -") == "se"
                or "லிருந்து" in after or "இருந்து" in after
                or t[:start].endswith(_PICKUP_BEFORE)):
            drop = next(p for p in order if p != pid)
            return pid, drop
    return order[0], order[-1]


def understand(text: str, lang: str) -> dict:
    """-> {pickup, drop, confidence, source: 'sarvam-llm' | 'rules', llm_error}"""
    source, llm_error = "sarvam-llm", None
    try:
        data = parse_llm_json(sarvam.chat(build_messages(text, lang)))
        pickup, drop = data.get("pickup"), data.get("drop")
        confidence = float(data.get("confidence", 0.0))
    except (sarvam.SarvamError, ValueError, TypeError) as e:
        source, llm_error = "rules", str(e)
        pickup, drop = rule_based(text)
        confidence = 0.7 if pickup and drop else 0.3
    pickup = pickup if pickup in PLACES else None
    drop = drop if drop in PLACES else None
    if pickup is not None and pickup == drop:
        drop = None
    # The LLM said it's unsure: trust the rules if they found both places.
    if source == "sarvam-llm" and confidence < 0.6:
        rp, rd = rule_based(text)
        if rp and rd:
            pickup, drop, confidence = rp, rd, 0.7
    return {"pickup": pickup, "drop": drop, "confidence": round(max(0.0, min(confidence, 1.0)), 2),
            "source": source, "llm_error": llm_error}
