import os
import json
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Tuple

import streamlit as st
from openai import OpenAI


def _safe_secret(key: str) -> str:
    """Safely read Streamlit secret without crashing when secrets file is missing."""
    try:
        value = st.secrets.get(key)
    except Exception:
        value = None
    return value or os.getenv(key) or ""


def parse_user_preferences(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert raw form input into a structured preferences dictionary."""
    def _split_csv(value: str) -> List[str]:
        if not value:
            return []
        return [item.strip().lower() for item in value.split(",") if item.strip()]

    city = " ".join((input_data.get("city") or "").strip().split())
    budget = input_data.get("budget")
    available_time = (input_data.get("available_time") or "").strip()
    start_time = (input_data.get("start_time") or "").strip()
    end_time = (input_data.get("end_time") or "").strip()
    if not available_time and start_time and end_time:
        available_time = f"{start_time} - {end_time}"
    mood = (input_data.get("mood") or "").strip().lower()
    interests = _split_csv(input_data.get("interests", ""))
    constraints = _split_csv(input_data.get("constraints", ""))
    mood_detail = (input_data.get("mood_detail") or "").strip()

    return {
        "city": city,
        "budget": float(budget) if budget is not None else 0.0,
        "available_time": available_time,
        "start_time": start_time,
        "end_time": end_time,
        "mood": mood,
        "mood_detail": mood_detail,
        "interests": interests,
        "constraints": constraints,
    }


def _trace_summary(step: str, data: Any, prefs: Dict[str, Any]) -> str:
    """Convert trace data into human-readable summaries."""
    if step == "Parsed Preferences":
        return (
            f"City: {prefs.get('city', 'N/A')}\n"
            f"Budget: {int(prefs.get('budget', 0))}\n"
            f"Time: {prefs.get('available_time', 'N/A')}\n"
            f"Mood: {prefs.get('mood', 'N/A')}\n"
            f"Interests: {', '.join(prefs.get('interests', [])) or 'none'}\n"
            f"Constraints: {', '.join(prefs.get('constraints', [])) or 'none'}"
        )

    if step == "Real Places (Overpass)":
        note = data.get("note", "") if isinstance(data, dict) else ""
        places = data.get("places", []) if isinstance(data, dict) else []
        lines = [f"{note}"]
        if places:
            lines.append("Top matches:")
            for place in places[:4]:
                lines.append(f"- {place.get('name', 'Unknown')} | cost ~{place.get('cost', 0)} | crowd: {place.get('crowd_level', 'medium')}")
        return "\n".join(lines)

    if step in {"Activities Found", "Food Options", "Validated Plan", "Combined Plan"} and isinstance(data, list):
        if not data:
            return "No items found."
        lines = [f"{len(data)} options selected:"]
        for item in data[:5]:
            lines.append(f"- {item.get('name', 'Unknown')} | cost ~{item.get('cost', 0)} | crowd: {item.get('crowd_level', 'medium')}")
        return "\n".join(lines)

    if step == "Selection Reasons" and isinstance(data, list):
        return "\n".join([f"- {line}" for line in data]) if data else "No explicit matching reasons available."

    if step == "Final Output":
        return "Final plan generated successfully."

    return str(data)


def get_activity_options(city: str, interests: List[str], mood: str) -> List[Dict[str, Any]]:
    """Return mock activities based on interests + mood."""
    city_label = city if city else "your city"

    base_activities = [
        {
            "name": f"Park walk in {city_label}",
            "tags": ["outdoors", "relax", "nature"],
            "cost": 0,
            "crowd_level": "low",
        },
        {
            "name": f"Live music cafe in {city_label}",
            "tags": ["music", "social", "cozy"],
            "cost": 20,
            "crowd_level": "high",
        },
        {
            "name": f"Bookstore visit in {city_label}",
            "tags": ["books", "quiet", "indoor"],
            "cost": 10,
            "crowd_level": "low",
        },
        {
            "name": f"Local art gallery in {city_label}",
            "tags": ["art", "culture", "indoor"],
            "cost": 15,
            "crowd_level": "medium",
        },
        {
            "name": f"Bike trail loop in {city_label}",
            "tags": ["fitness", "outdoors", "adventure"],
            "cost": 5,
            "crowd_level": "medium",
        },
    ]

    mood_boost = {
        "chill": ["quiet", "relax", "cozy"],
        "relaxed": ["quiet", "relax", "nature"],
        "energetic": ["fitness", "social", "adventure"],
        "creative": ["art", "culture", "books"],
        "social": ["social", "music", "cozy"],
    }

    target_tags = set(interests)
    target_tags.update(mood_boost.get(mood, []))

    if not target_tags:
        return base_activities[:3]

    scored = []
    for activity in base_activities:
        overlap = len(set(activity["tags"]) & target_tags)
        if overlap > 0:
            scored.append((overlap, activity))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored]


def get_real_places(city: str, interests: List[str], constraints: List[str]) -> Tuple[List[Dict[str, Any]], str]:
    """Fetch real places from Overpass API, with safe failure fallback."""
    if not city.strip():
        return [], "City missing"

    def _geocode_city_bbox(city_name: str) -> Tuple[float, float, float, float, float, float, str] | None:
        url = (
            "https://nominatim.openstreetmap.org/search?format=json&addressdetails=1&limit=5&q="
            + urllib.parse.quote(city_name)
        )
        req = urllib.request.Request(url, headers={"User-Agent": "PerfectSaturdayPlanner/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
            if not data:
                return None

            city_lower = city_name.strip().lower()

            def _score(item: Dict[str, Any]) -> int:
                name = str(item.get("display_name", "")).lower()
                score = 0
                if city_lower and city_lower in name:
                    score += 4
                place_type = str(item.get("type", "")).lower()
                if place_type in {"city", "administrative", "town"}:
                    score += 2
                osm_class = str(item.get("class", "")).lower()
                if osm_class in {"boundary", "place"}:
                    score += 2
                if osm_class in {"amenity", "shop", "tourism", "leisure"}:
                    score -= 5
                if any(tok in name for tok in ["united states", "india", "uk", "canada", "australia"]):
                    score += 1
                return score

            data_sorted = sorted(data, key=_score, reverse=True)
            best = data_sorted[0]

            bbox = best.get("boundingbox", [])
            if len(bbox) != 4:
                return None
            south = float(bbox[0])
            north = float(bbox[1])
            west = float(bbox[2])
            east = float(bbox[3])
            lat = float(best.get("lat"))
            lon = float(best.get("lon"))
            display_name = str(best.get("display_name", city_name))
            return south, west, north, east, lat, lon, display_name
        except Exception:
            return None

    def _clean_place_label(raw_name: str) -> str:
        parts = [part.strip() for part in raw_name.split(",") if part.strip()]
        if len(parts) >= 2:
            return f"{parts[0]}, {parts[-1]}"
        return raw_name

    bbox = _geocode_city_bbox(city.strip())
    if not bbox:
        return [], "City geocoding failed"
    south, west, north, east, lat, lon, geocoded_name = bbox
    geocoded_label = _clean_place_label(geocoded_name)

    # Shrink search region to city center area to avoid Overpass timeouts on huge cities.
    lat_span = max(0.02, (north - south) * 0.35)
    lon_span = max(0.02, (east - west) * 0.35)
    center_south = lat - (lat_span / 2)
    center_north = lat + (lat_span / 2)
    center_west = lon - (lon_span / 2)
    center_east = lon + (lon_span / 2)
    bbox_text = f"({center_south},{center_west},{center_north},{center_east})"

    interest_map = {
        "walks": f'nwr["leisure"="park"]{bbox_text};',
        "nature": f'nwr["leisure"="park"]{bbox_text};',
        "music": f'nwr["amenity"~"arts_centre|theatre|bar|pub|cafe"]{bbox_text};',
        "books": f'nwr["shop"="books"]{bbox_text};',
        "art": f'nwr["tourism"~"gallery|museum"]{bbox_text};',
        "food": f'nwr["amenity"~"cafe|restaurant"]{bbox_text};',
        "cafe": f'nwr["amenity"="cafe"]{bbox_text};',
        "cafes": f'nwr["amenity"="cafe"]{bbox_text};',
        "pizza": f'nwr["cuisine"~"pizza",i]{bbox_text};',
        "restaurant": f'nwr["amenity"="restaurant"]{bbox_text};',
    }

    picked_queries = []
    for interest in interests:
        for key, snippet in interest_map.items():
            if key in interest:
                picked_queries.append(snippet)
                break

    if not picked_queries:
        picked_queries = [
            f'nwr["leisure"="park"]{bbox_text};',
            f'nwr["shop"="books"]{bbox_text};',
            f'nwr["amenity"~"cafe|restaurant"]{bbox_text};',
        ]

    query = '[out:json][timeout:15];(' + "".join(picked_queries[:3]) + ');out tags center 15;'

    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]

    payload = None
    last_error = ""
    for endpoint in endpoints:
        req = urllib.request.Request(
            endpoint,
            data=urllib.parse.urlencode({"data": query}).encode("utf-8"),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "PerfectSaturdayPlanner/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except Exception as exc:
            last_error = f"{endpoint}: {str(exc)[:90]}"

    if payload is None:
        return [], f"Overpass request failed: {last_error} | geocoded_to={geocoded_label}"

    avoid_crowds = any("avoid crowded places" in c or "low crowd" in c for c in constraints)

    places: List[Dict[str, Any]] = []
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        name = tags.get("name")
        if not name:
            continue

        kind = (
            tags.get("amenity")
            or tags.get("shop")
            or tags.get("tourism")
            or tags.get("leisure")
            or "place"
        )

        crowd_level = "medium"
        if kind in {"park", "books", "gallery", "library"}:
            crowd_level = "low"
        if kind in {"music_venue", "restaurant"}:
            crowd_level = "high"
        if avoid_crowds and crowd_level == "high":
            continue

        estimated_cost = 0
        if kind in {"restaurant", "cafe"}:
            estimated_cost = 20
        elif kind in {"music_venue", "arts_centre", "gallery"}:
            estimated_cost = 15
        elif kind in {"books"}:
            estimated_cost = 10

        places.append(
            {
                "name": f"{name} ({kind})",
                "tags": [kind, "real-data", "overpass"],
                "cost": estimated_cost,
                "crowd_level": crowd_level,
            }
        )

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for place in places:
        key = place["name"].lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(place)

    if not deduped:
        return [], f"Overpass returned zero named places | geocoded_to={geocoded_label}"

    return deduped[:8], f"Fetched {len(deduped[:8])} real places | geocoded_to={geocoded_label}"


def get_food_options(city: str, budget: float, constraints: List[str]) -> List[Dict[str, Any]]:
    """Return mock food options honoring vegetarian/budget/low-crowd constraints."""
    city_label = city if city else "your city"
    options = [
        {
            "name": f"Vegetarian cafe backup ({city_label})",
            "cost": 18,
            "vegetarian": True,
            "crowd_level": "low",
            "source": "mock",
        },
        {
            "name": f"Budget noodle cafe backup ({city_label})",
            "cost": 12,
            "vegetarian": True,
            "crowd_level": "medium",
            "source": "mock",
        },
        {
            "name": f"Grill house backup ({city_label})",
            "cost": 35,
            "vegetarian": False,
            "crowd_level": "high",
            "source": "mock",
        },
        {
            "name": f"Quiet soup cafe backup ({city_label})",
            "cost": 14,
            "vegetarian": True,
            "crowd_level": "low",
            "source": "mock",
        },
    ]

    wants_veg = any("vegetarian" in c for c in constraints)
    avoid_crowds = any("avoid crowded places" in c or "low crowd" in c for c in constraints)

    filtered = []
    for opt in options:
        if wants_veg and not opt["vegetarian"]:
            continue
        if avoid_crowds and opt["crowd_level"] == "high":
            continue
        if budget > 0 and opt["cost"] > max(10, budget * 0.5):
            continue
        filtered.append(opt)

    return filtered


def validate_plan(plan: List[Dict[str, Any]], constraints: List[str], budget: float) -> List[Dict[str, Any]]:
    """Remove invalid items, with fallback if plan becomes empty."""
    avoid_crowds = any("avoid crowded places" in c or "low crowd" in c for c in constraints)

    validated = []
    seen_names = set()
    for item in plan:
        name_key = str(item.get("name", "")).strip().lower()
        if name_key and name_key in seen_names:
            continue
        if avoid_crowds and item.get("crowd_level") == "high":
            continue
        if budget > 0 and item.get("cost", 0) > budget:
            continue
        validated.append(item)
        if name_key:
            seen_names.add(name_key)

    if not validated:
        return [
            {
                "name": "Relax at a quiet cafe with a book",
                "cost": min(12, budget if budget > 0 else 12),
                "crowd_level": "low",
                "tags": ["quiet", "relax", "books"],
            }
        ]

    return validated


def generate_final_plan(context: Dict[str, Any]) -> str:
    """Use OpenAI to generate final timeline and reasoning."""
    def _local_plan_fallback(ctx: Dict[str, Any]) -> str:
        prefs = ctx.get("preferences", {})
        items = ctx.get("candidate_plan", [])
        mood = prefs.get("mood") or "balanced"
        city = prefs.get("city") or "your city"
        time_window = prefs.get("available_time") or "your available window"
        interests = prefs.get("interests") or []
        constraints = prefs.get("constraints") or []

        picked = items[:4] if items else [{"name": "Relax at a quiet cafe with a book", "cost": 12}]
        time_slots = ["10:00 AM", "11:30 AM", "1:00 PM", "2:30 PM", "4:00 PM"]

        timeline_lines = []
        for idx, item in enumerate(picked):
            slot = time_slots[idx] if idx < len(time_slots) else f"Step {idx + 1}"
            reason = "fits your mood and keeps things practical"
            tags = item.get("tags", [])
            if "quiet" in tags or item.get("crowd_level") == "low":
                reason = "keeps the vibe calm and avoids big crowds"
            elif "social" in tags or "music" in tags:
                reason = "adds a fun energy boost without overloading your day"
            timeline_lines.append(f"- {slot}: {item['name']} ({reason})")

        total_estimated = sum(float(x.get("cost", 0)) for x in picked)
        tradeoff = "- Tradeoff: Some options were filtered out to respect your constraints and budget."
        if constraints:
            tradeoff = (
                "- Tradeoff: Prioritized "
                + ", ".join(constraints[:2])
                + " over highly popular venues that may be crowded."
            )

        return (
            f"1) Timeline ({city}, {time_window})\n"
            + "\n".join(timeline_lines)
            + "\n\n2) Why this plan fits you\n"
            + f"- Matches your '{mood}' mood with a practical pace.\n"
            + (
                f"- Reflects your interests: {', '.join(interests)}.\n" if interests else "- Balances activity, food, and downtime.\n"
            )
            + f"- Estimated spend stays around {int(total_estimated)} in local currency terms.\n\n"
            + "3) Tradeoffs\n"
            + tradeoff
        )

    openai_api_key = _safe_secret("OPENAI_API_KEY")
    groq_api_key = _safe_secret("GROQ_API_KEY")

    if not openai_api_key and not groq_api_key:
        return _local_plan_fallback(context)

    if groq_api_key:
        client = OpenAI(api_key=groq_api_key, base_url="https://api.groq.com/openai/v1")
        model_name = "llama-3.1-8b-instant"
    else:
        client = OpenAI(api_key=openai_api_key)
        model_name = "gpt-4o-mini"

    system_prompt = (
        "You are a smart weekend planner.\n\n"
        "Given structured plan:\n"
        "- Create a realistic timeline\n"
        "- Explain why each activity fits the user\n"
        "- Respect constraints\n"
        "- Keep travel practical\n"
        "- Mention tradeoffs if needed"
    )

    user_prompt = (
        "Create a Saturday plan from this structured context:\n"
        f"{context}\n\n"
        "CRITICAL RULES:\n"
        "- Use only places present in candidate_plan.\n"
        "- Do not invent any new restaurant/activity names.\n"
        "- Do not repeat the same place multiple times in timeline.\n"
        "- Use each candidate place at most once.\n"
        "- If an item has source=mock, you may keep it but mention it is a backup option.\n\n"
        "Output format:\n"
        "1) Timeline with times\n"
        "2) Why this plan fits you\n"
        "3) Tradeoffs"
    )

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content or _local_plan_fallback(context)


def run_agent(input_data: Dict[str, Any], progress_cb=None) -> Tuple[str, List[Tuple[str, Any]], Dict[str, Any]]:
    trace: List[Tuple[str, Any]] = []

    def _progress(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    _progress("Parsing your preferences...")
    prefs = parse_user_preferences(input_data)
    trace.append(("Parsed Preferences", prefs))

    _progress("Finding real places from Overpass...")
    real_activities, real_places_note = get_real_places(prefs["city"], prefs["interests"], prefs["constraints"])
    trace.append(("Real Places (Overpass)", {"note": real_places_note, "places": real_activities}))

    _progress("Shortlisting activity options...")
    activities = real_activities or get_activity_options(prefs["city"], prefs["interests"], prefs["mood"])
    if not activities:
        activities = [
            {
                "name": "Neighborhood stroll and people-watching",
                "cost": 0,
                "crowd_level": "low",
                "tags": ["relax"],
            }
        ]
    trace.append(("Activities Found", activities))

    _progress("Filtering food options...")
    real_food_options = []
    for place in real_activities:
        tags = place.get("tags", [])
        place_kind = tags[0] if tags else ""
        if place_kind in {"cafe", "restaurant"}:
            real_food_options.append(
                {
                    "name": place["name"],
                    "cost": place.get("cost", 20),
                    "vegetarian": True,
                    "crowd_level": place.get("crowd_level", "medium"),
                    "source": "overpass",
                }
            )

    if real_food_options:
        seen_food = set()
        unique_real_food = []
        for opt in real_food_options:
            key = opt["name"].strip().lower()
            if key in seen_food:
                continue
            seen_food.add(key)
            unique_real_food.append(opt)
        food_options = unique_real_food
    else:
        food_options = get_food_options(prefs["city"], prefs["budget"], prefs["constraints"])

    if not food_options:
        food_options = [
            {
                "name": "Quiet cafe light meal",
                "cost": 12,
                "vegetarian": True,
                "crowd_level": "low",
                "source": "fallback",
            }
        ]
    # Build mixed plan with de-duplication and category variety.
    used = set()
    selected_activities = []
    for item in activities:
        key = item.get("name", "").strip().lower()
        if not key or key in used:
            continue
        selected_activities.append(item)
        used.add(key)
        if len(selected_activities) == 3:
            break

    selected_food = []
    for item in food_options:
        key = item.get("name", "").strip().lower()
        if not key or key in used:
            continue
        selected_food.append(item)
        used.add(key)
        break

    combined_plan = selected_activities + selected_food
    selection_reasons = []
    interests_set = set(prefs.get("interests", []))
    mood = prefs.get("mood", "")
    avoid_crowd = any("avoid crowded places" in c or "low crowd" in c for c in prefs.get("constraints", []))
    for item in combined_plan[:4]:
        name = item.get("name", "this place")
        reasons = []
        tags = set(item.get("tags", []))
        if tags & interests_set:
            reasons.append(f"matches interest: {', '.join(sorted(tags & interests_set))}")
        if mood and ("quiet" in tags or item.get("crowd_level") == "low"):
            reasons.append(f"fits mood '{mood}'")
        if avoid_crowd and item.get("crowd_level") in {"low", "medium"}:
            reasons.append("supports low-crowd preference")
        if item.get("cost", 0) <= prefs.get("budget", 0):
            reasons.append("within budget")
        if not reasons:
            reasons.append("keeps travel practical")
        selection_reasons.append(f"Selected {name} because it " + ", ".join(reasons) + ".")
    trace.append(("Selection Reasons", selection_reasons))

    _progress("Validating constraints and budget...")
    validated_plan = validate_plan(combined_plan, prefs["constraints"], prefs["budget"])
    trace.append(("Validated Plan", validated_plan))

    llm_context = {
        "preferences": prefs,
        "candidate_plan": validated_plan,
        "city": prefs["city"],
        "available_time": prefs["available_time"],
        "selection_reasons": selection_reasons,
    }
    _progress("Generating your final plan...")
    final_plan = generate_final_plan(llm_context)
    trace.append(("Final Output", final_plan))

    _progress("Done")

    return final_plan, trace, prefs


def main() -> None:
    st.set_page_config(page_title="Perfect Saturday Planner", page_icon="🗓️", layout="centered")

    st.markdown(
        """
        <style>
        :root {
            --bg-a: #f7fbff;
            --bg-b: #fff8ef;
            --card: #ffffff;
            --ink: #1f2937;
            --accent: #ff6b35;
            --accent-2: #2a9d8f;
            --soft: #ffe9df;
        }

        .stApp {
            background:
              radial-gradient(circle at 10% 10%, rgba(255, 107, 53, 0.10), transparent 35%),
              radial-gradient(circle at 90% 20%, rgba(42, 157, 143, 0.10), transparent 40%),
              linear-gradient(145deg, var(--bg-a), var(--bg-b));
            color: var(--ink);
        }

        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }

        header[data-testid="stHeader"] {
            background: transparent;
        }

        h1, h2, h3 {
            color: #0f172a;
            letter-spacing: 0.2px;
        }

        div[data-testid="stForm"] {
            background: var(--card);
            border: 1px solid #f3d7c7;
            border-radius: 16px;
            padding: 1rem 1rem 1rem 1rem;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
        }

        div[data-testid="stForm"] .stButton {
            margin-top: 0.75rem;
        }

        div[data-testid="stExpander"] {
            border-radius: 12px;
            border: 1px solid #e5e7eb;
            background: #ffffffcc;
        }

        div[data-testid="stNumberInput"] input,
        div[data-testid="stTextInput"] input,
        div[data-baseweb="input"] {
            border-radius: 10px !important;
        }

        .stButton > button {
            background: linear-gradient(90deg, var(--accent), #ff8c42);
            color: white;
            border: none;
            border-radius: 12px;
            font-weight: 600;
            padding: 0.55rem 1rem;
            box-shadow: 0 6px 16px rgba(255, 107, 53, 0.28);
        }

        .stButton > button:hover {
            background: linear-gradient(90deg, #f65d24, #ff7a22);
            transform: translateY(-1px);
        }

        .planner-badge {
            display: inline-block;
            font-size: 0.85rem;
            background: var(--soft);
            color: #7c2d12;
            border: 1px solid #ffc8b2;
            padding: 0.25rem 0.6rem;
            border-radius: 999px;
            margin-top: 0.4rem;
            margin-bottom: 0.9rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="planner-badge">AI + Real Places + Smart Fallback</div>', unsafe_allow_html=True)
    st.title("Perfect Saturday Planner")
    st.caption("Plan a personalized Saturday using an agent-style flow.")

    with st.form("planner_form"):
        city = st.text_input("City", placeholder="e.g., Bangalore")
        budget = st.number_input("Budget", min_value=0.0, step=5.0, value=30.0)
        time_col_1, time_col_2 = st.columns(2)
        with time_col_1:
            start_time_raw = st.time_input("Start Time", value=None)
        with time_col_2:
            end_time_raw = st.time_input("End Time", value=None)

        available_time = ""
        if start_time_raw is not None and end_time_raw is not None:
            available_time = f"{start_time_raw.strftime('%I:%M %p')} - {end_time_raw.strftime('%I:%M %p')}"
            st.caption(f"Available Time: {available_time}")
        else:
            st.caption("Select start and end time for your Saturday window.")
        mood = st.text_input("Mood", placeholder="e.g., chill, energetic, creative")
        interests = st.text_input("Interests (comma separated)", placeholder="books, music, nature")
        constraints = st.text_input(
            "Constraints (comma separated)",
            placeholder="vegetarian, avoid crowded places",
        )

        mood_is_vague = mood.strip().lower() in {"ok", "fine", "normal", "idk", "not sure", "mixed"}
        mood_detail = ""
        if mood_is_vague:
            mood_detail = st.text_input("Quick clarifier: what vibe do you want today?", placeholder="quiet recharge, social buzz, etc.")

        submitted = st.form_submit_button("Plan My Saturday")

    if submitted:
        if not city.strip() or not available_time.strip() or not mood.strip():
            st.warning("Please fill in at least city, time window (start/end), and mood.")
            return

        input_data = {
            "city": city,
            "budget": budget,
            "available_time": available_time,
            "start_time": start_time_raw.strftime('%I:%M %p') if start_time_raw else "",
            "end_time": end_time_raw.strftime('%I:%M %p') if end_time_raw else "",
            "mood": mood,
            "mood_detail": mood_detail,
            "interests": interests,
            "constraints": constraints,
        }

        progress_box = st.empty()
        progress_steps: List[str] = []

        def _on_progress(step_message: str) -> None:
            if step_message != "Done":
                progress_steps.append(f"- {step_message}")
                progress_box.info("Agent progress\n" + "\n".join(progress_steps))
                time.sleep(0.25)

        with st.spinner("Planning your Saturday..."):
            final_plan, trace, prefs = run_agent(input_data, progress_cb=_on_progress)

        progress_box.success("Done. Plan is ready.")

        st.subheader("Final Plan")
        st.markdown(final_plan)

        st.subheader("Why this plan fits you")
        st.write(
            f"This plan is tailored for your **{prefs['mood'] or 'current'}** mood, interests in "
            f"**{', '.join(prefs['interests']) if prefs['interests'] else 'a balanced mix'}**, "
            f"and constraints: **{', '.join(prefs['constraints']) if prefs['constraints'] else 'none'}**."
        )

        st.subheader("Agent Thinking")
        for step, data in trace:
            with st.expander(step):
                st.text(_trace_summary(step, data, prefs))


if __name__ == "__main__":
    main()
