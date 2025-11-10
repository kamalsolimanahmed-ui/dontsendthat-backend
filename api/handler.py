from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os, json, secrets, stripe, datetime
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# -------------------------------------------------------
# SETUP
# -------------------------------------------------------
app = Flask(__name__)

# --- Secure CORS: only your extension + website ---
CORS(app, origins=[
    "chrome-extension://*",         # your Chrome extension
    "https://dontsendthat.com",     # your site (optional)
    "https://dontsendthat-backend-1.onrender.com"  # backend domain
])

# --- Rate limiter (anti-spam) ---
limiter = Limiter(get_remote_address, app=app, default_limits=["30 per minute"])

# --- Stripe Setup ---
stripe.api_key = os.getenv("STRIPE_SECRET", "").strip()
PRICE_ID = os.getenv("STRIPE_PRICE_ID", "").strip()  # keep price ID in Render secrets

# --- OpenAI Setup ---
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

# --- Whitelist ---
WHITELIST = {
    "kamalsolimanahmed@gmail.com",
    "breogan51@hotmail.com"
}

# --- Token storage (still JSON, fine for now) ---
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
# SECURITY: Verify subscription status
# -------------------------------------------------------
def is_subscription_active(token):
    if not token:
        return False

    data = load_data()
    token_info = data["tokens"].get(token)
    if not token_info:
        return False

    email = token_info.get("email", "")
    if email in WHITELIST:
        return True  # free pro

    customer_id = token_info.get("stripe_customer_id")
    if not customer_id:
        return False

    try:
        subs = stripe.Subscription.list(customer=customer_id, status="active", limit=1)
        return len(subs.data) > 0
    except Exception as e:
        print("❌ Stripe check error:", e)
        return False

# -------------------------------------------------------
# ROUTES
# -------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "✅ Secure API running"})

# -------------------------------------------------------
# STRIPE CHECKOUT
# -------------------------------------------------------
@app.route("/create-checkout-session", methods=["POST"])
@limiter.limit("5 per minute")
def create_checkout():
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": PRICE_ID, "quantity": 1}],
            success_url="https://dontsendthat.com/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://dontsendthat.com/cancel",
        )
        return jsonify({"url": session.url})
    except Exception as e:
        print("❌ Stripe error:", str(e))
        return jsonify({"error": "Checkout failed"}), 400

@app.route("/success")
def success():
    session_id = request.args.get("session_id")
    if not session_id:
        return "Missing session ID", 400
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        email = session.get("customer_details", {}).get("email", "")
        cust_id = session.get("customer")
        token = "DST-" + secrets.token_hex(8).upper()

        data = load_data()
        data["tokens"][token] = {
            "email": email,
            "stripe_customer_id": cust_id,
            "created": str(datetime.date.today())
        }
        save_data(data)

        return f"""
        <html><head><title>Payment Success</title></head>
        <body style="font-family:sans-serif;text-align:center;margin-top:80px;">
        <h2>💖 Payment Successful!</h2>
        <p>Your Pro Token:</p>
        <h3 style="background:#eee;padding:10px;border-radius:8px;">{token}</h3>
        <p>Copy this token into your extension.<br><b>Do NOT share it.</b></p>
        </body></html>
        """
    except Exception as e:
        print("❌ Success route error:", str(e))
        return "Internal error", 500

@app.route("/cancel")
def cancel():
    return "<h3>Payment cancelled. You can try again later.</h3>"

# -------------------------------------------------------
# WHITELIST TOKEN
# -------------------------------------------------------
@app.route("/get-whitelist-token", methods=["POST"])
def whitelist_token():
    email = request.json.get("email", "").strip().lower()
    if email not in WHITELIST:
        return jsonify({"error": "Not whitelisted"}), 403

    token = "DST-WL-" + secrets.token_hex(6).upper()
    data = load_data()
    data["tokens"][token] = {
        "email": email,
        "whitelisted": True,
        "created": str(datetime.date.today())
    }
    save_data(data)
    return jsonify({"token": token, "email": email})

# -------------------------------------------------------
# VERIFY TOKEN
# -------------------------------------------------------
@app.route("/verify-token", methods=["POST"])
def verify_token():
    token = request.json.get("token")
    if is_subscription_active(token):
        return jsonify({"valid": True})
    return jsonify({"valid": False}), 403

# -------------------------------------------------------
# AI ENDPOINT (rewrite / analyze)
# -------------------------------------------------------
@app.route("/", methods=["POST"])
@limiter.limit("20 per minute")
def rewrite_text():
    try:
        data = request.get_json(force=True)
        text = data.get("text", "").strip()
        tone = data.get("tone", "general").lower()
        action = data.get("action", "rewrite").lower()
        token = data.get("token")

        if not text:
            return jsonify({"error": "Missing text"}), 400

        data_store = load_data()
        is_pro = is_subscription_active(token)

        # Free-user daily limit (by IP)
        if not is_pro:
            ip = request.remote_addr
            today = str(datetime.date.today())
            usage = data_store["usage"].get(ip, {"count": 0, "date": today})
            if usage["date"] != today:
                usage = {"count": 0, "date": today}
            if usage["count"] >= 2:
                return jsonify({"message": "⚠️ Free limit reached. Upgrade to Pro!"}), 403
            usage["count"] += 1
            data_store["usage"][ip] = usage
            save_data(data_store)

        # Language detection
        detect = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Detect the language name only."},
                {"role": "user", "content": text}
            ],
            max_tokens=10,
        )
        lang = detect.choices[0].message.content.strip()

        # Build prompt
        if action == "analyze":
            prompt = f"Analyze in {lang}:\n1. Emotion\n2. Professionalism\n3. Risk\n\n{text}"
        else:
            prompt = f"Rewrite kindly in {lang}, tone={tone}:\n\n{text}"

        # AI call
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"Reply in {lang}"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
        )

        result = response.choices[0].message.content.strip()
        return jsonify({"rewritten_text": result, "language": lang, "pro": is_pro})

    except Exception as e:
        print("❌ Error:", str(e))
        return jsonify({"error": "Internal server error"}), 500

# -------------------------------------------------------
# MAIN
# -------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
