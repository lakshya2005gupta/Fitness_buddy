"""
FITNESS BUDDY — Flask + IBM Watsonx.ai
AI-powered personal fitness coach web application
"""

import os
import re
import json
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv

# ── Load environment variables from .env ──────────────────────────
load_dotenv()

# ── Flask app setup ───────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fitness-buddy-dev-secret-change-in-prod")

# ── Logging ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
#  AGENT_INSTRUCTIONS — Customize the AI coach here
#  ─────────────────────────────────────────────────────────────────
#  This is the system prompt that shapes every response from the
#  IBM Granite model. Edit this block freely to change:
#    • Tone          – formal, friendly, motivational, clinical
#    • Philosophy    – HIIT-first, low-impact, yoga-inclusive, etc.
#    • Safety rules  – medical disclaimers, injury handling
#    • Food culture  – regional preferences, dietary flags
#    • Language      – English default; add "respond in Hindi" etc.
# ══════════════════════════════════════════════════════════════════
AGENT_INSTRUCTIONS = """
You are Fitness Buddy — a knowledgeable, warm, and motivating AI personal fitness coach.

## PERSONALITY & TONE
- Speak like a supportive, encouraging coach — never preachy or judgmental.
- Use clear, simple language. Avoid excessive jargon unless the user seems experienced.
- Add a touch of positivity and energy, but stay concise and practical.
- Address the user directly using "you" to keep it personal.

## FITNESS PHILOSOPHY
- Advocate for sustainable, progressive fitness habits over quick fixes.
- Emphasize consistency over intensity, especially for beginners.
- Respect all fitness levels — beginner, intermediate, advanced.
- Prioritise bodyweight and minimal-equipment home workouts by default.
- Include warm-up and cool-down reminders for all workout plans.
- Recommend a balanced approach: strength, cardio, flexibility, and rest.

## NUTRITION GUIDELINES
- Suggest whole, accessible, budget-friendly foods.
- Include diverse Indian vegetarian options: dal, paneer, roti, idli,
  rajma, chana, oats, poha, sprouts, curd, seasonal vegetables.
- Include non-vegetarian options when appropriate: eggs, chicken breast,
  fish (especially rohu/hilsa/salmon), lean meats.
- Respect common dietary preferences: vegetarian, vegan, gluten-free.
- Promote adequate protein, fibre, hydration, and micronutrients.
- Avoid recommending expensive supplements as necessities.

## WORKOUT PLANNING RULES
- Always ask about or acknowledge: available time, equipment, fitness level,
  any injuries or physical limitations before prescribing workouts.
- Provide specific exercise names, sets, reps, and rest durations.
- Flag high-impact exercises for users with joint issues (knee, back pain).
- Scale difficulty appropriately: offer easier and harder variations.

## SAFETY GUARDRAILS (CRITICAL)
- ALWAYS advise consulting a doctor before starting any new fitness programme,
  especially for users who mention medical conditions.
- NEVER diagnose medical conditions or prescribe medication.
- If a user describes symptoms of injury or illness, recommend professional help.
- Do not provide advice that could cause harm to vulnerable individuals.
- Decline to generate harmful, inappropriate, or off-topic content politely.

## HABIT & LIFESTYLE COACHING
- Encourage the "big four" daily habits: hydration, sleep (7–9 hrs),
  movement, and mindful eating.
- Provide small, actionable habit nudges rather than overwhelming plans.
- Celebrate small wins. Acknowledge and reframe setbacks positively.

## RESPONSE FORMAT
- For workout plans: use numbered lists with exercise, sets × reps, and rest.
- For meal suggestions: use clear sections (Breakfast / Lunch / Dinner / Snacks).
- For motivational quotes: keep them under 2 sentences, punchy and original.
- For general questions: 3–5 concise paragraphs maximum.
- Always end responses with a brief encouraging sign-off when appropriate.
""".strip()

# ── Watsonx.ai credentials — hardcoded (move to .env for production) ──
WATSONX_APIKEY     = os.getenv("WATSONX_APIKEY", "858PzW7eqHuF7T0gezjAA9T50RUYskIRHr-nRM0aTlhA")
WATSONX_PROJECT_ID = os.getenv("WATSONX_PROJECT_ID", "a1f67a4b-2d34-460c-91f7-889c28d6fe91")
WATSONX_URL        = os.getenv("WATSONX_URL", "https://au-syd.ml.cloud.ibm.com")

# Model available in au-syd region that supports the chat API
GRANITE_MODEL_ID   = "meta-llama/llama-3-3-70b-instruct"

# Generation parameters for the chat endpoint
GENERATION_PARAMS  = {
    "max_tokens": 800,
    "temperature": 0.7,
    "top_p": 0.9,
    "repetition_penalty": 1.1,
}

def get_watsonx_model():
    """
    Initialise and return an IBM Watsonx.ai ModelInference client.
    Uses the chat API (/ml/v1/text/chat) which is the current supported endpoint.
    Returns None if credentials are missing or the SDK cannot connect.
    """
    if not WATSONX_APIKEY or not WATSONX_PROJECT_ID:
        logger.warning("Watsonx credentials not configured — running in demo mode.")
        return None
    try:
        from ibm_watsonx_ai import Credentials
        from ibm_watsonx_ai.foundation_models import ModelInference

        credentials = Credentials(
            url=WATSONX_URL,
            api_key=WATSONX_APIKEY,
        )
        model = ModelInference(
            model_id=GRANITE_MODEL_ID,
            credentials=credentials,
            project_id=WATSONX_PROJECT_ID,
            params=GENERATION_PARAMS,
        )
        logger.info("IBM Watsonx.ai ModelInference client initialised successfully.")
        return model
    except ImportError:
        logger.error("ibm-watsonx-ai package not installed. Run: pip install ibm-watsonx-ai")
        return None
    except Exception as exc:
        logger.error("Failed to initialise Watsonx.ai client: %s", exc)
        return None


def sanitize_input(text: str) -> str:
    """
    Basic input sanitization to prevent prompt injection attacks.
    Strips attempts to override system instructions.
    """
    if not isinstance(text, str):
        return ""
    # Truncate to a safe max length
    text = text[:2000]
    # Remove control characters
    text = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", text)
    # Block common prompt injection patterns
    injection_patterns = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"forget\s+(everything|all)",
        r"you\s+are\s+now\s+",
        r"act\s+as\s+(if\s+you\s+are|a\s+)",
        r"system\s*:\s*",
        r"<\|system\|>",
    ]
    for pattern in injection_patterns:
        text = re.sub(pattern, "[filtered]", text, flags=re.IGNORECASE)
    return text.strip()


def build_messages(user_message: str, chat_history: list) -> list:
    """
    Build a messages list for the chat API.
    Format: [{"role": "system", "content": ...}, {"role": "user"|"assistant", "content": ...}, ...]
    Keeps last 6 turns of history to manage token budget.
    """
    messages = [{"role": "system", "content": AGENT_INSTRUCTIONS}]
    for turn in chat_history[-6:]:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


def call_watsonx(user_message: str, chat_history: list, model) -> str:
    """
    Call the IBM Watsonx.ai model via the chat API and return the reply text.
    Falls back to a canned demo response if the model is unavailable.
    """
    if model is None:
        return (
            "🏋️ **Demo Mode Active** — IBM Watsonx.ai credentials are not configured yet.\n\n"
            "Add your `WATSONX_APIKEY` and `WATSONX_PROJECT_ID` to the `.env` file to "
            "activate the full AI coach. In the meantime, I'm still here to help you "
            "explore the dashboard! 💪"
        )
    try:
        messages = build_messages(user_message, chat_history)
        response = model.chat(messages=messages)
        # Extract text from chat response structure
        reply = response["choices"][0]["message"]["content"]
        return reply.strip()
    except Exception as exc:
        logger.error("Watsonx generation error: %s", exc)
        return (
            "⚠️ I'm having trouble connecting to the AI service right now. "
            "Please check your credentials and IBM Cloud status, then try again. "
            "Your fitness journey continues — don't let a tech hiccup slow you down! 💪"
        )


# ── Initialise model once at startup ─────────────────────────────
watsonx_model = get_watsonx_model()

# ── Static fitness data used by non-AI features ───────────────────
WORKOUT_LIBRARY = {
    "15": {
        "beginner": [
            {"exercise": "Jumping Jacks", "sets": 2, "reps": "20", "rest": "30s"},
            {"exercise": "Wall Push-ups", "sets": 2, "reps": "10", "rest": "30s"},
            {"exercise": "Bodyweight Squats", "sets": 2, "reps": "12", "rest": "30s"},
            {"exercise": "Plank", "sets": 2, "reps": "20s hold", "rest": "30s"},
            {"exercise": "Seated Leg Raises", "sets": 2, "reps": "10", "rest": "30s"},
        ],
        "intermediate": [
            {"exercise": "High Knees", "sets": 3, "reps": "30s", "rest": "20s"},
            {"exercise": "Push-ups", "sets": 3, "reps": "12", "rest": "30s"},
            {"exercise": "Jump Squats", "sets": 3, "reps": "10", "rest": "30s"},
            {"exercise": "Mountain Climbers", "sets": 3, "reps": "20", "rest": "20s"},
        ],
        "advanced": [
            {"exercise": "Burpees", "sets": 4, "reps": "10", "rest": "20s"},
            {"exercise": "Plyometric Push-ups", "sets": 3, "reps": "10", "rest": "30s"},
            {"exercise": "Pistol Squat (each leg)", "sets": 3, "reps": "6", "rest": "30s"},
            {"exercise": "Plank to Pike", "sets": 3, "reps": "12", "rest": "20s"},
        ],
    },
    "30": {
        "beginner": [
            {"exercise": "March in Place", "sets": 3, "reps": "60s", "rest": "30s"},
            {"exercise": "Knee Push-ups", "sets": 3, "reps": "10", "rest": "40s"},
            {"exercise": "Goblet Squat (water bottle)", "sets": 3, "reps": "12", "rest": "40s"},
            {"exercise": "Glute Bridge", "sets": 3, "reps": "15", "rest": "30s"},
            {"exercise": "Dead Bug", "sets": 3, "reps": "8 each side", "rest": "30s"},
            {"exercise": "Standing Calf Raises", "sets": 3, "reps": "20", "rest": "20s"},
        ],
        "intermediate": [
            {"exercise": "Jump Rope / Shadow Rope", "sets": 3, "reps": "60s", "rest": "30s"},
            {"exercise": "Diamond Push-ups", "sets": 3, "reps": "12", "rest": "40s"},
            {"exercise": "Bulgarian Split Squat", "sets": 3, "reps": "10 each", "rest": "40s"},
            {"exercise": "Pike Push-ups", "sets": 3, "reps": "10", "rest": "30s"},
            {"exercise": "Bicycle Crunches", "sets": 3, "reps": "20", "rest": "30s"},
            {"exercise": "Superman Hold", "sets": 3, "reps": "10s hold", "rest": "20s"},
        ],
        "advanced": [
            {"exercise": "Box Jump (chair)", "sets": 4, "reps": "10", "rest": "30s"},
            {"exercise": "Archer Push-ups", "sets": 4, "reps": "8 each", "rest": "40s"},
            {"exercise": "Single-leg Deadlift", "sets": 3, "reps": "10 each", "rest": "30s"},
            {"exercise": "Handstand Wall Hold", "sets": 3, "reps": "20s", "rest": "40s"},
            {"exercise": "Dragon Flag (progression)", "sets": 3, "reps": "5", "rest": "40s"},
        ],
    },
    "45": {
        "beginner": [
            {"exercise": "Brisk Walking in Place", "sets": 1, "reps": "5 min", "rest": "—"},
            {"exercise": "Standard Push-ups", "sets": 4, "reps": "10", "rest": "45s"},
            {"exercise": "Bodyweight Squats", "sets": 4, "reps": "15", "rest": "45s"},
            {"exercise": "Dumbbell Row (water bottle)", "sets": 3, "reps": "12 each", "rest": "40s"},
            {"exercise": "Glute Bridge March", "sets": 3, "reps": "10 each", "rest": "30s"},
            {"exercise": "Plank", "sets": 3, "reps": "30s hold", "rest": "30s"},
            {"exercise": "Child's Pose Stretch", "sets": 1, "reps": "3 min", "rest": "—"},
        ],
        "intermediate": [
            {"exercise": "Jump Rope", "sets": 1, "reps": "5 min", "rest": "—"},
            {"exercise": "Wide Push-ups", "sets": 4, "reps": "15", "rest": "40s"},
            {"exercise": "Sumo Squat Pulse", "sets": 4, "reps": "20", "rest": "40s"},
            {"exercise": "Renegade Row", "sets": 3, "reps": "8 each", "rest": "45s"},
            {"exercise": "Reverse Lunges", "sets": 3, "reps": "12 each", "rest": "40s"},
            {"exercise": "Hollow Body Hold", "sets": 3, "reps": "20s", "rest": "30s"},
            {"exercise": "Hip Flexor Stretch", "sets": 1, "reps": "3 min", "rest": "—"},
        ],
        "advanced": [
            {"exercise": "Burpee Complex", "sets": 5, "reps": "10", "rest": "30s"},
            {"exercise": "Typewriter Push-ups", "sets": 4, "reps": "8 each", "rest": "40s"},
            {"exercise": "Pistol Squats", "sets": 4, "reps": "6 each", "rest": "40s"},
            {"exercise": "L-sit Hold (chairs)", "sets": 4, "reps": "10s", "rest": "40s"},
            {"exercise": "Nordic Curls", "sets": 3, "reps": "5", "rest": "60s"},
            {"exercise": "Full Body Stretch Flow", "sets": 1, "reps": "5 min", "rest": "—"},
        ],
    },
}

DAILY_HABITS = [
    {"id": "water", "label": "Drink 8 Glasses of Water", "icon": "💧"},
    {"id": "workout", "label": "Complete Today's Workout", "icon": "🏋️"},
    {"id": "sleep", "label": "Got 7+ Hours of Sleep", "icon": "😴"},
    {"id": "steps", "label": "10,000 Steps / 30 min Walk", "icon": "🚶"},
    {"id": "veggies", "label": "Ate 5 Servings of Veg/Fruit", "icon": "🥦"},
    {"id": "screen", "label": "Screen-free 1hr Before Bed", "icon": "📵"},
]

NUTRITION_PLANS = {
    "fat_loss": {
        "calories": "1600–1900 kcal",
        "macro_tip": "High protein (30%), moderate carbs (40%), healthy fats (30%)",
        "meals": {
            "breakfast": ["Oats with banana & chia seeds", "Moong dal chilla with mint chutney", "Scrambled eggs + whole wheat toast"],
            "lunch": ["Rajma brown rice + salad", "Grilled chicken with roti & dal", "Paneer bhurji with phulka + curd"],
            "dinner": ["Palak dal + 1 roti + sautéed veg", "Baked fish with stir-fried vegetables", "Tofu stir-fry with quinoa"],
            "snacks": ["Roasted chana (handful)", "Apple with 1 tbsp peanut butter", "Greek yogurt with cucumber"],
        },
    },
    "muscle_gain": {
        "calories": "2400–2800 kcal",
        "macro_tip": "High protein (35%), high carbs (45%), healthy fats (20%)",
        "meals": {
            "breakfast": ["6-egg omelette with vegetables + oats", "Paneer paratha + 2 glasses milk", "Banana smoothie with whey + oats"],
            "lunch": ["Chicken breast 200g + rice + dal", "Soya chunks curry + 3 rotis + salad", "Eggs (4) + sweet potato + veg"],
            "dinner": ["Cottage cheese (200g) + dal + 2 rotis", "Salmon / Rohu fillet + rice + sabzi", "Rajma + rice + raita"],
            "snacks": ["Peanut butter sandwich (whole wheat)", "Mixed nuts + dates (100g)", "Boiled eggs (3) + banana"],
        },
    },
    "endurance": {
        "calories": "2000–2400 kcal",
        "macro_tip": "Moderate protein (25%), high carbs (55%), healthy fats (20%)",
        "meals": {
            "breakfast": ["Poha with peanuts & lemon", "Banana + whole grain toast + peanut butter", "Idli (4) + sambar + coconut chutney"],
            "lunch": ["Rice + dal + vegetable curry + curd", "Whole wheat pasta with chicken & vegetables", "Roti + chana masala + salad"],
            "dinner": ["Khichdi with ghee + pickles", "Oats khichdi with vegetables", "Rice + fish curry + salad"],
            "snacks": ["Banana + dates (energy balls)", "Coconut water + handful of nuts", "Sprout salad with lemon"],
        },
    },
    "general": {
        "calories": "1800–2200 kcal",
        "macro_tip": "Balanced macros: protein (25%), carbs (50%), fats (25%)",
        "meals": {
            "breakfast": ["Dalia (broken wheat) khichdi with veg", "2 eggs + toast + seasonal fruit", "Upma with sambar"],
            "lunch": ["Dal + roti + sabzi + salad", "Rice + any curry + raita", "Wrap with paneer / chicken + salad"],
            "dinner": ["Soup + 1-2 rotis + dry sabzi", "Brown rice + dal tadka + papad", "Salad bowl with protein of choice"],
            "snacks": ["Masala chaas (buttermilk)", "Fruit salad", "Makhana (foxnuts) roasted"],
        },
    },
}

# ── Routes ────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Render the main dashboard page."""
    today = datetime.now().strftime("%A, %B %d %Y")
    return render_template(
        "index.html",
        habits=DAILY_HABITS,
        today=today,
    )


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    POST /api/chat
    Body: { "message": str, "history": list[{role, content}] }
    Returns: { "reply": str }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        raw_message = data.get("message", "").strip()
        history = data.get("history", [])

        if not raw_message:
            return jsonify({"error": "Message cannot be empty."}), 400

        # Sanitize input
        clean_message = sanitize_input(raw_message)
        if not clean_message:
            return jsonify({"error": "Invalid input."}), 400

        # Validate history format
        if not isinstance(history, list):
            history = []
        history = [
            h for h in history
            if isinstance(h, dict) and "role" in h and "content" in h
        ][-10:]  # cap at last 10 turns

        reply = call_watsonx(clean_message, history, watsonx_model)

        return jsonify({"reply": reply})

    except Exception as exc:
        logger.error("Chat API error: %s", exc)
        return jsonify({"error": "Internal server error. Please try again."}), 500


@app.route("/api/workout", methods=["POST"])
def api_workout():
    """
    POST /api/workout
    Body: { "duration": "15"|"30"|"45", "level": "beginner"|"intermediate"|"advanced",
            "focus": str, "goal": str }
    Returns: { "workout": list, "ai_intro": str }
    """
    try:
        data     = request.get_json(force=True, silent=True) or {}
        duration = data.get("duration", "30")
        level    = data.get("level", "beginner").lower()
        focus    = sanitize_input(data.get("focus", "full body"))
        goal     = sanitize_input(data.get("goal", "general fitness"))

        if duration not in WORKOUT_LIBRARY:
            duration = "30"
        if level not in ("beginner", "intermediate", "advanced"):
            level = "beginner"

        workout = WORKOUT_LIBRARY[duration][level]

        # Generate a short AI intro for the workout via chat API
        ai_intro = call_watsonx(
            f"Give me a 2-sentence motivating intro for this home workout: "
            f"{duration}-minute {level} workout focused on {focus}. Goal: {goal}. "
            "Be concise and energetic.",
            [],
            watsonx_model,
        )

        return jsonify({"workout": workout, "ai_intro": ai_intro, "duration": duration, "level": level})

    except Exception as exc:
        logger.error("Workout API error: %s", exc)
        return jsonify({"error": "Could not generate workout. Please try again."}), 500


@app.route("/api/nutrition", methods=["POST"])
def api_nutrition():
    """
    POST /api/nutrition
    Body: { "goal": "fat_loss"|"muscle_gain"|"endurance"|"general",
            "diet_type": "veg"|"non-veg"|"vegan" }
    Returns: { "plan": dict }
    """
    try:
        data      = request.get_json(force=True, silent=True) or {}
        goal      = data.get("goal", "general").lower().replace(" ", "_")
        diet_type = sanitize_input(data.get("diet_type", "non-veg"))

        if goal not in NUTRITION_PLANS:
            goal = "general"

        plan = NUTRITION_PLANS[goal]
        return jsonify({"plan": plan, "goal": goal, "diet_type": diet_type})

    except Exception as exc:
        logger.error("Nutrition API error: %s", exc)
        return jsonify({"error": "Could not fetch nutrition plan."}), 500


@app.route("/api/motivation", methods=["GET"])
def api_motivation():
    """
    GET /api/motivation
    Returns: { "quote": str }
    """
    try:
        quote = call_watsonx(
            "Generate one powerful, original fitness motivational quote (2 sentences max). "
            "Make it uplifting, energetic, and focused on consistency and progress.",
            [],
            watsonx_model,
        )
        return jsonify({"quote": quote})
    except Exception as exc:
        logger.error("Motivation API error: %s", exc)
        return jsonify({"quote": "Every rep, every step, every choice — they all add up. Keep going! 💪"}), 200


@app.route("/api/habits", methods=["POST"])
def api_habits():
    """
    POST /api/habits
    Body: { "habits": { habit_id: bool } }
    Stores habit state in session and returns a completion percentage + AI encouragement.
    Returns: { "percent": int, "message": str }
    """
    try:
        data   = request.get_json(force=True, silent=True) or {}
        habits = data.get("habits", {})

        if not isinstance(habits, dict):
            return jsonify({"error": "Invalid habits data."}), 400

        completed = sum(1 for v in habits.values() if v)
        total     = len(DAILY_HABITS)
        percent   = round((completed / total) * 100) if total > 0 else 0

        # Store in session for persistence within the browsing session
        session["habits"] = habits
        session["habit_date"] = datetime.now().strftime("%Y-%m-%d")

        # Quick AI encouragement based on completion
        if percent == 100:
            message = "🎉 Perfect day! You've completed all your habits. Absolutely crushing it!"
        elif percent >= 66:
            message = f"🔥 {percent}% done — you're on fire! Just a few more habits to go. Finish strong!"
        elif percent >= 33:
            message = f"💪 {percent}% complete. Good progress! Every habit you tick off compounds over time."
        else:
            message = f"🌱 {percent}% done today. It's not about being perfect — it's about showing up. Keep going!"

        return jsonify({"percent": percent, "message": message, "completed": completed, "total": total})

    except Exception as exc:
        logger.error("Habits API error: %s", exc)
        return jsonify({"error": "Could not update habits."}), 500


# ── Main entry point ──────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info("Starting Fitness Buddy on http://localhost:%d", port)
    app.run(host="0.0.0.0", port=port, debug=debug)
