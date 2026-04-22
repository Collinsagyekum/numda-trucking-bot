import os
import requests
from flask import Flask, request, jsonify
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread

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
    "Help with load logging, expense logging, maintenance tracking, invoice tracking, mileage logging, retirement contributions, and business summaries. "

    "When you detect a LOAD being logged, include this tag: "
    "[LOG_LOAD|origin|destination|miles|amount|broker] "
    "Example: [LOG_LOAD|Atlanta GA|Charlotte NC|280|1840|Echo Global] "

    "When you detect a FUEL or general EXPENSE, include this tag: "
    "[LOG_EXPENSE|category|amount|notes] "
    "Example: [LOG_EXPENSE|Fuel|180|Memphis TN] "

    "When you detect a MAINTENANCE or REPAIR, include this tag: "
    "[LOG_MAINTENANCE|description|cost|mileage] "
    "Example: [LOG_MAINTENANCE|Tire blowout repair|320|142000] "
    "If mileage is not mentioned use 0. "

    "When you detect an INVOICE update, include this tag: "
    "[LOG_INVOICE|broker|amount|status|load_date] "
    "Example: [LOG_INVOICE|Echo Global|1840|Pending|2026-04-20] "
    "Status can be: Pending, Sent, Paid, Overdue. "

    "When you detect MILEAGE per state for IFTA, include this tag: "
    "[LOG_MILEAGE|state|miles|date] "
    "Example: [LOG_MILEAGE|Tennessee|180|2026-04-20] "

    "When you detect a RETIREMENT contribution or question, include this tag: "
    "[LOG_RETIREMENT|contribution_amount|account_type|notes] "
    "Example: [LOG_RETIREMENT|500|Solo 401k|April contribution] "
    "Account types: Solo 401k, IRA, SEP IRA. "

    "When the user asks for a weekly summary or you are summarizing the week, include this tag: [LOG_WEEKLY|week_start|total_loads|total_miles|gross_revenue|total_expenses|net_profit] Example: [LOG_WEEKLY|2026-04-14|5|1240|6800|1200|5600] Keep responses under 5 sentences. Plain text only, no markdown. "
    "Always strip the tags from your visible reply — they are for the system only."
)


def get_or_create_worksheet(sheet, title, headers):
    try:
        return sheet.worksheet(title)
    except Exception:
        ws = sheet.add_worksheet(title=title, rows=1000, cols=len(headers))
        ws.append_row(headers)
        return ws


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
    sheet = get_sheet()
    ws = get_or_create_worksheet(sheet, "Loads", ["Date", "Origin", "Destination", "Miles", "Amount", "Broker", "Invoice Status"])
    ws.append_row([datetime.now().strftime("%Y-%m-%d"), origin, destination, miles, amount, broker, "Pending"])


def log_expense(category, amount, notes):
    sheet = get_sheet()
    ws = get_or_create_worksheet(sheet, "Expenses", ["Date", "Category", "Amount", "Notes"])
    ws.append_row([datetime.now().strftime("%Y-%m-%d"), category, amount, notes])


def log_maintenance(description, cost, mileage):
    sheet = get_sheet()
    ws = get_or_create_worksheet(sheet, "Maintenance", ["Date", "Description", "Cost", "Mileage"])
    ws.append_row([datetime.now().strftime("%Y-%m-%d"), description, cost, mileage])


def log_invoice(broker, amount, status, load_date):
    sheet = get_sheet()
    ws = get_or_create_worksheet(sheet, "Invoices", ["Date Logged", "Broker", "Amount", "Status", "Load Date"])
    ws.append_row([datetime.now().strftime("%Y-%m-%d"), broker, amount, status, load_date])


def log_mileage(state, miles, date):
    sheet = get_sheet()
    ws = get_or_create_worksheet(sheet, "Mileage", ["Date", "State", "Miles"])
    ws.append_row([date, state, miles])


def log_retirement(contribution, account_type, notes):
    sheet = get_sheet()
    ws = get_or_create_worksheet(sheet, "Retirement", ["Date", "Contribution Amount", "Account Type", "Notes"])
    ws.append_row([datetime.now().strftime("%Y-%m-%d"), contribution, account_type, notes])


def extract_tag(reply, tag):
    if tag not in reply:
        return None
    try:
        start = reply.index(tag) + len(tag)
        end = reply.index("]", start)
        return reply[start:end].split("|")
    except Exception:
        return None


def parse_and_log(reply):
    try:
        parts = extract_tag(reply, "[LOG_LOAD|")
        if parts and len(parts) == 5:
            log_load(parts[0], parts[1], parts[2], parts[3], parts[4])
    except Exception as e:
        print("Load log error:", e)

    try:
        parts = extract_tag(reply, "[LOG_EXPENSE|")
        if parts and len(parts) == 3:
            log_expense(parts[0], parts[1], parts[2])
    except Exception as e:
        print("Expense log error:", e)

    try:
        parts = extract_tag(reply, "[LOG_MAINTENANCE|")
        if parts and len(parts) == 3:
            log_maintenance(parts[0], parts[1], parts[2])
    except Exception as e:
        print("Maintenance log error:", e)

    try:
        parts = extract_tag(reply, "[LOG_INVOICE|")
        if parts and len(parts) == 4:
            log_invoice(parts[0], parts[1], parts[2], parts[3])
    except Exception as e:
        print("Invoice log error:", e)

    try:
        parts = extract_tag(reply, "[LOG_MILEAGE|")
        if parts and len(parts) == 3:
            log_mileage(parts[0], parts[1], parts[2])
    except Exception as e:
        print("Mileage log error:", e)

    try:
        parts = extract_tag(reply, "[LOG_RETIREMENT|")
        if parts and len(parts) == 3:
            log_retirement(parts[0], parts[1], parts[2])
    except Exception as e:
        print("Retirement log error:", e)


    try:
        parts = extract_tag(reply, "[LOG_WEEKLY|")
        if parts and len(parts) == 6:
            log_weekly_summary(parts[0], parts[1], parts[2], parts[3], parts[4], parts[5])
    except Exception as e:
        print("Weekly summary log error:", e)

    clean = reply
    for tag in ["[LOG_LOAD|", "[LOG_EXPENSE|", "[LOG_MAINTENANCE|", "[LOG_INVOICE|", "[LOG_MILEAGE|", "[LOG_RETIREMENT|", "[LOG_WEEKLY|"]:
        if tag in clean:
            start = clean.index(tag)
            end = clean.index("]", start) + 1
            clean = clean[:start].strip() + clean[end:].strip()

    return clean.strip()



def log_weekly_summary(week_start, total_loads, total_miles, gross_revenue, total_expenses, net_profit):
    sheet = get_sheet()
    ws = get_or_create_worksheet(sheet, "Weekly Summary", ["Week Starting", "Total Loads", "Total Miles", "Gross Revenue", "Total Expenses", "Net Profit"])
    ws.append_row([week_start, total_loads, total_miles, gross_revenue, total_expenses, net_profit])

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
            return {"status": "ok"}, 200
        message = value["messages"][0]
        from_phone = message["from"]
        if message["type"] == "text":
            user_text = message["text"]["body"]
            reply = ask_claude(from_phone, user_text)
            send_whatsapp_message(from_phone, reply)
    except Exception as e:
        print("Error:", e)
    return {"status": "ok"}, 200


@app.route("/", methods=["GET"])
def health_check():
    return "Numda Numda Trucking Assistant is running!", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
