import os
import requests
from flask import Flask, request, jsonify, render_template_string
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



DASHBOARD_HTML = '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>Miles Dashboard — Daniel Thompson</title>\n<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">\n<style>\n  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }\n\n  :root {\n    --navy: #0B1F3A;\n    --gold: #D4A843;\n    --gold-light: #F0C96A;\n    --teal: #1D9E75;\n    --red: #D85A30;\n    --bg: #0D1520;\n    --surface: #111E2E;\n    --surface2: #162435;\n    --border: rgba(212,168,67,0.15);\n    --text: #E8E4DC;\n    --muted: #7A8A9A;\n  }\n\n  body {\n    font-family: \'Syne\', sans-serif;\n    background: var(--bg);\n    color: var(--text);\n    min-height: 100vh;\n    padding: 0;\n  }\n\n  /* HEADER */\n  .header {\n    background: var(--surface);\n    border-bottom: 1px solid var(--border);\n    padding: 20px 28px;\n    display: flex;\n    justify-content: space-between;\n    align-items: center;\n    position: sticky;\n    top: 0;\n    z-index: 100;\n  }\n  .logo { display: flex; align-items: center; gap: 12px; }\n  .logo-mark {\n    width: 38px; height: 38px;\n    background: var(--gold);\n    border-radius: 10px;\n    display: flex; align-items: center; justify-content: center;\n    font-weight: 800; font-size: 14px; color: var(--navy);\n    letter-spacing: -1px;\n  }\n  .logo-text { font-size: 15px; font-weight: 700; color: var(--text); }\n  .logo-sub { font-size: 11px; color: var(--muted); font-family: \'DM Mono\', monospace; }\n  .header-right { font-family: \'DM Mono\', monospace; font-size: 11px; color: var(--muted); text-align: right; }\n  .live-dot { display: inline-block; width: 7px; height: 7px; background: var(--teal); border-radius: 50%; margin-right: 5px; animation: pulse 2s infinite; }\n  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }\n\n  /* MAIN */\n  .main { padding: 28px; max-width: 1100px; margin: 0 auto; }\n\n  /* LOADING */\n  .loading {\n    display: flex; flex-direction: column; align-items: center; justify-content: center;\n    height: 60vh; gap: 16px;\n  }\n  .spinner {\n    width: 40px; height: 40px;\n    border: 3px solid var(--border);\n    border-top-color: var(--gold);\n    border-radius: 50%;\n    animation: spin 0.8s linear infinite;\n  }\n  @keyframes spin { to { transform: rotate(360deg); } }\n  .loading p { color: var(--muted); font-family: \'DM Mono\', monospace; font-size: 12px; }\n\n  /* ERROR */\n  .error-msg { color: var(--red); font-family: \'DM Mono\', monospace; font-size: 13px; text-align: center; padding: 40px; }\n\n  /* KPI GRID */\n  .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }\n  @media(max-width: 700px) { .kpi-grid { grid-template-columns: repeat(2, 1fr); } }\n\n  .kpi {\n    background: var(--surface);\n    border: 1px solid var(--border);\n    border-radius: 16px;\n    padding: 20px;\n    position: relative;\n    overflow: hidden;\n    animation: fadeUp 0.4s ease both;\n  }\n  .kpi::before {\n    content: \'\';\n    position: absolute;\n    top: 0; left: 0; right: 0;\n    height: 3px;\n    border-radius: 16px 16px 0 0;\n  }\n  .kpi.gold::before { background: var(--gold); }\n  .kpi.teal::before { background: var(--teal); }\n  .kpi.blue::before { background: #378ADD; }\n  .kpi.purple::before { background: #8B5CF6; }\n\n  .kpi-label { font-size: 10px; font-family: \'DM Mono\', monospace; color: var(--muted); letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 10px; }\n  .kpi-value { font-size: 28px; font-weight: 800; color: var(--text); line-height: 1; }\n  .kpi-sub { font-size: 11px; color: var(--muted); margin-top: 6px; font-family: \'DM Mono\', monospace; }\n\n  /* TWO COL */\n  .two-col { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; margin-bottom: 24px; }\n  @media(max-width: 800px) { .two-col { grid-template-columns: 1fr; } }\n\n  /* CARDS */\n  .card {\n    background: var(--surface);\n    border: 1px solid var(--border);\n    border-radius: 16px;\n    padding: 22px;\n    animation: fadeUp 0.5s ease both;\n  }\n  .card-title {\n    font-size: 11px;\n    font-family: \'DM Mono\', monospace;\n    color: var(--muted);\n    letter-spacing: 0.1em;\n    text-transform: uppercase;\n    margin-bottom: 18px;\n    display: flex; align-items: center; gap: 8px;\n  }\n  .card-title span { color: var(--gold); }\n\n  /* LOADS TABLE */\n  .loads-table { width: 100%; border-collapse: collapse; }\n  .loads-table th {\n    font-size: 10px; font-family: \'DM Mono\', monospace;\n    color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em;\n    text-align: left; padding: 0 0 12px 0; border-bottom: 1px solid var(--border);\n  }\n  .loads-table td { padding: 12px 0; border-bottom: 1px solid rgba(255,255,255,0.04); font-size: 13px; }\n  .loads-table tr:last-child td { border-bottom: none; }\n  .route { font-weight: 600; color: var(--text); }\n  .arrow { color: var(--gold); margin: 0 6px; }\n  .broker-tag {\n    font-size: 10px; font-family: \'DM Mono\', monospace;\n    background: rgba(212,168,67,0.1); color: var(--gold);\n    padding: 3px 8px; border-radius: 6px; white-space: nowrap;\n  }\n  .amount { font-weight: 700; color: var(--teal); font-family: \'DM Mono\', monospace; }\n  .miles { color: var(--muted); font-family: \'DM Mono\', monospace; font-size: 12px; }\n  .status-pill {\n    font-size: 10px; padding: 3px 8px; border-radius: 6px;\n    font-family: \'DM Mono\', monospace; white-space: nowrap;\n  }\n  .status-paid { background: rgba(29,158,117,0.15); color: var(--teal); }\n  .status-pending { background: rgba(212,168,67,0.12); color: var(--gold); }\n  .status-overdue { background: rgba(216,90,48,0.15); color: var(--red); }\n\n  /* BROKER BARS */\n  .broker-row { margin-bottom: 16px; }\n  .broker-row:last-child { margin-bottom: 0; }\n  .broker-info { display: flex; justify-content: space-between; margin-bottom: 6px; }\n  .broker-name { font-size: 13px; font-weight: 600; }\n  .broker-amount { font-size: 13px; font-family: \'DM Mono\', monospace; color: var(--gold); }\n  .bar-track { height: 6px; background: rgba(255,255,255,0.06); border-radius: 3px; }\n  .bar-fill { height: 6px; border-radius: 3px; background: linear-gradient(90deg, var(--gold), var(--gold-light)); transition: width 1s ease; }\n\n  /* EXPENSES */\n  .exp-row { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.04); }\n  .exp-row:last-child { border-bottom: none; }\n  .exp-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }\n  .exp-cat { font-size: 13px; flex: 1; }\n  .exp-amt { font-size: 13px; font-family: \'DM Mono\', monospace; font-weight: 500; }\n\n  /* RETIREMENT */\n  .retirement-big { font-size: 36px; font-weight: 800; color: var(--gold); margin-bottom: 4px; }\n  .retirement-sub { font-size: 12px; color: var(--muted); font-family: \'DM Mono\', monospace; margin-bottom: 20px; }\n  .ret-track { height: 12px; background: rgba(255,255,255,0.06); border-radius: 6px; margin-bottom: 8px; overflow: hidden; }\n  .ret-fill { height: 12px; border-radius: 6px; background: linear-gradient(90deg, var(--teal), #2DD4A0); transition: width 1.2s ease; }\n  .ret-labels { display: flex; justify-content: space-between; font-size: 11px; font-family: \'DM Mono\', monospace; color: var(--muted); }\n  .ret-suggestion { margin-top: 18px; background: rgba(29,158,117,0.08); border: 1px solid rgba(29,158,117,0.2); border-radius: 10px; padding: 12px 14px; }\n  .ret-suggestion p { font-size: 12px; color: var(--teal); font-family: \'DM Mono\', monospace; }\n  .ret-suggestion strong { color: var(--text); }\n\n  /* BOTTOM ROW */\n  .bottom-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: 24px; }\n  @media(max-width: 900px) { .bottom-row { grid-template-columns: 1fr; } }\n\n  /* EMPTY STATE */\n  .empty { color: var(--muted); font-size: 13px; font-family: \'DM Mono\', monospace; text-align: center; padding: 20px 0; }\n\n  @keyframes fadeUp {\n    from { opacity: 0; transform: translateY(16px); }\n    to { opacity: 1; transform: translateY(0); }\n  }\n</style>\n</head>\n<body>\n\n<div class="header">\n  <div class="logo">\n    <div class="logo-mark">NN</div>\n    <div>\n      <div class="logo-text">Miles Dashboard</div>\n      <div class="logo-sub">Numda Numda Analytics</div>\n    </div>\n  </div>\n  <div class="header-right">\n    <div><span class="live-dot"></span>Live Data</div>\n    <div id="last-updated">—</div>\n  </div>\n</div>\n\n<div class="main">\n  <div class="loading" id="loading">\n    <div class="spinner"></div>\n    <p>Loading your business data...</p>\n  </div>\n  <div id="dashboard" style="display:none"></div>\n  <div class="error-msg" id="error" style="display:none"></div>\n</div>\n\n<script>\nwindow.SPREADSHEET_ID = "{{ spreadsheet_id }}";\n\nasync function fetchSheet(sheetName) {\n  const id = window.SPREADSHEET_ID;\n  const url = `https://docs.google.com/spreadsheets/d/${id}/gviz/tq?tqx=out:json&sheet=${encodeURIComponent(sheetName)}`;\n  const resp = await fetch(url);\n  const text = await resp.text();\n  const json = JSON.parse(text.match(/google\\.visualization\\.Query\\.setResponse\\(([\\s\\S]*)\\)/)[1]);\n  const rows = json.table.rows || [];\n  const cols = json.table.cols.map(c => c.label);\n  return rows.map(r => {\n    const obj = {};\n    cols.forEach((c, i) => { obj[c] = r.c[i] ? r.c[i].v : \'\'; });\n    return obj;\n  });\n}\n\nfunction fmt(n) {\n  if (!n && n !== 0) return \'$0\';\n  return \'$\' + Number(n).toLocaleString(\'en-US\', {minimumFractionDigits: 0, maximumFractionDigits: 0});\n}\n\nfunction fmtNum(n) {\n  return Number(n || 0).toLocaleString(\'en-US\', {minimumFractionDigits: 0, maximumFractionDigits: 0});\n}\n\nasync function loadDashboard() {\n  try {\n    const [loads, expenses, retirement] = await Promise.allSettled([\n      fetchSheet(\'Loads\'),\n      fetchSheet(\'Expenses\'),\n      fetchSheet(\'Retirement\')\n    ]);\n\n    const loadsData = loads.status === \'fulfilled\' ? loads.value : [];\n    const expensesData = expenses.status === \'fulfilled\' ? expenses.value : [];\n    const retirementData = retirement.status === \'fulfilled\' ? retirement.value : [];\n\n    // KPIs\n    const totalRevenue = loadsData.reduce((s, r) => s + (parseFloat(r.Amount) || 0), 0);\n    const totalMiles = loadsData.reduce((s, r) => s + (parseFloat(r.Miles) || 0), 0);\n    const totalExpenses = expensesData.reduce((s, r) => s + (parseFloat(r.Amount) || 0), 0);\n    const netProfit = totalRevenue - totalExpenses;\n    const avgRate = totalMiles > 0 ? (totalRevenue / totalMiles).toFixed(2) : 0;\n    const totalLoads = loadsData.length;\n\n    // Broker volumes\n    const brokers = {};\n    loadsData.forEach(r => {\n      const b = r.Broker || \'Unknown\';\n      brokers[b] = (brokers[b] || 0) + (parseFloat(r.Amount) || 0);\n    });\n    const brokersSorted = Object.entries(brokers).sort((a,b) => b[1]-a[1]);\n    const maxBroker = brokersSorted[0] ? brokersSorted[0][1] : 1;\n\n    // Expense categories\n    const expCats = {};\n    const expColors = [\'#D4A843\',\'#1D9E75\',\'#378ADD\',\'#8B5CF6\',\'#D85A30\',\'#EC4899\',\'#F59E0B\'];\n    expensesData.forEach(r => {\n      const c = r.Category || \'Other\';\n      expCats[c] = (expCats[c] || 0) + (parseFloat(r.Amount) || 0);\n    });\n    const expSorted = Object.entries(expCats).sort((a,b) => b[1]-a[1]);\n\n    // Retirement\n    const retTotal = retirementData.reduce((s, r) => s + (parseFloat(r[\'Contribution Amount\']) || 0), 0);\n    const retLimit = 23000;\n    const retPct = Math.min((retTotal / retLimit) * 100, 100).toFixed(1);\n    const suggestedRet = Math.min(netProfit * 0.15, 1917).toFixed(0);\n\n    // Recent loads (last 5)\n    const recentLoads = [...loadsData].reverse().slice(0, 5);\n\n    document.getElementById(\'last-updated\').textContent = new Date().toLocaleTimeString();\n\n    const html = `\n      <div class="kpi-grid">\n        <div class="kpi gold">\n          <div class="kpi-label">Gross Revenue</div>\n          <div class="kpi-value">${fmt(totalRevenue)}</div>\n          <div class="kpi-sub">${totalLoads} loads total</div>\n        </div>\n        <div class="kpi teal">\n          <div class="kpi-label">Net Profit</div>\n          <div class="kpi-value">${fmt(netProfit)}</div>\n          <div class="kpi-sub">after ${fmt(totalExpenses)} expenses</div>\n        </div>\n        <div class="kpi blue">\n          <div class="kpi-label">Total Miles</div>\n          <div class="kpi-value">${fmtNum(totalMiles)}</div>\n          <div class="kpi-sub">$${avgRate}/mile avg</div>\n        </div>\n        <div class="kpi purple">\n          <div class="kpi-label">401k Progress</div>\n          <div class="kpi-value">${fmt(retTotal)}</div>\n          <div class="kpi-sub">${retPct}% of $23k limit</div>\n        </div>\n      </div>\n\n      <div class="two-col">\n        <div class="card">\n          <div class="card-title"><span>◈</span> Recent Loads</div>\n          ${recentLoads.length === 0 ? \'<div class="empty">No loads logged yet</div>\' : `\n          <table class="loads-table">\n            <thead>\n              <tr>\n                <th>Route</th>\n                <th>Miles</th>\n                <th>Amount</th>\n                <th>Broker</th>\n                <th>Status</th>\n              </tr>\n            </thead>\n            <tbody>\n              ${recentLoads.map(r => `\n                <tr>\n                  <td><span class="route">${r.Origin || \'—\'}<span class="arrow">→</span>${r.Destination || \'—\'}</span></td>\n                  <td><span class="miles">${fmtNum(r.Miles)}</span></td>\n                  <td><span class="amount">${fmt(r.Amount)}</span></td>\n                  <td><span class="broker-tag">${r.Broker || \'—\'}</span></td>\n                  <td><span class="status-pill ${r[\'Invoice Status\'] === \'Paid\' ? \'status-paid\' : r[\'Invoice Status\'] === \'Overdue\' ? \'status-overdue\' : \'status-pending\'}">${r[\'Invoice Status\'] || \'Pending\'}</span></td>\n                </tr>\n              `).join(\'\')}\n            </tbody>\n          </table>`}\n        </div>\n\n        <div class="card">\n          <div class="card-title"><span>◈</span> Broker Volume</div>\n          ${brokersSorted.length === 0 ? \'<div class="empty">No broker data yet</div>\' : brokersSorted.slice(0, 5).map(([name, amt]) => `\n            <div class="broker-row">\n              <div class="broker-info">\n                <span class="broker-name">${name}</span>\n                <span class="broker-amount">${fmt(amt)}</span>\n              </div>\n              <div class="bar-track">\n                <div class="bar-fill" style="width:${(amt/maxBroker*100).toFixed(1)}%"></div>\n              </div>\n            </div>\n          `).join(\'\')}\n        </div>\n      </div>\n\n      <div class="bottom-row">\n        <div class="card">\n          <div class="card-title"><span>◈</span> Expenses</div>\n          ${expSorted.length === 0 ? \'<div class="empty">No expenses logged yet</div>\' : expSorted.slice(0, 6).map(([cat, amt], i) => `\n            <div class="exp-row">\n              <div class="exp-dot" style="background:${expColors[i % expColors.length]}"></div>\n              <div class="exp-cat">${cat}</div>\n              <div class="exp-amt">${fmt(amt)}</div>\n            </div>\n          `).join(\'\')}\n        </div>\n\n        <div class="card" style="grid-column: span 2">\n          <div class="card-title"><span>◈</span> Solo 401(k) — Retirement</div>\n          <div class="retirement-big">${fmt(retTotal)}</div>\n          <div class="retirement-sub">contributed in 2026</div>\n          <div class="ret-track">\n            <div class="ret-fill" id="ret-bar" style="width:0%"></div>\n          </div>\n          <div class="ret-labels"><span>$0</span><span>${retPct}%</span><span>$23,000</span></div>\n          <div class="ret-suggestion">\n            <p>Suggested this month: <strong>${fmt(suggestedRet)}</strong> — based on 15% of your net profit</p>\n          </div>\n        </div>\n      </div>\n    `;\n\n    document.getElementById(\'dashboard\').innerHTML = html;\n    document.getElementById(\'loading\').style.display = \'none\';\n    document.getElementById(\'dashboard\').style.display = \'block\';\n\n    setTimeout(() => {\n      const bar = document.getElementById(\'ret-bar\');\n      if (bar) bar.style.width = retPct + \'%\';\n    }, 300);\n\n  } catch(e) {\n    document.getElementById(\'loading\').style.display = \'none\';\n    document.getElementById(\'error\').style.display = \'block\';\n    document.getElementById(\'error\').textContent = \'Error loading data: \' + e.message + \'. Make sure your sheet is publicly readable.\';\n  }\n}\n\nloadDashboard();\nsetInterval(loadDashboard, 60000);\n</script>\n</body>\n</html>\n'

@app.route("/dashboard", methods=["GET"])
def dashboard():
    return render_template_string(DASHBOARD_HTML, spreadsheet_id=SPREADSHEET_ID)

@app.route("/", methods=["GET"])
def health_check():
    return "Numda Numda Trucking Assistant is running!", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
