# --- Step 1: Add New Tools ---
from flask import Flask, request, jsonify
from openai import OpenAI
import os
import sys
import datetime # <- ADDED for the candy counter
from collections import defaultdict # <- ADDED for the candy counter

# Add the directory containing 'handler.py' to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)

# --- Step 2: Add the Candy Counter Notebook ---
# Our magic notebook to count candies (requests) for each person (IP address)
ip_requests = defaultdict(lambda: {"count": 0, "date": datetime.date.min})
DAILY_LIMIT = 10 # Each person gets 10 free 'candies' (requests) per day
# --- END of Step 2 ---

# --- Helper function for analyzing text (copied from Streamlit app) ---
def analyze_text(text_to_analyze, api_key):
    analyzer_prompt = f"""
    Analyze the tone of the user's text.
    Return only three words separated by commas.
    1.  **Emotion:** Choose ONE from this list: [Angry, Frustrated, Sad, Confused, Happy, Calm]
    2.  **Professionalism:** Choose ONE from this list: [Unprofessional, Neutral, Professional]
    3.  **Risk:** Choose ONE from this list: [High-Risk, Medium-Risk, Safe]
    TEXT: "{text_to_analyze}"
    EXAMPLE_RESPONSE: Angry,Unprofessional,High-Risk
    """
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": analyzer_prompt}],
            temperature=0.0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error in analyze_text: {e}")
        return None

# --- Helper function for rewriting text (similar to Streamlit app) ---
def rewrite_text(text_to_rewrite, tone_instruction, api_key):
    tone_prompts_map = {
        "Boss": "Rewrite as if talking to your boss — respectful, concise, and calm.",
        "Client": "Rewrite as a professional client message — polite, confident, and reassuring.",
        "Teacher/Parent": "Rewrite calmly and empathetically for a teacher or parent.",
        "Wife/Partner": "Rewrite as if talking to your wife or partner — warm, emotionally intelligent, real, and caring.",
        "Friend": "Rewrite casually as if talking to a close friend — natural, fun, and authentic.",
        "Complaint": "Rewrite to express frustration constructively — firm, clear, but polite."
    }
    instruction = tone_prompts_map.get(tone_instruction, "Rewrite professionally.")

    prompt = f"User message: {text_to_rewrite}\n\nInstruction: {instruction}\n\nReturn only the rewritten message in the same language."

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error in rewrite_text: {e}")
        return None

# --- API Endpoint ---
@app.route('/', methods=['POST'])
def handle_request():
    # --- Step 3: Add the Door Checker ---
    # Get the person's computer address (IP address)
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    today = datetime.date.today()
    user_data = ip_requests[ip_address]

    # If the last time they asked was before today, reset their count
    if user_data["date"] < today:
        user_data["count"] = 0
        user_data["date"] = today

    # Check if they have already taken too many candies today
    if user_data["count"] >= DAILY_LIMIT:
        print(f"IP {ip_address} exceeded daily limit of {DAILY_LIMIT}")
        return jsonify({"error": f"Daily free limit of {DAILY_LIMIT} requests reached."}), 429

    # --- END of Step 3 ---

    try:
        data = request.json
        action = data.get('action') # 'evaluate' or 'rewrite'
        text = data.get('text')
        tone = data.get('tone') # e.g., 'Boss'

        if not text:
            return jsonify({"error": "No text provided"}), 400
        if not action:
            return jsonify({"error": "No action specified"}), 400

        # Get API key securely from environment variable
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
             print("API key not found in environment variables")
             return jsonify({"error": "API key not configured on server"}), 500

        # --- Step 4: Add the Increment Counter Line ---
        ip_requests[ip_address]["count"] += 1
        # --- END of Step 4 ---

        if action == 'evaluate':
            result = analyze_text(text, api_key)
            if result:
                try:
                    emotion, prof, risk = result.split(',')
                    return jsonify({"emotion": emotion, "professionalism": prof, "risk": risk})
                except ValueError:
                    print(f"Error splitting analysis result: {result}")
                    return jsonify({"error": "Failed to parse analysis"}), 500
            else:
                return jsonify({"error": "Evaluation failed"}), 500

        elif action == 'rewrite':
            if not tone:
                 return jsonify({"error": "Tone required for rewrite"}), 400
            result = rewrite_text(text, tone, api_key)
            if result:
                return jsonify({"rewritten_text": result})
            else:
                return jsonify({"error": "Rewrite failed"}), 500

        else:
            return jsonify({"error": "Invalid action"}), 400

    except Exception as e:
        print(f"General error in handle_request: {e}")
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

# This part is needed for Vercel to find the Flask app
if __name__ == "__main__":
    app.run()