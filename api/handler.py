from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os, json, secrets, stripe, datetime

# -------------------------------------------------------
# INITIAL SETUP
# -------------------------------------------------------
app = Flask(__name__)
CORS(app)

# --- Stripe Setup ---
stripe.api_key = os.getenv("STRIPE_SECRET", "").strip()

PRICE_ID = "price_1SKByAIDtEuyeKmr3ILbytRI"  # ✅ Your Stripe Price ID

# --- OpenAI Setup ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

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
    return jsonify({"message": "✅ API running (Stripe + Token system ready)"})


# -------------------------------------------------------
# STRIPE CHECKOUT FLOW
# -------------------------------------------------------
@app.route("/create-checkout-session", methods=["POST"])
def create_checkout():
    """Creates a Stripe Checkout session"""
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
@app.route("/success")
def success():
    """Stripe redirect → generates Pro token"""
    session_id = request.args.get("session_id")
    if not session_id:
        return "Missing session ID", 400

    session = stripe.checkout.Session.retrieve(session_id)
    email = session.get("customer_details", {}).get("email", "unknown")

    token = "DST-" + secrets.token_hex(4).upper()
    data = load_data()
    data["tokens"][token] = {"email": email, "created": str(datetime.date.today())}
    save_data(data)

    # ✅ Custom success page with auto-redirect
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Payment Successful 💌</title>
        <style>
            body {{
                background: linear-gradient(135deg, #ff66b3, #ff99cc);
                font-family: 'Poppins', sans-serif;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                height: 100vh;
                color: white;
                text-align: center;
            }}
            .card {{
                background: white;
                color: #333;
                border-radius: 16px;
                padding: 40px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                max-width: 400px;
            }}
            h1 {{
                color: #ff4fa3;
                margin-bottom: 10px;
            }}
            .token {{
                background: #f7f7f7;
                border-radius: 10px;
                padding: 10px 20px;
                margin: 15px 0;
                font-weight: bold;
                font-size: 1.1rem;
            }}
            button {{
                background: #ff4fa3;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 10px;
                cursor: pointer;
                font-size: 1rem;
                transition: 0.2s;
            }}
            button:hover {{
                background: #ff2d8b;
            }}
            .redirect {{
                margin-top: 15px;
                font-size: 0.9rem;
                color: #777;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>💖 Payment Successful!</h1>
            <p>Thank you for supporting <b>Don’t Send That</b>.</p>
            <p>Your Pro Token:</p>
            <div class="token">{token}</div>
            <button onclick="copyToken()">Copy Token</button>
            <p class="redirect">Redirecting to your extension in <span id="timer">5</span> seconds…</p>
        </div>

        <script>
            function copyToken() {{
                navigator.clipboard.writeText("{token}");
                alert("✅ Token copied!");
            }}

            // Countdown + redirect
            let seconds = 5;
            const timer = document.getElementById("timer");
            const redirectURL = "chrome-extension://YOUR_EXTENSION_ID/popup.html?token={token}"; 
            // 🔁 Replace with your real Chrome extension or front-end page

            const countdown = setInterval(() => {{
                seconds--;
                timer.textContent = seconds;
                if (seconds <= 0) {{
                    clearInterval(countdown);
                    window.location.href = redirectURL;
                }}
            }}, 1000);
        </script>
    </body>
    </html>
    """


@app.route("/verify-token", methods=["POST"])
def verify_token():
    """Checks if a token is valid"""
    token = request.json.get("token")
    data = load_data()
    if token in data["tokens"]:
        return jsonify({"valid": True})
    return jsonify({"valid": False}), 403


# -------------------------------------------------------
# MAIN REWRITE / ANALYZE ENDPOINT
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

        # --- Load token data ---
        store = load_data()
        is_pro = token in store["tokens"]

        # --- Limit free users ---
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

        # --- Prompt logic ---
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

        # --- OpenAI call ---
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


# -------------------------------------------------------
# MAIN
# -------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
