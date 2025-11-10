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
PRICE_ID = "price_1SKBy9IDtEuyeKmrWN1eRvgJ"  

# --- OpenAI Setup ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_API_KEY)

# --- Whitelist (Emails that get FREE Pro access) ---
WHITELIST = {
    "kamalsolimanahmed@gmail.com",
    "breogan51@hotmail.com"
}

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
# SECURITY FIX: Check if Stripe subscription is ACTIVE
# -------------------------------------------------------
def is_subscription_active(token):
    """Check if token's subscription is still active with Stripe"""
    if not token:
        return False
        
    data = load_data()
    
    if token not in data["tokens"]:
        return False
    
    token_info = data["tokens"][token]
    
    # CHECK WHITELIST: If email is whitelisted, give Pro for free
    email = token_info.get("email", "")
    if email in WHITELIST:
        return True  # Whitelisted = Free Pro!
    
    stripe_customer_id = token_info.get("stripe_customer_id")
    
    if not stripe_customer_id:
        return False
    
    try:
        # Check Stripe for active subscriptions
        subscriptions = stripe.Subscription.list(
            customer=stripe_customer_id,
            status='active',
            limit=1
        )
        
        # If they have an active subscription, they're Pro
        return len(subscriptions.data) > 0
        
    except Exception as e:
        print(f"❌ Stripe check error: {e}")
        return False


# -------------------------------------------------------
# ROUTES
# -------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "✅ API running (SECURE version)"})


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

    try:
        session = stripe.checkout.Session.retrieve(session_id)
        email = session.get("customer_details", {}).get("email", "unknown")
        customer_id = session.get("customer")  # CRITICAL: Get Stripe customer ID
        
        token = "DST-" + secrets.token_hex(8).upper()
        
        data = load_data()
        # SECURITY FIX: Store Stripe customer ID with token
        data["tokens"][token] = {
            "email": email,
            "stripe_customer_id": customer_id,  # IMPORTANT!
            "created": str(datetime.date.today())
        }
        save_data(data)

        return f"""
        <html>
        <head><title>Payment Successful 💌</title></head>
        <body style="font-family:sans-serif;text-align:center;margin-top:80px;">
            <h1>💖 Payment Successful!</h1>
            <p>Your Pro Token:</p>
            <h3 style="background:#f0f0f0;padding:15px;border-radius:10px;">{token}</h3>
            <p>Copy and paste this into your extension.</p>
            <p style="color:red;"><strong>⚠️ Keep this token private! Do not share!</strong></p>
        </body>
        </html>
        """
    except Exception as e:
        return f"Error: {str(e)}", 500


@app.route("/cancel")
def cancel():
    return """
    <html>
    <head><title>Payment Cancelled</title></head>
    <body style="font-family:sans-serif;text-align:center;margin-top:80px;">
        <h1>Payment Cancelled</h1>
        <p>You can try again anytime!</p>
    </body>
    </html>
    """


# -------------------------------------------------------
# WHITELIST: Generate free token for whitelisted emails
# -------------------------------------------------------
@app.route("/get-whitelist-token", methods=["POST"])
def get_whitelist_token():
    """Generate a free Pro token for whitelisted emails"""
    email = request.json.get("email", "").strip().lower()
    
    if email not in WHITELIST:
        return jsonify({"error": "Email not whitelisted"}), 403
    
    # Generate token
    token = "DST-WL-" + secrets.token_hex(6).upper()
    
    data = load_data()
    data["tokens"][token] = {
        "email": email,
        "stripe_customer_id": None,  # No Stripe for whitelist
        "whitelisted": True,
        "created": str(datetime.date.today())
    }
    save_data(data)
    
    return jsonify({
        "token": token,
        "email": email,
        "message": "Free Pro token generated!"
    })


# -------------------------------------------------------
# SECURITY FIX: Verify token AND subscription status
# -------------------------------------------------------
@app.route("/verify-token", methods=["POST"])
def verify_token():
    token = request.json.get("token")
    
    # Check if token exists AND subscription is active
    if is_subscription_active(token):
        return jsonify({"valid": True})
    
    return jsonify({"valid": False}), 403


# -------------------------------------------------------
# MAIN AI ENDPOINT (SECURED)
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
        
        # SECURITY FIX: Check if token has ACTIVE subscription
        is_pro = is_subscription_active(token)

        # --- Limit for Free Users ---
        if not is_pro:
            ip = request.remote_addr
            today = str(datetime.date.today())
            usage = store["usage"].get(ip, {"count": 0, "date": today})

            # Reset count if new day
            if usage["date"] != today:
                usage = {"count": 0, "date": today}
            
            # Check limit (2 messages per day for free users)
            if usage["count"] >= 2:
                return jsonify({
                    "message": "⚠️ Free limit reached (2 messages/day). Upgrade to Pro for unlimited!"
                }), 403
            
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
        # Action-based behavior
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
        # Get AI Response
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
