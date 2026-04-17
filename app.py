import os
import json
import requests
import gspread
from datetime import datetime
from flask import Flask, request, jsonify
from google.oauth2.service_account import Credentials

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "numdanumda2026")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "")
GOOGLE_CLIENT_EMAIL = os.environ.get("GOOGLE_CLIENT_EMAIL", "")
GOOGLE_PRIVATE_KEY = os.environ.get("GOOGLE_PRIVATE_KEY", "").replace("\\n", "\n")

conversation_history = {}

SYSTEM_PROMPT = (
    "You are Miles, a smart trucking business assistant built by Numda Numda Analytics. "
    "You help Daniel Thompson manage his trucking business through WhatsApp. "
    "Be friendly, concise, and professional. Daniel is busy on the road so keep responses short. "
    "Help with load logging, expense logging, business summaries, invoice status, retirement reminders, tax reminders. "
    "When you detect a load being logged, always include this exact tag at the end of your response: "
    "[LOG_LOAD|origin|destination|miles|amount|broker] "
    "For example: [LOG_LOAD|Atlanta GA|Charlotte NC|280|1840|Echo Global] "
    "When you detect an expense being logged, include this tag: "
    "[LOG_EXPENSE|category|amount] "
    "For example: [LOG_EXPENSE|Fuel|180] "
    "Keep responses under 5 sentences. Plain text only, no markdown."
)


def get_sheet():
    creds_dict = {
        "type": "service_account",
        "client_email": GOOGLE_CLIENT_EMAIL,
        "private_key": GOOGLE_PRIVATE_KEY,
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID)


def log_load(origin, destination, miles, amount, broker):
    try:
        sheet = get_sheet()
        worksheet = sheet.worksheet("Loads")
    except Exception:
        sheet = get_sheet()
        worksheet = sheet.add_worksheet(title="Loads", rows=1000, cols=8)
        worksheet.append_row(["Date", "Origin", "Destination", "Miles", "Amount", "Broker", "Invoice Status"])
    worksheet.append_row([
        datetime.now().strftime("%Y-%m-%d"),
        origin, destination, miles, amount, broker, "Pending"
    ])


def log_expense(category, amount):
    try:
        sheet = get_sheet()
        worksheet = sheet.worksheet("Expenses")
    except Exception:
        sheet = get_sheet()
        worksheet = sheet.add_worksheet(title="Expenses", rows=1000, cols=4)
        worksheet.append_row(["Date", "Category", "Amount"])
    worksheet.append_row([
        datetime.now().strftime("%Y-%m-%d"),
        category, amount
    ])


def parse_and_log(reply):
    if "[LOG_LOAD|" in reply:
        try:
            tag = reply[reply.index("[LOG_LOAD|")+10:reply.index("]", reply.index("[LOG_LOAD|"))]
            parts = tag.split("|")
            if len(parts) == 5:
                log_load(parts[0], parts[1], parts[2], parts[3], parts[4])
        except Exception as e:
            print("Load log error:", e)

    if "[LOG_EXPENSE|" in reply:
        try:
            tag = reply[reply.index("[LOG_EXPENSE|")+13:reply.index("]", reply.index("[LOG_EXPENSE|"))]
            parts = tag.split("|")
            if len(parts) == 2:
                log_expense(parts[0], parts[1])
        except Exception as e:
            print("Expense log error:", e)

    clean_reply = reply
    for tag in ["[LOG_LOAD|", "[LOG_EXPENSE|"]:
        if tag in clean_reply:
            start = clean_reply.index(tag)
            end = clean_reply.index("]", start) + 1
            clean_reply = clean_reply[:start].strip() + clean_reply[end:].strip()

    return clean_reply


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
    clean_reply = parse_and_log(reply)
    conversation_history[user_phone].append({"role": "assistant", "content": clean_reply})
    return clean_reply


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
