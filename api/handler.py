from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os, json, secrets, stripe, datetime

app = Flask(__name__)
CORS(app)

# --- Stripe setup ---
stripe.api_key = os.getenv("STRIPE_SECRET")
PRICE_ID = "price_1SKBy9IDtEuyeKmrWN1eRvgJ"  # ⬅️ Replace this with your real Stripe Price ID

# --- OpenAI setup ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# --- Token storage ---
TOKEN_FILE = "tokens.json"
if not os.path.exists(TOKEN_FILE):
    with open(TOKEN_FILE, "w") as f:
        json.dump({"tokens": {}, "usage": {}}, f)


def load_data():
    with open(TOKEN_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f, indent=2)


@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "✅ API running (Stripe + Token system ready)"})


# --- Stripe checkout session ---
@app.route("/create-checkout-session", methods=["POST"])
def create_checkout():
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": PRICE_ID, "quantity": 1}],
            success_url="https://dontsendthat-backend-1.onrender.com/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://dontsendthat-backend-1.onrender.com/cancel",
        )
        return jsonify({"url": session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# --- Success page with token ---
@app.route("/success")
def success():
    session_id = request.args.get("session_id")
    if not session_id:
        return "Missing session_id", 400
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        customer_email = session.customer_details.email if session.customer_details else "unknown"

        data = load_data()
        token = "DST-" + secrets.token_hex(4).upper()
        data["tokens"][token] = {"email": customer_email, "created": str(datetime.date.today())}
        save_data(data)

        return f"""
        <html>
          <head><title>Payment Successful</title></head>
          <body style='font-family:Arial;text-align:center;margin-top:50px;'>
            <h2>✅ Payment Successful!</h2>
            <p>Your Pro Access Token:</p>
            <div style='font-size:20px;color:#ff4081;font-weight:bold;'>{token}</div>
            <p>Copy and paste this token into the extension popup to unlock unlimited access.</p>
          </body>
        </html>
        """
    except Exception as e:
        return f"Error verifying payment: {e}", 400


# --- Cancel page ---
@app.route("/cancel")
def cancel():
    return """
    <html>
      <head><title>Payment Cancelled</title></head>
      <body style='font-family:Arial;text-align:center;margin-top:50px;'>
        <h2>❌ Payment Cancelled</h2>
        <p>No worries! You can continue using the Free Plan (3 rewrites/day).</p>
      </body>
    </html>
    """


# --- Verify token ---
@app.route("/verify-token", methods=["POST"])
def verify_token():
    token = request.json.get("token")
    data = load_data()
    if token in data["tokens"]:
        return jsonify({"valid": True})
    return jsonify({"valid": False}), 403


# --- Main rewrite/analyze route ---
@app.route("/", methods=["POST"])
def rewrite_text():
    try:
        data = request.get_json(force=True)
        action = data.get("action", "").lower()
        text = data.get("text", "").strip()
        tone = data.get("tone", "general").lower()
        token = data.get("token")

        if not text:
            return jsonify({"error": "Missing text"}), 400

        store = load_data()
        is_pro = token in store["tokens"]

        # --- Free plan logic ---
        ip = request.remote_addr
        today = str(datetime.date.today())
        usage = store["usage"].get(ip, {"count": 0, "date": today})

        if not is_pro:
            if usage["date"] != today:
                usage = {"count": 0, "date": today}
            if usage["count"] >= 3:
                return jsonify({"message": "⚠️ Free limit reached. Go Pro for unlimited use."}), 403
            usage["count"] += 1
            store["usage"][ip] = usage
            save_data(store)

        # --- Generate AI output ---
        if action == "analyze":
            prompt = (
                f"Analyze this message:\n"
                f"1. Emotion\n2. Professionalism\n3. Risk Level\n\nMessage:\n{text}"
            )
        elif action == "rewrite":
            prompt = (
                f"Rewrite this message to sound respectful, natural, and clear "
                f"for a {tone} context:\n\n{text}"
            )
        else:
            return jsonify({"error": "Invalid action"}), 400

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
        )
        result = response.choices[0].message.content.strip()
        return jsonify({"rewritten_text": result, "pro": is_pro})

    except Exception as e:
        print("❌ Error:", str(e))
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
