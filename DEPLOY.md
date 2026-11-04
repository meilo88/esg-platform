# ESG 可持续发展报告智能平台 - 公网部署指南 (DEPLOY.md)

本项目已完成线上安全加固、鉴权隔离与容器化适配，支持通过 **GitHub + Zeabur（强烈推荐）** 或 **Render** 实现 0 成本一键云端部署。

---

## 一、为什么首选 Zeabur？

| 对比维度 | Zeabur（首选推荐 ⭐️） | Render（备选） | 传统云服务器 (ECS/CVM) |
| :--- | :--- | :--- | :--- |
| **国内访问速度** | 极快（支持中国香港/亚太节点，免备案） | 较慢（节点在欧美，易受网络波动） | 极快（但需域名 ICP 备案） |
| **服务休眠** | 不休眠（访客随时秒开） | 15分钟无请求自动休眠（冷启动需 50s） | 不休眠 |
| **部署难度** | 0 配置，连接 GitHub 仓库自动构建 Docker | 连接 GitHub 自动构建 Docker | 需手动配 Nginx、SSL、Docker 等 |
| **费用成本** | 提供免费额度，个人演示完全免费 | 基础免费套餐 | 需按月租用服务器（约 30~80元/月） |
| **公网域名** | 自动分配免费 `*.zeabur.app` HTTPS 域名 | 自动分配 `*.onrender.com` 域名 | 需自购域名并完成备案流程 |

---

## 二、关键说明：关于 954MB 报告原版 PDF 的处理

- **数据完整性保障**：项目全部 18 家重点上市公司、35 份报告、**945 项真实指标数值、原文证据披露内容与出处页码** 已完整保存在 `esg_platform.db` (约 335KB) 及 `core/cninfo_seed_reports.json` 中。
- **功能独立性**：网站前端浏览、指标检索、行业排名对比、普通用户纯净数据导出、管理员双工作表底稿导出、AI 在线抽取新报告等**所有核心功能完全基于轻量数据库运行**。
- **避免 GitHub 上传超时**：`esg报告/` 目录存放了 35 份全高清原版 PDF，总大小达 954MB。若一次性 push 到 GitHub，容易因网络缓冲超时 (`RPC failed: HTTP 413`) 失败。
  - **推荐方案（轻量秒级上线）**：将 `esg报告/` 暂存本地或仅保留代表性报告，代码库仅 2MB，推送耗时 3 秒，云端构建 1 分钟即可部署完毕！
  - **全量方案**：若需要云端也支持点击下载 35 份 60MB 的完整原版 PDF，需配置 Git 大文件缓存分批推送，或部署后在 Zeabur 挂载存储卷。

---

## 三、4 步极速上线指南（以 Zeabur 为例）

### 步骤 1：本地初始化 Git 仓库并提交

在终端（或 VSCode/命令行）执行以下命令：

```bash
# 1. 确保在项目根目录 /Users/zhangwei/Desktop/ai竞赛
cd /Users/zhangwei/Desktop/ai竞赛

# 2. 如果未配置过 git 用户信息，先设置一次
git config --global user.name "YourName"
git config --global user.email "your_email@example.com"

# 3. 初始化本地仓库
git init

# 4. 暂存所有代码与数据库（esg_platform.db 会被正常打包）
# （注：如需避免上传 954MB 大 PDF，可先将 esg报告/ 移出或加入 .gitignore）
git add .

# 5. 创建首次提交
git commit -m "feat: complete ESG platform v2.1 ready for cloud deployment"
```

---

### 步骤 2：在 GitHub 上创建仓库并推送

1. 浏览器打开 [https://github.com/new](https://github.com/new) 并登录你的 GitHub 账号。
2. 填写 **Repository name**（例如：`esg-platform`）。
3. 选择 **Private**（私有仓库，防止敏感配置外泄），**不要** 勾选 "Add a README file"、".gitignore" 或 "license"（本地已有）。
4. 点击绿色按钮 **Create repository**。
5. 复制页面给出的推送指令，在本地终端执行：
   ```bash
   git branch -M main
   git remote add origin https://github.com/<你的GitHub用户名>/esg-platform.git
   git push -u origin main
   ```

---

### 步骤 3：在 Zeabur 导入仓库自动部署

1. 浏览器打开 [https://zeabur.com](https://zeabur.com)
2. 点击右上角 **Log in**，选择 **Continue with GitHub** 授权登录。
3. 点击 **「Create Project」（创建新项目）**：
   - 建议节点选择：**Hong Kong（中国香港）** 或 **Singapore（新加坡）**（国内访问延迟低且免备案）。
4. 在项目面板中点击 **「Deploy New Service」（部署服务）** -> 选择 **「Deploy from GitHub」**。
5. 首次使用请点击 **「Configure GitHub App」** 授权 Zeabur 访问你的 `esg-platform` 仓库。
6. 选中 `esg-platform` 仓库，Zeabur 会**自动识别根目录的 Dockerfile** 并开始自动化构建与部署！
   - 构建通常耗时 1~2 分钟，可在页面查看实时构建日志。

---

### 步骤 4：生成免费 HTTPS 公网域名

构建完成且状态显示为 **Running（运行中）** 后：

1. 点击进入该服务卡片，点击顶部的 **「Networking / 网络」** 标签。
2. 在 **Public Networking（公网接入）** 区域，点击 **「Generate Domain」（生成域名）**。
3. 输入你喜欢的前缀（例如：`my-esg-platform`），系统会自动生成一个专属网址：
   ```
   https://my-esg-platform.zeabur.app
   ```
4. **大功告成！** 复制这个链接，在任何手机、平板或外网电脑的浏览器中打开，即可流畅访问并使用！

---

## 四、可选：配置云端环境变量

部署完成后，在 Zeabur 服务的 **「Variables / 环境变量」** 标签页中，可以按需添加以下配置：

| 环境变量名 | 说明 | 默认值 | 示例值 |
| :--- | :--- | :--- | :--- |
| `ADMIN_PASSWORD` | 管理后台登录密码 | `suibe123` | 自定义你的强密码 |
| `LLM_PROVIDER` | 默认大模型通道 | `gemini` | `gemini` 或 `openai` |
| `OPENAI_API_KEY` | DeepSeek / 智谱等兼容 Key | 空 | `sk-xxxxxx` |
| `OPENAI_BASE_URL` | 大模型接口地址 | `https://api.deepseek.com/v1` | `https://api.deepseek.com/v1` |
| `OPENAI_MODEL` | 使用的模型代号 | `deepseek-chat` | `deepseek-chat` |
| `GEMINI_API_KEY` | Google Gemini API Key | 空 | `AIzaSy...` |

> **提示**：即使不配置上述环境变量，管理员上线后也可以直接在网页右上角点击「管理后台」（密码 `suibe123`），在专属面板内随时填写或修改 API Key。

---

## 五、备选方案：Render 平台部署流程

若由于特殊原因希望使用 Render：
1. 访问 [https://render.com](https://render.com) 并用 GitHub 登录。
2. 点击右上角 **New +** -> **Web Service**。
3. 选择连接你的 `esg-platform` GitHub 仓库。
4. 在设置页确认：
   - **Environment / Runtime**: `Docker`
   - **Instance Type**: `Free`
   - **Health Check Path**: `/api/health`
5. 点击最下方的 **Create Web Service**，等待构建完成后，系统会分配一个 `https://xxx.onrender.com` 链接。
