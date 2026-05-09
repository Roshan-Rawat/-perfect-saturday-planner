# Perfect Saturday Planner

Perfect Saturday Planner is a small AI-powered Streamlit web app.
It takes your city, budget, time, mood, interests, and constraints, then builds a practical Saturday plan.

## What This App Does

- Collects user preferences from a clean form
- Finds place options (real places from Overpass when available)
- Filters options based on budget and constraints
- Generates a final timeline with reasons
- Shows a simple "Agent Thinking" trace so you can see each step

## Main Features

### 1) Input Form
You can enter:
- City
- Budget
- Start time and end time
- Mood
- Interests (comma-separated)
- Constraints (comma-separated)

### 2) Tool-Based Agent Flow
This app does not use one giant prompt.
It uses separate functions (tools):

- `parse_user_preferences(input_data)`
- `get_real_places(city, interests, constraints)`
- `get_activity_options(city, interests, mood)`
- `get_food_options(city, budget, constraints)`
- `validate_plan(plan, constraints, budget)`
- `generate_final_plan(context)`
- `run_agent(input_data)` to orchestrate all steps

### 3) Real Data + Safe Fallback
- Tries to fetch real places with Overpass API
- If Overpass is slow/fails/returns nothing, it uses mock fallback data
- This keeps the app working reliably

### 4) Final Output
The app shows:
- Final Plan (timeline + explanation)
- Why this plan fits you
- Agent Thinking trace

### 5) Failure Handling
- Shows warning if required fields are missing
- Uses fallback suggestion if valid options become empty
- Works even without API keys (local fallback plan generation)

### 6) Better UX
- Loading spinner while planning
- Progress updates during agent steps
- Cleaner and colorful UI styling

## API / Model Behavior

- If `GROQ_API_KEY` is set: uses Groq (`llama-3.1-8b-instant`)
- Else if `OPENAI_API_KEY` is set: uses OpenAI (`gpt-4o-mini`)
- Else: uses local fallback text generation so the app still works

## Project Structure

Single-file app:
- `app.py`

Dependencies:
- `requirements.txt`

## Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Cloud

1. Push this project to GitHub
2. Open Streamlit Cloud and create a new app
3. Select your repo and set main file to `app.py`
4. (Optional) Add secrets:

```toml
GROQ_API_KEY="your_key_here"
OPENAI_API_KEY="your_key_here"
```

5. Deploy and copy your public app URL
