import os
import re
import requests
from flask import Flask, request, jsonify, render_template
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
    "When an invoice status changes, send the tag again with the SAME broker and amount as the original load "
    "so the load's status is kept in sync. "

    "When you detect MILEAGE per state for IFTA, include this tag: "
    "[LOG_MILEAGE|state|miles|date] "
    "Example: [LOG_MILEAGE|Tennessee|180|2026-04-20] "

    "When you detect a RETIREMENT contribution or question, include this tag: "
    "[LOG_RETIREMENT|contribution_amount|account_type|notes] "
    "Example: [LOG_RETIREMENT|500|Solo 401k|April contribution] "
    "Account types: Solo 401k, IRA, SEP IRA. "

    "When the user asks for a weekly summary or you are summarizing the week, include this tag: [LOG_WEEKLY|week_start|total_loads|total_miles|gross_revenue|total_expenses|net_profit] Example: [LOG_WEEKLY|2026-04-14|5|1240|6800|1200|5600] Keep responses under 5 sentences. Plain text only, no markdown. "
    "If one message reports several things, include a separate tag for each one — for example two fuel stops "
    "get two [LOG_EXPENSE|...] tags. "
    "Always strip the tags from your visible reply — they are for the system only."
)


LOADS_HEADERS = ["Date", "Origin", "Destination", "Miles", "Amount", "Broker", "Invoice Status"]
INVOICES_HEADERS = ["Date Logged", "Broker", "Amount", "Status", "Load Date"]


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


def to_number(value):
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def numeric(value):
    """Return the value as a number when possible so Sheets stores it numerically."""
    num = to_number(value)
    if num is None:
        return value
    return int(num) if num.is_integer() else num


def same_text(a, b):
    return str(a).strip().lower() == str(b).strip().lower()


def same_amount(a, b):
    na = to_number(a)
    nb = to_number(b)
    if na is None or nb is None:
        return False
    return abs(na - nb) < 0.01


def column_index(header, name):
    """1-based index of a column by header name, or None if absent."""
    for i, label in enumerate(header):
        if same_text(label, name):
            return i + 1
    return None


def cell_value(row, col):
    if not col or len(row) < col:
        return ""
    return row[col - 1]


def match_invoice_row(rows, header, broker, amount, load_date):
    """Find an existing invoice for this broker/amount, newest first.

    Returns (row_number, current_status), or (None, None) when there is no match.
    """
    b_col = column_index(header, "Broker")
    a_col = column_index(header, "Amount")
    d_col = column_index(header, "Load Date")
    s_col = column_index(header, "Status")
    if not b_col or not a_col:
        return None, None
    for index in range(len(rows) - 1, 0, -1):
        row = rows[index]
        if not same_text(cell_value(row, b_col), broker):
            continue
        if not same_amount(cell_value(row, a_col), amount):
            continue
        # A load date on both sides has to agree; a blank on either side is a wildcard.
        row_date = cell_value(row, d_col)
        if load_date and row_date and not same_text(row_date, load_date):
            continue
        return index + 1, cell_value(row, s_col)
    return None, None


def existing_invoice_status(sheet, broker, amount):
    """Status already recorded for a load's invoice, when the invoice was logged first."""
    try:
        ws = sheet.worksheet("Invoices")
    except Exception:
        return None
    rows = ws.get_all_values()
    if len(rows) < 2:
        return None
    _, status = match_invoice_row(rows, rows[0], broker, amount, "")
    return status or None


def update_load_invoice_status(sheet, broker, amount, status, load_date):
    """Push an invoice status onto the Loads row it belongs to."""
    try:
        ws = sheet.worksheet("Loads")
    except Exception:
        return False
    rows = ws.get_all_values()
    if len(rows) < 2:
        return False
    header = rows[0]
    b_col = column_index(header, "Broker")
    a_col = column_index(header, "Amount")
    s_col = column_index(header, "Invoice Status")
    d_col = column_index(header, "Date")
    if not b_col or not a_col or not s_col:
        return False

    matches = []
    for index in range(1, len(rows)):
        row = rows[index]
        if same_text(cell_value(row, b_col), broker) and same_amount(cell_value(row, a_col), amount):
            matches.append(index + 1)
    if not matches:
        return False

    # Same broker and rate can repeat, so prefer the run that matches the load date.
    if load_date and d_col:
        dated = [r for r in matches if same_text(cell_value(rows[r - 1], d_col), load_date)]
        if dated:
            matches = dated

    row_num = matches[-1]
    if same_text(cell_value(rows[row_num - 1], s_col), status):
        return True
    ws.update_cell(row_num, s_col, status)
    return True


def upsert_invoice(ws, broker, amount, status, load_date):
    """Update a matching invoice's status, or append it when it is new."""
    rows = ws.get_all_values()
    header = rows[0] if rows else INVOICES_HEADERS
    row_num, current = match_invoice_row(rows, header, broker, amount, load_date)
    s_col = column_index(header, "Status")
    if row_num and s_col:
        if not same_text(current, status):
            ws.update_cell(row_num, s_col, status)
        return
    ws.append_row([datetime.now().strftime("%Y-%m-%d"), broker, numeric(amount), status, load_date])


def log_load(origin, destination, miles, amount, broker):
    sheet = get_sheet()
    ws = get_or_create_worksheet(sheet, "Loads", LOADS_HEADERS)
    status = "Pending"
    try:
        known = existing_invoice_status(sheet, broker, amount)
        if known:
            status = known
    except Exception as e:
        print("Invoice status lookup error:", e)
    ws.append_row([datetime.now().strftime("%Y-%m-%d"), origin, destination, numeric(miles), numeric(amount), broker, status])


def log_expense(category, amount, notes):
    sheet = get_sheet()
    ws = get_or_create_worksheet(sheet, "Expenses", ["Date", "Category", "Amount", "Notes"])
    ws.append_row([datetime.now().strftime("%Y-%m-%d"), category, numeric(amount), notes])


def log_maintenance(description, cost, mileage):
    sheet = get_sheet()
    ws = get_or_create_worksheet(sheet, "Maintenance", ["Date", "Description", "Cost", "Mileage"])
    ws.append_row([datetime.now().strftime("%Y-%m-%d"), description, numeric(cost), numeric(mileage)])


def log_invoice(broker, amount, status, load_date):
    sheet = get_sheet()
    ws = get_or_create_worksheet(sheet, "Invoices", INVOICES_HEADERS)
    upsert_invoice(ws, broker, amount, status, load_date)
    try:
        update_load_invoice_status(sheet, broker, amount, status, load_date)
    except Exception as e:
        print("Load status update error:", e)


def log_mileage(state, miles, date):
    sheet = get_sheet()
    ws = get_or_create_worksheet(sheet, "Mileage", ["Date", "State", "Miles"])
    ws.append_row([date, state, numeric(miles)])


def log_retirement(contribution, account_type, notes):
    sheet = get_sheet()
    ws = get_or_create_worksheet(sheet, "Retirement", ["Date", "Contribution Amount", "Account Type", "Notes"])
    ws.append_row([datetime.now().strftime("%Y-%m-%d"), numeric(contribution), account_type, notes])


def log_weekly_summary(week_start, total_loads, total_miles, gross_revenue, total_expenses, net_profit):
    sheet = get_sheet()
    ws = get_or_create_worksheet(sheet, "Weekly Summary", ["Week Starting", "Total Loads", "Total Miles", "Gross Revenue", "Total Expenses", "Net Profit"])
    ws.append_row([week_start, numeric(total_loads), numeric(total_miles), numeric(gross_revenue), numeric(total_expenses), numeric(net_profit)])


# tag, expected field count, handler, label for error logs
TAG_HANDLERS = [
    ("[LOG_LOAD|", 5, log_load, "Load"),
    ("[LOG_EXPENSE|", 3, log_expense, "Expense"),
    ("[LOG_MAINTENANCE|", 3, log_maintenance, "Maintenance"),
    ("[LOG_INVOICE|", 4, log_invoice, "Invoice"),
    ("[LOG_MILEAGE|", 3, log_mileage, "Mileage"),
    ("[LOG_RETIREMENT|", 3, log_retirement, "Retirement"),
    ("[LOG_WEEKLY|", 6, log_weekly_summary, "Weekly summary"),
]

TAG_PATTERN = re.compile("|".join(re.escape(tag) + r"[^\]]*\]" for tag, _, _, _ in TAG_HANDLERS))


def extract_tags(reply, tag):
    """Fields for every occurrence of a tag, so one message can log several entries."""
    found = []
    search_from = 0
    while True:
        start = reply.find(tag, search_from)
        if start == -1:
            return found
        end = reply.find("]", start + len(tag))
        if end == -1:
            return found
        found.append(reply[start + len(tag):end].split("|"))
        search_from = end + 1


def strip_tags(reply):
    clean = TAG_PATTERN.sub("", reply)
    clean = re.sub(r"[ \t]{2,}", " ", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    clean = re.sub(r"[ \t]+\n", "\n", clean)
    return clean.strip()


def parse_and_log(reply):
    for tag, field_count, handler, label in TAG_HANDLERS:
        for parts in extract_tags(reply, tag):
            if len(parts) != field_count:
                print(label + " log error: expected " + str(field_count) + " fields, got " + str(len(parts)))
                continue
            try:
                handler(*parts)
            except Exception as e:
                print(label + " log error:", e)

    return strip_tags(reply)


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




@app.route("/dashboard", methods=["GET"])
def dashboard():
    return render_template("dashboard.html", spreadsheet_id=SPREADSHEET_ID)

@app.route("/", methods=["GET"])
def health_check():
    return "Numda Numda Trucking Assistant is running!", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
