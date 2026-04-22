import requests, telebot, html
from datetime import datetime, timezone, timedelta

# ==========================================
# ⚙️ 核心配置 (專為本機 Local 部署設定，破解 Cron 環境變數遺失問題)
# ==========================================
TOKEN = "8565218972:AAHHtiSWajDx8yuE3Rej2NbCYGPMBD5tf6Y"
CHAT_ID = "770325907"
FREQTRADE_API = "http://127.0.0.1:18081/api/v1" # 已修正為你的 18081 Port
bot = telebot.TeleBot(TOKEN)

# 寫死 Agent 洩漏的本機帳密，確保 API 通關
API_USER = "admin"
API_PASS = "admin66"
auth = requests.auth.HTTPBasicAuth(API_USER, API_PASS)

# ==========================================
# 🛡️ 數據解析模組 (Agent 的強健邏輯)
# ==========================================
def fetch_api(endpoints, params=None):
    if isinstance(endpoints, str): endpoints = [endpoints]
    for ep in endpoints:
        try:
            r = requests.get(f"{FREQTRADE_API}/{ep}", auth=auth, params=params, timeout=10)
            if r.status_code == 200: return r.json()
        except Exception as e: 
            pass
    return None

def extract_list(data):
    """撥開 Freqtrade API 的外皮，取出陣列"""
    if isinstance(data, list): return data
    if isinstance(data, dict):
        for k in ['trades', 'data', 'results', 'items']:
            if isinstance(data.get(k), list): return data[k]
    return []

def run():
    tw_now = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime('%m/%d %H:%M')
    
    # 1. 抓取 API 數據
    balance_data = fetch_api(['balance', 'balances', 'account/balance']) or {}
    profit_data = fetch_api(['profit']) or {}
    daily_data = fetch_api(['daily'], params={'timescale': '1d'}) or {}
    open_trades_raw = fetch_api(['status', 'open_trades']) or []
    closed_trades_raw = fetch_api(['trades']) or {}

    # 2. 深度解析數據
    # -- 淨值 (Current Equity) --
    current_equity = float(balance_data.get("total") or balance_data.get("total_usd") or balance_data.get("equity") or 0.0)
    if current_equity == 0.0 and "currencies" in balance_data:
        current_equity = sum(float(c.get("est_stake", 0) or c.get("stake_value", 0)) for c in balance_data["currencies"])

    # -- 利潤 (Total Profit) --
    total_profit = float(profit_data.get("profit_all_coin", 0.0))
    if total_profit == 0.0 and "profit" in profit_data:
        total_profit = float(profit_data.get("profit", 0.0))
        
    starting_cap = current_equity - total_profit if current_equity > 0 else 0.0
    
    # -- 今日利潤 (Daily Profit) --
    daily_list = extract_list(daily_data)
    daily_profit = float(daily_list[0].get("abs_profit", 0.0)) if daily_list else 0.0

    # -- 浮動盈虧 (Floating PnL) --
    open_trades = extract_list(open_trades_raw)
    float_profit = sum(float(t.get("profit_abs", 0.0)) for t in open_trades)
    float_pct = (float_profit / starting_cap * 100) if starting_cap > 0 else 0.0

    # 3. 組合最新交易動態 (近期平倉 Top 5)
    closed_list = extract_list(closed_trades_raw)
    closed_list = sorted(closed_list, key=lambda x: x.get("close_timestamp", 0) or x.get("close_date", ""), reverse=True)[:5]
    
    recent_history_str = ""
    for i, t in enumerate(closed_list, 1):
        pair = t.get("pair", "N/A").split('/')[0] # 簡化名稱
        p_abs = float(t.get("profit_abs") or t.get("profit") or 0.0)
        emoji = "🟢" if p_abs >= 0 else "🔴"
        recent_history_str += f"{i}. {emoji} {pair} | 已平倉 | 獲利: {p_abs:+.2f} USDT\n"
    if not recent_history_str: recent_history_str = "無近期交易紀錄\n"

    # 4. 組合目前持倉摘要 (Top 5)
    open_trades = sorted(open_trades, key=lambda x: float(x.get("profit_ratio", 0) or x.get("profit_pct", 0))) 
    open_holdings_str = ""
    for i, t in enumerate(open_trades[:5], 1):
        pair = t.get("pair", "N/A")
        p_pct = float(t.get("profit_ratio", 0.0) or t.get("profit_pct", 0.0)) * 100
        p_abs = float(t.get("profit_abs", 0.0) or t.get("profit_fiat_abs", 0.0))
        price = t.get("current_rate", 0.0)
        amt = t.get("amount", 0.0)
        open_holdings_str += f"{i}. {pair} | 當前報酬: {p_pct:+.2f}% | 未實現: {p_abs:+.2f} USDT | 價格: {price} | 數量: {amt}\n"
    
    hidden_count = len(open_trades) - 5
    if hidden_count > 0:
        open_holdings_str += f"... +{hidden_count} 筆持倉未列出\n"
    elif not open_holdings_str:
        open_holdings_str = "目前空手，無持倉\n"

    # 5. AI 戰術分析
    try:
        ai_input = f"淨值 {current_equity:.2f}, 浮動盈虧 {float_pct:.2f}%, 今日利潤 {daily_profit:.2f}"
        url = 'http://127.0.0.1:11434/api/generate'
        prompt = f"你是冷酷的加密貨幣交易官。依據以下 Freqtrade 數據：{ai_input}。給出 50 字以內的戰術研判，禁止廢話與英文。"
        r = requests.post(url, json={'model': 'phi4-mini:latest', 'prompt': prompt, 'stream': False}, timeout=15)
        ai_msg = r.json().get('response', '').strip()
    except:
        ai_msg = "🧠 本地 AI 正在載入模型，暫時無法提供分析，戰報已送出。"

    # 6. 渲染 UI 報表
    report = f"📊 <b>Freqtrade 戰略簡報</b>\n"
    report += f"📅 報告時間: {tw_now}\n"
    report += "━━━━━━━━━━━━━━━━\n"
    report += "💰 <b>資金水位監控</b>\n"
    report += f"• 初始本金: {starting_cap:.2f} USDT\n"
    report += f"• 當前淨值: {current_equity:.2f} USDT\n"
    report += f"• 今日利潤: {daily_profit:+.2f} USDT\n"
    report += f"• 浮動盈虧: {float_pct:+.2f}%\n\n"

    report += "🛒 <b>最新交易動態 ( 近期 )</b>\n"
    report += f"{recent_history_str}\n"

    report += "📦 <b>目前持倉摘要 ( Top 5 )</b>\n"
    report += f"{open_holdings_str}\n"

    report += "🤖 <b>AI 戰術官分析</b>\n"
    report += f"<i>{html.escape(ai_msg)}</i>\n\n"

    report += "📌 <b>結構化建議 ( Rules + AI )</b>\n"
    report += "• 嚴守網格與停損紀律，等待市場訊號。"

    # 7. 發送至 Telegram
    try:
        bot.send_message(CHAT_ID, report, parse_mode="HTML")
        print(f"[{tw_now}] 戰報發送成功 (Port 18081)")
    except Exception as e:
        print(f"發送失敗: {e}")

if __name__ == "__main__":
    run()
