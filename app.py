import os
from typing import Any, Dict, List, Tuple

import streamlit as st
from openai import OpenAI


def parse_user_preferences(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert raw form input into a structured preferences dictionary."""
    def _split_csv(value: str) -> List[str]:
        if not value:
            return []
        return [item.strip().lower() for item in value.split(",") if item.strip()]

    city = (input_data.get("city") or "").strip()
    budget = input_data.get("budget")
    available_time = (input_data.get("available_time") or "").strip()
    mood = (input_data.get("mood") or "").strip().lower()
    interests = _split_csv(input_data.get("interests", ""))
    constraints = _split_csv(input_data.get("constraints", ""))
    mood_detail = (input_data.get("mood_detail") or "").strip()

    return {
        "city": city,
        "budget": float(budget) if budget is not None else 0.0,
        "available_time": available_time,
        "mood": mood,
        "mood_detail": mood_detail,
        "interests": interests,
        "constraints": constraints,
    }


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


def get_food_options(city: str, budget: float, constraints: List[str]) -> List[Dict[str, Any]]:
    """Return mock food options honoring vegetarian/budget/low-crowd constraints."""
    city_label = city if city else "your city"
    options = [
        {
            "name": f"Green Leaf Vegetarian Bistro ({city_label})",
            "cost": 18,
            "vegetarian": True,
            "crowd_level": "low",
        },
        {
            "name": f"Corner Noodle Bar ({city_label})",
            "cost": 12,
            "vegetarian": True,
            "crowd_level": "medium",
        },
        {
            "name": f"Rooftop Grill ({city_label})",
            "cost": 35,
            "vegetarian": False,
            "crowd_level": "high",
        },
        {
            "name": f"Quiet Soup Cafe ({city_label})",
            "cost": 14,
            "vegetarian": True,
            "crowd_level": "low",
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
    for item in plan:
        if avoid_crowds and item.get("crowd_level") == "high":
            continue
        if budget > 0 and item.get("cost", 0) > budget:
            continue
        validated.append(item)

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

    openai_api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    groq_api_key = st.secrets.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")

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


def run_agent(input_data: Dict[str, Any]) -> Tuple[str, List[Tuple[str, Any]], Dict[str, Any]]:
    trace: List[Tuple[str, Any]] = []

    prefs = parse_user_preferences(input_data)
    trace.append(("Parsed Preferences", prefs))

    activities = get_activity_options(prefs["city"], prefs["interests"], prefs["mood"])
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

    food_options = get_food_options(prefs["city"], prefs["budget"], prefs["constraints"])
    if not food_options:
        food_options = [
            {
                "name": "Quiet cafe light meal",
                "cost": 12,
                "vegetarian": True,
                "crowd_level": "low",
            }
        ]
    trace.append(("Food Options", food_options))

    combined_plan = activities[:3] + food_options[:1]
    validated_plan = validate_plan(combined_plan, prefs["constraints"], prefs["budget"])
    trace.append(("Validated Plan", validated_plan))

    llm_context = {
        "preferences": prefs,
        "candidate_plan": validated_plan,
        "city": prefs["city"],
        "available_time": prefs["available_time"],
    }
    final_plan = generate_final_plan(llm_context)
    trace.append(("Final Output", final_plan))

    return final_plan, trace, prefs


def main() -> None:
    st.set_page_config(page_title="Perfect Saturday Planner", page_icon="🗓️", layout="centered")
    st.title("Perfect Saturday Planner")
    st.caption("Plan a personalized Saturday using an agent-style flow.")

    with st.form("planner_form"):
        city = st.text_input("City", placeholder="e.g., Bangalore")
        budget = st.number_input("Budget", min_value=0.0, step=5.0, value=30.0)
        available_time = st.text_input("Available Time", placeholder="e.g., 9 AM - 6 PM")
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
            st.warning("Please fill in at least city, available time, and mood.")
            return

        input_data = {
            "city": city,
            "budget": budget,
            "available_time": available_time,
            "mood": mood,
            "mood_detail": mood_detail,
            "interests": interests,
            "constraints": constraints,
        }

        with st.spinner("Planning your Saturday..."):
            final_plan, trace, prefs = run_agent(input_data)

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
                st.json(data)


if __name__ == "__main__":
    main()
