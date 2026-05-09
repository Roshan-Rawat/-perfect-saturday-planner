# Perfect Saturday Planner

A small Streamlit agent app that builds a personalized Saturday plan from user preferences.

## Features

- Structured input form: city, budget, available time, mood, interests, constraints
- Tool-based agent flow (not one giant prompt):
  - `parse_user_preferences`
  - `get_activity_options`
  - `get_food_options`
  - `validate_plan`
  - `generate_final_plan`
- Agent trace UI under **Agent Thinking**
- Failure handling:
  - Missing required input warning
  - Fallback activity/food when no options match
- Works with or without model API keys:
  - With `OPENAI_API_KEY`: uses `gpt-4o-mini`
  - With `GROQ_API_KEY`: uses `llama-3.1-8b-instant` via Groq OpenAI-compatible endpoint
  - Without key: local heuristic plan generator (still practical and personalized)

## Local Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Cloud Deploy

1. Push this repo to GitHub.
2. Go to Streamlit Cloud and create a new app from the repo.
3. Set main file to `app.py`.
4. (Optional) Add one of these secrets:

```toml
OPENAI_API_KEY="your_key_here"
GROQ_API_KEY="your_key_here"
```

5. Deploy and share the generated public URL.

## Notes on AI Tooling

Built quickly with AI coding assistance for:
- initial app scaffolding and Streamlit form flow
- tool-function decomposition and trace structure
- fallback logic and deployment-readiness checks
