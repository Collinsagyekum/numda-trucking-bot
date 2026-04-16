import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "numdanumda2026")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

conversation_history = {}

SYSTEM_PROMPT = (
    "You are Miles, a smart trucking business assistant built by Numda Numda Analytics. "
    "You help Daniel Thompson manage his trucking business through WhatsApp. "
    "Be friendly, concise, and professional. Daniel is busy on the road so keep responses short. "
    "Help with load logging, expense logging, business summaries, invoice status, retirement reminders, tax reminders. "
    "When logging a load confirm with: Route, Miles, Amount, Broker, Invoice Pending. "
    "When logging an expense confirm with: Category and Amount. "
    "Keep responses under 5 sentences unless giving a summary. Plain text only, no markdown."
)


def ask_claude(user_phone, user_message):
    if user_phone not in conversation_history:
        conversation_history[user_phone] = []
    conversation_history[user_phone].append({"role": "user", "content": user_message})
    messages = conversation_history[user_phone][-20:]
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1000,
        "system": SYSTEM_PROMPT,
        "messages": messages
    }
    resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
    data = resp.json()
    reply = data["content"][0]["text"]
    conversation_history[user_phone].append({"role": "assistant", "content": reply})
    return reply


def send_whatsapp_message(to_phone, message):
    url = "https://graph.facebook.com/v18.0/" + PHONE_NUMBER_ID + "/messages"
    headers = {"Authorization": "Bearer " + WHATSAPP_TOKEN, "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to_phone, "type": "text", "text": {"body": message}}
    requests.post(url, headers=headers, json=payload)


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()
    try:
        value = data["entry"][0]["changes"][0]["value"]
        if "messages" not in value:
            return jsonify({"status": "ok"}), 200
        message = value["messages"][0]
        from_phone = message["from"]
        if message["type"] == "text":
            user_text = message["text"]["body"]
            reply = ask_claude(from_phone, user_text)
            send_whatsapp_message(from_phone, reply)
    except Exception as e:
        print("Error:", e)
    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET"])
def health_check():
    return "Numda Numda Trucking Assistant is running!", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
