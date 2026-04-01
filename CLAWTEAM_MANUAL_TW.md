# 🦞 ClawTeam 使用手冊

> **多智能體群組協調系統** - 適用於 CLI 編碼智能體

<p align="center">
  <a href="#-快速入門">快速入門</a> |
  <a href="#-安裝">安裝</a> |
  <a href="#-核心概念">核心概念</a> |
  <a href="#-常用命令">常用命令</a> |
  <a href="#-進階功能">進階功能</a> |
  <a href="#-故障排除">故障排除</a>
</p>

---

## 🎯 簡介

ClawTeam 是一個強大的**多智能體協調框架**，讓 AI 智能體能夠自組織成團隊，自動分工、溝通與協作，無需人工微管理。

### 為什麼選擇 ClawTeam？

| 特性 | ClawTeam | 其他多智能體框架 |
|------|----------|------------------|
| **使用者** | AI 智能體自主使用 | 人工編寫協調代碼 |
| **設置** | `pip install` + 一個提示 | Docker、雲端 API、YAML 配置 |
| **基礎設施** | 檔案系統 + tmux | Redis、訊息隊列、資料庫 |
| **智能體支援** | 任何 CLI 智能體 | 僅框架專用 |
| **隔離** | Git 工作樹（真實分支） | 容器或虛擬環境 |

---

## 🚀 快速入門

### 選項 1：讓智能體自主駕駛（推薦）

安裝 ClawTeam 後，直接對您的智能體下達指令：

```
「建立一個網路應用程式。使用 clawteam 將工作分割給多個智能體。」
```

智能體會自動：
1. 創建團隊
2. 生成任務
3. 產生工作者智能體
4. 協調整個過程

### 選項 2：手動控制

```bash
# 創建團隊
clawteam team spawn-team my-team -d "建立認證模組" -n leader

# 產生工作者 - 每個工作者獲得獨立的 git 工作樹和 tmux 視窗
clawteam spawn --team my-team --agent-name alice --task "實作 OAuth2 流程"
clawteam spawn --team my-team --agent-name bob   --task "編寫單元測試"

# 監控進度
clawteam board attach my-team
```

---

## 📦 安裝

### 先決條件

- **Python 3.10+**
- **tmux**
- 至少一個 CLI 編碼智能體（OpenClaw、Claude Code、Codex 等）

```bash
# 檢查現有工具
python3 --version   # 需要 3.10+
tmux -V             # 需要任何版本
openclaw --version  # 或 claude --version / codex --version
```

### 安裝 ClawTeam

> **重要**：請勿使用 `pip install clawteam` - 這會安裝上游版本。請從此倉庫安裝。

```bash
git clone https://github.com/win4r/ClawTeam-OpenClaw.git
cd ClawTeam-OpenClaw
pip install -e .
```

### 可選 - P2P 傳輸（ZeroMQ）

```bash
pip install -e ".[p2p]"
```

### 步驟 3：創建 `~/bin/clawteam` 符號連結

```bash
mkdir -p ~/bin
ln -sf "$(which clawteam)" ~/bin/clawteam
```

### 步驟 4：安裝 OpenClaw 技能（僅限 OpenClaw 用戶）

```bash
mkdir -p ~/.openclaw/workspace/skills/clawteam
cp skills/openclaw/SKILL.md ~/.openclaw/workspace/skills/clawteam/SKILL.md
```

### 步驟 5：配置執行許可（僅限 OpenClaw 用戶）

```bash
# 確保安全模式為「允許清單」
python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.openclaw' / 'exec-approvals.json'
if p.exists():
    d = json.loads(p.read_text())
    d.setdefault('defaults', {})['security'] = 'allowlist'
    p.write_text(json.dumps(d, indent=2))
    print('exec-approvals.json 已更新：security = allowlist')
else:
    print('exec-approvals.json 未找到 - 請先執行 openclaw 一次')
"

# 將 clawteam 加入允許清單
openclaw approvals allowlist add --agent "*" "*/clawteam"
```

### 驗證

```bash
clawteam --version          # 應顯示版本
clawteam config health      # 應顯示所有綠色
```

---

## 🧠 核心概念

### 1. 團隊結構

```
您（人類）
   │
   ▼
┌──────────────────┐
│  領導智能體      │  ← 使用 clawteam CLI 協調
│  （任何智能體）  │
└────────┬─────────┘
         │
         ├──────────────────► ┌─────────────────┐
         │                    │  工作者智能體   │
         │                    │  git 工作樹     │
         │                    │  tmux 視窗      │
         ├──────────────────► ├─────────────────┤
         │                    │  工作者智能體   │
         └──────────────────► └─────────────────┘
                                  所有智能體透過
                                  ~/.clawteam/ 協調
```

### 2. 工作區隔離

每個智能體獲得獨立的 **git 工作樹**，避免平行開發時的合併衝突。

### 3. 任務追蹤

- 共享看板：`pending` → `in_progress` → `completed` / `blocked`
- 依賴鏈：`--blocked-by` 會在完成時自動解除阻塞
- `task wait` 會阻塞直到所有任務完成

### 4. 智能體間訊息

- 點對點收件匣（發送、接收、偷看）
- 廣播給所有團隊成員
- 基於檔案（預設）或 ZeroMQ P2P 傳輸

---

## 🔧 常用命令

### 團隊管理

```bash
# 創建團隊
clawteam team spawn-team <團隊名稱> -d "描述" -n <領導者名稱>

# 列出所有團隊
clawteam team discover

# 顯示團隊成員
clawteam team status <團隊名稱>

# 產生智能體
clawteam spawn --team <團隊名稱> --agent-name <名稱> --task "執行此任務"

# 監控進度
clawteam board show <團隊名稱>        # 終端機看板
clawteam board live <團隊名稱>        # 自動刷新
clawteam board attach <團隊名稱>      # 平鋪 tmux 視圖
clawteam board serve --port 8080      # 網路 UI
```

### 任務管理

```bash
# 創建任務
clawteam task create <團隊名稱> "主題" -o <擁有者> --blocked-by <id1>,<id2>

# 更新任務狀態
clawteam task update <團隊名稱> <id> --status completed

# 列出任務
clawteam task list <團隊名稱> --status blocked --owner worker1

# 等待任務完成
clawteam task wait <團隊名稱> --timeout 300
```

### 訊息傳遞

```bash
# 發送訊息
clawteam inbox send <團隊名稱> <接收者> "訊息內容"

# 廣播訊息
clawteam inbox broadcast <團隊名稱> "訊息內容"

# 接收訊息（消耗）
clawteam inbox receive <團隊名稱>

# 偷看訊息（不消耗）
clawteam inbox peek <團隊名稱>
```

---

## 🚀 進階功能

### 1. 團隊範本

使用 TOML 檔案定義團隊原型：

```bash
# 使用範本啟動團隊
clawteam launch <範本名稱> --team <團隊名稱> --goal "建立 X"

# 列出可用範本
clawteam template list
```

### 2. 工作區管理

```bash
# 列出工作區
clawteam workspace list <團隊名稱>

# 检查點（自動提交）
clawteam workspace checkpoint <團隊名稱> <智能體名稱>

# 合併回主分支
clawteam workspace merge <團隊名稱> <智能體名稱>

# 清理工作區
clawteam workspace cleanup <團隊名稱> <智能體名稱>
```

### 3. 生命週期管理

```bash
# 要求關閉
clawteam lifecycle request-shutdown <團隊名稱> <智能體名稱> --reason "完成"

# 批准關閉
clawteam lifecycle approve-shutdown <團隊名稱> <請求id> <智能體名稱>

# 設定閒置狀態
clawteam lifecycle idle <團隊名稱>
```

---

## 🐛 故障排除

| 問題 | 可能原因 | 解決方案 |
|------|----------|----------|
| `clawteam: command not found` | pip bin 目錄不在 PATH 中 | 執行步驟 3（創建符號連結 + PATH） |
| 產生的智能體找不到 `clawteam` | 智能體在新的 shell 中執行，沒有 pip PATH | 驗證 `~/bin/clawteam` 符號連結存在且 `~/bin` 在 PATH 中 |
| `openclaw approvals` 失敗 | 閘道未執行 | 先啟動 `openclaw gateway`，然後重試步驟 5 |
| `exec-approvals.json` 未找到 | OpenClaw 從未執行 | 執行 `openclaw` 一次以生成配置，然後重試步驟 5 |
| 智能體阻塞在許可提示 | 執行許可安全性為「完整」 | 執行步驟 5 切換到「允許清單」 |
| `pip install -e .` 失敗 | 缺少構建依賴 | 先執行 `pip install hatchling` |

---

## 📚 使用案例

### 1. 自主機器學習研究

```bash
# 一個提示啟動 8 個研究智能體
clawteam launch ml-research --team research1 --goal "優化 train.py"
```

### 2. 智能體軟體工程

```bash
# 建立全端 todo 應用程式
clawteam launch webapp --team todo-team --goal "建立帶有認證、資料庫和 React 前端的全端 todo 應用程式"
```

### 3. AI 對沖基金範本

```bash
# 使用範本啟動完整的 7 智能體投資團隊
clawteam launch hedge-fund --team fund1 --goal "分析 2026 年第二季度的 AAPL、MSFT、NVDA"
```

---

## 🔄 更新與維護

### 更新 ClawTeam

```bash
cd ClawTeam-OpenClaw
git pull origin main
pip install -e . --upgrade
```

### 定期維護

1. 清理舊的工作區：
   ```bash
   clawteam workspace cleanup <團隊名稱> <智能體名稱>
   ```

2. 更新技能（僅限 OpenClaw）：
   ```bash
   cp skills/openclaw/SKILL.md ~/.openclaw/workspace/skills/clawteam/SKILL.md
   ```

3. 檢查新版本：
   ```bash
   clawteam --version
   ```

---

## 📖 進階閱讀

- [官方文檔](https://github.com/win4r/ClawTeam-OpenClaw)
- [上游專案](https://github.com/HKUDS/ClawTeam)
- [OpenClaw 整合](https://openclaw.ai)
- [自動研究框架](https://github.com/karpathy/autoresearch)

---

## 🎯 最佳實踐

1. **從小開始**：先測試小團隊（2-3 個智能體）
2. **明確任務**：提供具體、可操作的目標
3. **監控進度**：使用 `board live` 追蹤進展
4. **定期检查點**：使用 `workspace checkpoint` 保存進度
5. **清理資源**：完成後清理工作區和團隊

---

<div align="center">

**ClawTeam** — *智能體群組智慧。*

</div>
<environment_details>
# Visual Studio Code Visible Files
browser-use/.env

# Visual Studio Code Open Tabs
../../home/ubuntu/hourly_oraclaw_report.sh
../../home/ubuntu/daily_claw_check.sh
../../home/ubuntu/freqtrade_monitor_report.sh
../../home/ubuntu/.openclaw/agents/my-pal/agent.json
../../home/ubuntu/.openclaw/agents/my-pal/pal_agent.py
../../home/ubuntu/.openclaw/workspace/skills/agent-office/package.json
../../home/ubuntu/.config/systemd/user/agent-office.service
task_progress.md
../../home/ubuntu/.openclaw/workspace/skills/agent-office/server.cjs
../../home/ubuntu/.openclaw/workspace/skills/agent-office/public/index.html
package.json
run_snyk.sh
openclaw_daily_trend_summary.py
../../home/ubuntu/.openclaw/workspace/skills/stock-tw-analyzer/package.json
../../home/ubuntu/.openclaw/workspace/skills/crypto-analyzer/package.json
../../home/ubuntu/.openclaw/workspace/skills/crypto-analyzer/main.py
browser-use/login_google_totp.py
browser-use/fetch_trending_social.py
../../home/ubuntu/browser-trigger/trigger_api.py
../../home/ubuntu/browser-trigger/visit_x_com.py
browser-use/Dockerfile
../../home/ubuntu/ai_workspace/test_browser.py
../../home/ubuntu/ai_workspace/news_scraper.py
../../home/ubuntu/ai_workspace/xcom_scraper.py
../../home/ubuntu/.openclaw/workspace/skills/stock-tw-analyzer/main.py
../../home/ubuntu/.openclaw/workspace/memory/2026-04-01.md
qrcode.png
get_totp.py
2330_report.png
chart.png
debug_login.png
full_page.png
fetch_xcom_headlines.py
browser-use/visit_x_com.py
browser-use/test_xcom_crawler.py
browser-use/test_threads_crawler.py
browser-use/visit_threads_com.py
browser-use/test_llama3_model.py
browser-use/fetch_tw_trending.py
browser-use/.env

# Current Time
4/1/2026, 3:19:01 PM (Asia/Taipei, UTC+8:00)

# Context Window Usage
33,431 / 256K tokens used (13%)

# Context Window Usage
33,431 / 256K tokens used (13%)

# Current Mode
ACT MODE
</environment_details>