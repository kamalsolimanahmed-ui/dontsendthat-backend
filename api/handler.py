from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os

# ---------------------------------------------
# Flask App Setup
# ---------------------------------------------
app = Flask(__name__)
CORS(app)  # ✅ allow Chrome extension requests

# ---------------------------------------------
# OpenAI Setup
# ---------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ Missing OPENAI_API_KEY environment variable")

client = OpenAI(api_key=OPENAI_API_KEY)

# ---------------------------------------------
# Health Check Endpoint
# ---------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "✅ API is running!"})

# ---------------------------------------------
# Main Rewrite / Analyze Endpoint
# ---------------------------------------------
@app.route("/", methods=["POST"])
def rewrite_text():
    try:
        data = request.get_json(force=True)
        action = data.get("action", "").lower()
        text = data.get("text", "").strip()
        tone = data.get("tone", "general").lower()

        if not text:
            return jsonify({"error": "Missing text"}), 400

        # -------------------------------
        # Build prompt based on action
        # -------------------------------
        if action == "analyze":
            prompt = (
                f"Analyze the following message and return three labeled lines:\n"
                f"1. Emotion (e.g., Angry, Calm, Sad)\n"
                f"2. Professionalism (Professional, Neutral, or Unprofessional)\n"
                f"3. Risk Level (High, Medium, or Low)\n\n"
                f"Message:\n{text}"
            )
        elif action == "rewrite":
            prompt = (
                f"Rewrite this message to sound respectful, natural, and clear "
                f"for a {tone} context while keeping the same meaning:\n\n{text}"
            )
        else:
            return jsonify({"error": "Invalid action"}), 400

        # -------------------------------
        # Call OpenAI
        # -------------------------------
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
        )

        result = response.choices[0].message.content.strip()
        return jsonify({"rewritten_text": result})

    except Exception as e:
        print("❌ Error:", e)
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------
# Local Dev Entry Point
# ---------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))  # ✅ use Render’s dynamic port
    app.run(host="0.0.0.0", port=port)

