from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os, json, secrets, stripe, datetime

# -------------------------------------------------------
# SETUP
# -------------------------------------------------------
app = Flask(__name__)
CORS(app)

# --- Stripe Setup ---
stripe.api_key = os.getenv("STRIPE_SECRET", "").strip()
PRICE_ID = "price_1SKBy9IDtEuyeKmrWN1eRvgJ"  # Stripe price ID

# --- OpenAI Setup ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_API_KEY)

# --- Whitelist (Full Access) ---
WHITELIST = {"kamalsolimanahmed@gmail.com", "breogan51@hotmail.com"}

# --- Token Storage ---
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


# -------------------------------------------------------
# ROUTES
# -------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "✅ API running (Stripe + Token + Language ready)"})


# -------------------------------------------------------
# STRIPE CHECKOUT
# -------------------------------------------------------
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
        print("❌ Stripe Error:", str(e))
        return jsonify({"error": str(e)}), 400


@app.route("/success")
def success():
    session_id = request.args.get("session_id")
    if not session_id:
        return "Missing session ID", 400

    session = stripe.checkout.Session.retrieve(session_id)
    email = session.get("customer_details", {}).get("email", "unknown")

    token = "DST-" + secrets.token_hex(4).upper()
    data = load_data()
    data["tokens"][token] = {"email": email, "created": str(datetime.date.today())}
    save_data(data)

    return f"""
    <html>
    <head><title>Payment Successful 💌</title></head>
    <body style="font-family:sans-serif;text-align:center;margin-top:80px;">
        <h1>💖 Payment Successful!</h1>
        <p>Your Pro Token:</p>
        <h3>{token}</h3>
        <p>Copy and paste this into your extension.</p>
    </body>
    </html>
    """


@app.route("/verify-token", methods=["POST"])
def verify_token():
    token = request.json.get("token")
    data = load_data()
    if token in data["tokens"]:
        return jsonify({"valid": True})
    return jsonify({"valid": False}), 403


# -------------------------------------------------------
# MAIN AI ENDPOINT
# -------------------------------------------------------
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

        # --- Whitelist Check ---
        if not is_pro:
            for tdata in store["tokens"].values():
                if tdata.get("email") in WHITELIST:
                    is_pro = True
                    break

        client_ip = request.remote_addr
        if any(
            email in WHITELIST
            for email in [data.get("email", ""), "kamalsolimanahmed@gmail.com", "breogan51@hotmail.com"]
        ) or client_ip.startswith("192.168."):
            is_pro = True

        # --- Limit for Free Users ---
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

        # -------------------------------------------------------
        # Language Detection (auto-respond in same language)
        # -------------------------------------------------------
        detect = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Detect the language of this text and reply only with its name, e.g., English, Spanish, French, Arabic, etc."},
                {"role": "user", "content": text},
            ],
            max_tokens=10,
        )
        lang = detect.choices[0].message.content.strip()

        # -------------------------------------------------------
        # based behavior
        # -------------------------------------------------------
        if action == "analyze":
            prompt = (
                f"Analyze this message in {lang}:\n"
                f"1. Emotion\n2. Professionalism\n3. Risk Level\n\nMessage:\n{text}"
            )
        elif action == "rewrite":
            prompt = (
                f"You are a helpful assistant that rewrites messages in the same language ({lang}). "
                f"Make the tone kind, respectful, and natural for a {tone} context. "
                f"Keep it short and human-sounding.\n\n"
                f"Message:\n{text}"
            )
        else:
            return jsonify({"error": "Invalid action"}), 400

        # -------------------------------------------------------
        #  AI Response
        # -------------------------------------------------------
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"Reply in {lang}. Make sure tone matches {tone} context."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
        )

        result = response.choices[0].message.content.strip()
        return jsonify({"rewritten_text": result, "language": lang, "pro": is_pro})

    except Exception as e:
        print("❌ Error:", str(e))
        return jsonify({"error": str(e)}), 500


# -------------------------------------------------------
# MAIN
# -------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

