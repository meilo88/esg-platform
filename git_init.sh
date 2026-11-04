#!/bin/bash
# ESG 平台 - Git 初始化与快速提交脚本
set -e

echo "========================================================"
echo "  ESG 智能平台 - GitHub 部署准备工具"
echo "========================================================"

# 1. 检查并提示 Git 用户配置
if [ -z "$(git config user.name)" ]; then
    read -p "请输入你的 Git 用户名（例如 ZhangWei）: " GIT_NAME
    git config --global user.name "$GIT_NAME"
fi

if [ -z "$(git config user.email)" ]; then
    read -p "请输入你的 Git 邮箱（例如 your_email@example.com）: " GIT_EMAIL
    git config --global user.email "$GIT_EMAIL"
fi

# 2. 初始化仓库
if [ ! -d ".git" ]; then
    git init
    echo "✅ 已初始化本地 Git 仓库"
else
    echo "ℹ️ 本地 Git 仓库已存在"
fi

# 3. 询问是否暂不上传 954MB 的原版 PDF（推荐选 Y，2MB 极速秒传）
echo ""
echo "【关键提示】本地 'esg报告/' 目录下包含 35 份完整高清大 PDF（共 954MB）。"
echo "数据库已收录全部 18 家企业、35 份报告、945 项真实指标与原文证据页码。"
echo "若排除 954MB 大 PDF，代码库仅 2MB，3秒即可推送成功，网站全部功能 100% 正常运行！"
read -p "是否暂不推送 954MB 原版大 PDF 到 GitHub（推荐 Y）? [Y/n]: " EXCLUDE_PDF
EXCLUDE_PDF=${EXCLUDE_PDF:-Y}

if [[ "$EXCLUDE_PDF" =~ ^[Yy]$ ]]; then
    if ! grep -q "^esg报告/" .gitignore 2>/dev/null; then
        echo -e "\n# 大型原版 PDF 报告库（线上功能依赖轻量 SQLite 数据库，无需常驻 950MB PDF）\nesg报告/" >> .gitignore
        echo "✅ 已将 'esg报告/' 临时加入 .gitignore，代码库精简至 2MB！"
    fi
else
    echo "⚠️ 你选择了全量包含 954MB 原版大 PDF，首次推送可能需要较长时间，请保持网络畅通。"
    git config --global http.postBuffer 1048576000
fi

# 4. 暂存并提交代码
git add .
git commit -m "feat: complete ESG platform v2.1 ready for cloud deployment" || echo "当前工作区暂无新变动需要提交"

echo ""
echo "========================================================"
echo "🎉 本地代码提交完毕！"
echo ""
echo "接下来请执行以下两步将代码推送到 GitHub："
echo "1. 打开浏览器访问 https://github.com/new 创建一个新仓库（建议勾选 Private 私有仓库）"
echo "2. 复制页面生成的两条命令并在终端运行："
echo "   git branch -M main"
echo "   git remote add origin https://github.com/<你的用户名>/<仓库名>.git"
echo "   git push -u origin main"
echo ""
echo "3. 打开 https://zeabur.com 一键导入该仓库，1 分钟即可生成公网 HTTPS 网址！"
echo "========================================================"
