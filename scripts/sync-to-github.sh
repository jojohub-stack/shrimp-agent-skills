#!/bin/bash
# 技能文檔 GitHub 同步腳本

set -e

GITHUB_REPO="https://github.com/jojohub-stack/shrimp-agent-skills.git"
SKILLS_DIR="/root/.openclaw/workspace/skills-docs"
BRANCH="master"

echo "🦐 蝦蝦君技能文檔 GitHub 同步"
echo "======================================"
echo ""

cd "$SKILLS_DIR"

# Git 配置
if [ ! -d ".git" ]; then
  git init
  git checkout -b "$BRANCH"
  git config user.email "phrene@github.com"
  git config user.name "Rene (phrene)"
fi

if git remote | grep -q origin; then
  git remote set-url origin "$GITHUB_REPO"
else
  git remote add origin "$GITHUB_REPO"
fi

# 拉取最新變更
git pull origin "$BRANCH" --rebase --strategy-option=theirs 2>/dev/null || echo "⏭️  首次同步"

# 添加檔案
git add -A
echo "📊 檢測到變更："
git status --short

# 提交
if git diff --cached --quiet; then
  echo "✅ 沒有變更，無需提交"
else
  git commit -m "📝 同步技能文檔 $(date +%Y-%m-%d)"
fi

# 推送
git push -u origin "$BRANCH"

echo ""
echo "======================================"
echo "🎉 同步完成！"
echo "======================================"
echo ""
echo "📊 倉庫網址：$GITHUB_REPO"
echo "📈 技能文檔：$(find skills -name "*.md" | wc -l) 個"
echo ""
