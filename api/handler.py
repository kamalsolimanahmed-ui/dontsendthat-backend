from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os

app = Flask(__name__)
CORS(app)  # allow cross-origin from extension

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "API is running!"})

@app.route("/", methods=["POST"])
def rewrite_text():
    try:
        data = request.get_json()
        action = data.get("action")
        text = data.get("text")
        tone = data.get("tone", "general")

        if not text:
            return jsonify({"error": "Missing text"}), 400

        prompt = ""
        if action == "analyze":
            prompt = f"Analyze this message for tone and emotion: {text}"
        elif action == "rewrite":
            prompt = f"Rewrite this message in a respectful, clear tone for {tone}: {text}"

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300
        )

        result = response.choices[0].message.content
        return jsonify({"rewritten_text": result})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
