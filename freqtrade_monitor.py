import os
import time
import requests
import subprocess
import telebot
from datetime import datetime

# === 配置區 ===
TELEGRAM_TOKEN = "8769502770:AAFwYb5aSSe5tYOekICeAvWSPFa-gEt-dfs"
CHAT_ID = "770325907"
FREQTRADE_API_URL = "http://172.18.0.2:8080/api/v1"
API_USER = "admin"
API_PASS = "admin66" 

# 讀取環境變數（wrapper 會 source /home/ubuntu/.secrets_freqtrade）
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
# 若要使用本地 ollama，設定以下環境變數或使用預設值
OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'gemma4:e4b')  # switch to smaller model by default for testing
# 風控與推薦閾值（可用環境變數覆寫）
TAKE_PROFIT_PCT = float(os.environ.get('TAKE_PROFIT_PCT', '2.0'))   # 正向利潤到達此百分比建議了結
STOP_LOSS_PCT = float(os.environ.get('STOP_LOSS_PCT', '-3.0'))      # 負向虧損到達此百分比建議停止並出場
SCALE_IN_PCT = float(os.environ.get('SCALE_IN_PCT', '-1.5'))       # 小幅回撤到達此百分比建議加碼（視情況）


# 初始本金會自動讀取：
# 1) 若 freqtrade config.json 設定 dry_run 且包含 dry_run_wallet，使用該值（最早預設為 500）
# 2) 否則嘗試讀取 balance API 的 total 作為初始金額
# 3) 首次取得後會寫入 /home/ubuntu/openclaw_workspace/initial_capital.json 作為持久值
INITIAL_CAPITAL_FILE = '/home/ubuntu/openclaw_workspace/initial_capital.json'

import os, json

def load_initial_capital(api_url=None, auth=None):
    # 1. try freqtrade config dry_run_wallet
    try:
        cfg = json.load(open('/freqtrade/user_data/config.json'))
        if cfg.get('dry_run') and 'dry_run_wallet' in cfg:
            val = float(cfg.get('dry_run_wallet') or 0)
            # persist
            try:
                os.makedirs(os.path.dirname(INITIAL_CAPITAL_FILE), exist_ok=True)
                json.dump({'initial_capital': val}, open(INITIAL_CAPITAL_FILE, 'w'))
            except Exception:
                pass
            return val
    except Exception:
        pass

    # 2. try reading persisted file
    try:
        if os.path.exists(INITIAL_CAPITAL_FILE):
            d = json.load(open(INITIAL_CAPITAL_FILE))
            return float(d.get('initial_capital') or 0)
    except Exception:
        pass

    # 3. fallback: query balance API
    if api_url and auth:
        try:
            r = requests.get(f"{api_url}/balance", auth=auth, timeout=10).json()
            val = float(r.get('total') or 0)
            try:
                os.makedirs(os.path.dirname(INITIAL_CAPITAL_FILE), exist_ok=True)
                json.dump({'initial_capital': val}, open(INITIAL_CAPITAL_FILE, 'w'))
            except Exception:
                pass
            return val
        except Exception:
            pass

    # final fallback
    return 0.0

# END initial capital loader

# 讀取初始本金（若無則預設 500）
INITIAL_CAPITAL = load_initial_capital(api_url=FREQTRADE_API_URL, auth=(API_USER, API_PASS))
if not INITIAL_CAPITAL or INITIAL_CAPITAL <= 0:
    INITIAL_CAPITAL = 500.0

bot = telebot.TeleBot(TELEGRAM_TOKEN)

def get_ai_analysis(capital, current, daily, float_p, trades_str):
    """呼叫 AI 大腦產生戰術分析：優先使用雲端（若設定 CLOUD_PROVIDER=google），否則使用本地 ollama，最後回退到 rules-only。"""
    prompt = f"""初始本金: {capital} USDT
當前淨值: {current} USDT
今日利潤: {daily} USDT
當前浮動: {float_p}%
近期交易紀錄:
{trades_str}"""

    system_msg = "你是一個冷靜的加密貨幣量化交易戰術官。請根據提供的本金、獲利與近期交易數據，給出50字以內的繁體中文操作建議與市場狀態評估。語氣要專業、果斷。"

    # 若配置使用雲端模型（例如 Google Gemma 4）
    cloud_provider = os.environ.get('CLOUD_PROVIDER')
    cloud_key = os.environ.get('CLOUD_API_KEY')
    # 預設使用 Google Gemma-4 A4B，可由環境變數 CLOUD_MODEL 覆寫
    cloud_model = os.environ.get('CLOUD_MODEL', 'google/gemma-4-26b-a4b-it')

    # Normalize model identifiers into a form usable in the Generative Language API URL.
    # Accepts: 'google/gemma-...', 'gemma-...', 'models/gemma-...', or full 'projects/.../models/...'
    def _normalize_model(m: str) -> str:
        if not m:
            return m
        m = m.strip()
        if m.startswith('projects/') or m.startswith('models/'):
            return m
        if m.startswith('google/'):
            return 'models/' + m.split('/', 1)[1]
        return 'models/' + m.lstrip('/')

    # prefer Hermes gpt-5-mini via local helper; fall back to cloud -> local ollama
    try:
        helper = os.path.expanduser('~/.hermes/ai/generate_with_gpt5.py')
        if os.path.exists(helper) and os.access(helper, os.X_OK):
            p = subprocess.run([helper], input=prompt.encode(), capture_output=True, timeout=60)
            if p.returncode == 0 and p.stdout:
                return p.stdout.decode().strip()
            else:
                # try cloud afterwards
                pass
    except Exception as e:
        print('gpt-5-mini helper failed, fallback to cloud:', e)

    if cloud_provider and cloud_provider.lower() == 'google' and cloud_key and cloud_model:
        try:
            # Prefer the openai-compatible chat completions endpoint which works for Gemma in our tests
            model_resource = _normalize_model(cloud_model)
            chat_url = 'https://generativelanguage.googleapis.com/v1beta/chat/completions'
            payload = {
                'model': model_resource,
                'messages': [
                    {'role': 'system', 'content': system_msg},
                    {'role': 'user', 'content': prompt}
                ],
                'temperature': 0.2,
                'max_tokens': 256
            }
            headers = {'Authorization': f'Bearer {cloud_key}', 'Content-Type': 'application/json'}
            r = requests.post(chat_url, json=payload, headers=headers, timeout=30)
            if r.status_code == 200:
                j = r.json()
                text = None
                # Robust parsing for known response shapes
                try:
                    if isinstance(j, dict) and 'choices' in j and len(j['choices']) > 0:
                        first = j['choices'][0]
                        # new-style: first.message.content (could be string or list)
                        if isinstance(first.get('message'), dict):
                            msg = first['message']
                            cont = msg.get('content') or msg.get('text')
                            if isinstance(cont, str):
                                text = cont
                            elif isinstance(cont, list) and len(cont) > 0:
                                # join text parts or pick 'text'/'output_text'
                                parts = []
                                for itm in cont:
                                    if isinstance(itm, dict):
                                        if itm.get('type') in ('output_text', 'text') and itm.get('text'):
                                            parts.append(str(itm.get('text')))
                                    elif isinstance(itm, str):
                                        parts.append(itm)
                                text = ''.join(parts) if parts else None
                        # legacy: choices[0].text
                        if not text and first.get('text'):
                            text = first.get('text')
                    # fallback other fields
                    if not text:
                        if isinstance(j, dict):
                            cand = j.get('candidates') or j.get('output') or []
                            if isinstance(cand, list) and len(cand) > 0:
                                for c in cand:
                                    if isinstance(c, dict):
                                        if 'content' in c and isinstance(c['content'], list):
                                            for itm in c['content']:
                                                if isinstance(itm, dict) and itm.get('type') in ('output_text','text'):
                                                    text = itm.get('text')
                                                    break
                                        if not text and 'text' in c:
                                            text = c.get('text')
                                        if text:
                                            break
                except Exception:
                    text = None
                if not text:
                    # last resort: raw response body
                    try:
                        text = r.text
                    except Exception:
                        text = None
                if text:
                    return text.strip()
                else:
                    return '雲端 AI 回傳格式不明，略過 AI 分析。'
            else:
                # let caller fallback to local ollama
                print(f'Cloud AI 連線失敗 (狀態碼: {r.status_code}), body: {r.text[:200]}')
        except Exception as e:
            print('Cloud AI failed, fallback to local:', e)

    # 若未使用或雲端失敗，呼叫本地 ollama (原本流程)
    try:
        api_url = OLLAMA_URL.rstrip('/') + '/api/generate'
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 256,
            "temperature": 0.2
        }
        max_attempts = 5
        backoff_seconds = [2, 4, 8, 16, 30]
        attempt = 0
        while attempt < max_attempts:
            try:
                r = requests.post(api_url, json=payload, timeout=60)
            except requests.exceptions.Timeout:
                if attempt < max_attempts - 1:
                    time.sleep(backoff_seconds[min(attempt, len(backoff_seconds)-1)])
                    attempt += 1
                    continue
                return '本地 AI 正忙碌或正在載入模型，略過 AI 分析。'
            except Exception as e:
                return f'AI 模組異常: {str(e)}'

            text = None
            try:
                j = r.json()
            except Exception:
                j = None

            done_reason = None
            if isinstance(j, dict):
                done_reason = j.get('done_reason') or j.get('status') or j.get('done')
            if (isinstance(j, dict) and (j.get('response') == '' or done_reason == 'load')) or (r.status_code == 200 and j is None and not r.text.strip()):
                if attempt < max_attempts - 1:
                    time.sleep(backoff_seconds[min(attempt, len(backoff_seconds)-1)])
                    attempt += 1
                    continue
                else:
                    return '本地 AI 正在載入模型，暫時無法提供分析，戰報已送出。'

            if r.status_code != 200:
                return f"AI 連線失敗 (狀態碼: {r.status_code})"

            if isinstance(j, dict):
                if 'choices' in j and len(j['choices']) > 0:
                    try:
                        text = j['choices'][0].get('message', {}).get('content') or j['choices'][0].get('text')
                    except Exception:
                        text = None
                if not text and 'response' in j:
                    text = j.get('response')
                if not text and 'completion' in j:
                    text = j.get('completion')
                if not text and 'output' in j:
                    out = j.get('output')
                    if isinstance(out, list):
                        text = ''.join([str(x) for x in out])
                    else:
                        text = str(out)
            if not text:
                try:
                    text = r.text
                except:
                    text = None

            if text:
                return text.strip()
            else:
                if attempt < max_attempts - 1:
                    time.sleep(backoff_seconds[min(attempt, len(backoff_seconds)-1)])
                    attempt += 1
                    continue
                return 'AI 回傳格式不明或無內容，請檢查本地 ollama 狀態。'
    except Exception as e:
        return f'AI 模組異常: {str(e)}' 
def get_freqtrade_status():
    try:
        auth = (API_USER, API_PASS)
        
        # 1. 抓取當前交易狀態 (計算浮動)
        status_data = requests.get(f"{FREQTRADE_API_URL}/status", auth=auth, timeout=10).json()
        
        # 2. 抓取今日獲利
        profit_data = requests.get(f"{FREQTRADE_API_URL}/daily?last_days=1", auth=auth, timeout=10).json()
        
        # 3. 抓取帳戶餘額 (計算淨值)
        try:
            balance_data = requests.get(f"{FREQTRADE_API_URL}/balance", auth=auth, timeout=10).json()
            # 取出錢包總價值
            current_capital = balance_data.get('total', INITIAL_CAPITAL) 
        except:
            current_capital = INITIAL_CAPITAL

        # 4. 抓取歷史交易紀錄 (取最後5筆)
        trades_data = requests.get(f"{FREQTRADE_API_URL}/trades", auth=auth, timeout=10).json()
        last_5_trades = trades_data.get('trades', [])[-5:]

        now = datetime.now().strftime("%m/%d %H:%M")
        
        # --- 數據計算 ---
        total_unrealized_pct = 0
        trade_count = len(status_data) if status_data else 0
        
        if status_data:
            for trade in status_data:
                total_unrealized_pct += float(trade.get('current_profit_pct', 0)) * 100
        avg_float_pct = (total_unrealized_pct / trade_count) if trade_count > 0 else 0.0
        
        day_profit = 0.0
        if profit_data and 'data' in profit_data and len(profit_data['data']) > 0:
            day_profit = float(profit_data['data'][0].get('abs_profit', 0))

        # --- 組合最新5筆交易文字 ---
        trades_str = ""
        if last_5_trades:
            for i, t in enumerate(last_5_trades, 1):
                pair = t.get('pair', 'Unknown').replace('/USDT', '')
                status = "🟢 進行中" if t.get('is_open') else "已平倉"
                profit = float(t.get('profit_abs', 0))
                icon = "🟢" if profit >= 0 else "🔴"
                trades_str += f"{i}. {icon} {pair} | {status} | 獲利: {profit:+.2f} USDT\n"
        else:
            trades_str = "目前無近期交易紀錄\n"

        # --- 組合目前持倉摘要 (top 5 by 持倉金額或浮動) ---
        holdings_str = ""
        open_trades = [t for t in status_data if t.get('is_open')]
        if open_trades:
            # 依未實現損益絕對值排序，取前5
            sorted_trades = sorted(open_trades, key=lambda x: abs(float(x.get('profit_abs') or 0)), reverse=True)
            top = sorted_trades[:5]
            for i, t in enumerate(top, 1):
                pair = t.get('pair', 'Unknown')
                profit_pct = t.get('profit_pct') if t.get('profit_pct') is not None else t.get('current_profit_pct')
                profit_abs = t.get('profit_abs') if t.get('profit_abs') is not None else t.get('total_profit_abs')
                current_rate = t.get('current_rate') or t.get('open_rate')
                amount = t.get('amount') or t.get('stake_amount')
                holdings_str += f"{i}. {pair} | 當前報酬: {float(profit_pct or 0):+.2f}% | 未實現: {float(profit_abs or 0):+.2f} USDT | 價格: {current_rate} | 數量: {amount}\n"
            if len(open_trades) > 5:
                holdings_str += f"... +{len(open_trades)-5} 筆持倉未列出\n"
        else:
            holdings_str = "目前無持倉\n"

        # --- 呼叫 5-mini AI 大腦 (把持倉摘要也傳給 AI) ---
        ai_input = trades_str + "\n持倉摘要:\n" + holdings_str
        ai_msg = get_ai_analysis(INITIAL_CAPITAL, current_capital, day_profit, avg_float_pct, ai_input)

        # --- 建立結構化建議並寫入 actions log（供 manager 讀取） ---
        try:
            actions_log_path = '/home/ubuntu/openclaw_workspace/grid_actions.log'
            try:
                import yaml
                cfgp = '/home/ubuntu/openclaw_workspace/grid_config.yaml'
                if os.path.exists(cfgp):
                    cfg = yaml.safe_load(open(cfgp))
                    actions_log_path = cfg.get('logging', {}).get('actions_log', actions_log_path)
            except Exception:
                pass

            suggestion = ai_decision_wrapper(ai_msg, holdings_str)
            action_entry = {
                'time': datetime.utcnow().isoformat() + 'Z',
                'type': 'ai_suggestion',
                'ai_text': ai_msg,
                'suggestion': suggestion,
                'holdings_preview': holdings_str[:1000]
            }
            try:
                with open(actions_log_path, 'a') as af:
                    af.write(json.dumps(action_entry, ensure_ascii=False) + "\n")
            except Exception:
                pass
        except Exception:
            pass

        # --- 組裝 HTML 報表 ---
        human_suggestion = ''
        try:
            human_suggestion = f"建議: {suggestion.get('action')}，說明: {suggestion.get('reason')}（可信度 {suggestion.get('confidence'):.2f}）"
        except Exception:
            human_suggestion = ''

        # 為避免 Telegram HTML parse error，對使用者輸入原文進行 HTML escape
        try:
            import html as _html
            safe_trades = _html.escape(trades_str)
            safe_holdings = _html.escape(holdings_str)
            safe_ai_msg = _html.escape(ai_msg)
            safe_human_suggestion = _html.escape(human_suggestion)
        except Exception:
            safe_trades = trades_str
            safe_holdings = holdings_str
            safe_ai_msg = ai_msg
            safe_human_suggestion = human_suggestion

        html_message = f"""📊 <b>Freqtrade 戰略簡報</b>
📅 報告時間: {now}

💰 <b>資金水位監控</b>
• 初始本金: {INITIAL_CAPITAL:.2f} USDT
• 當前淨值: {current_capital:.2f} USDT
• 今日利潤: {day_profit:+.2f} USDT
• 浮動盈虧: {avg_float_pct:+.2f}%

🛒 <b>最新交易動態（近期）</b>
{safe_trades}

📦 <b>目前持倉摘要（Top 5）</b>
{safe_holdings}

🤖 <b>AI 戰術官分析</b>
🧠 <i>{safe_ai_msg}</i>

📌 <b>結構化建議（Rules + AI）</b>
{safe_human_suggestion}
"""
        
        # 發送 Telegram (使用 HTML 模式)
        bot.send_message(CHAT_ID, html_message, parse_mode="HTML")
        print(f"[{now}] AI 戰報發送成功")

    except Exception as e:
        print(f"錯誤內容: {e}")
        # 發生錯誤時依然嘗試發送警告
        try:
            bot.send_message(CHAT_ID, f"⚠️ <b>戰報系統異常</b>\n錯誤代碼: <code>{e}</code>", parse_mode="HTML")
        except:
            pass

if __name__ == "__main__":
    get_freqtrade_status()
