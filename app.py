import json
import logging
import os
import re
import secrets
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import quote

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
from core.extractor import ESGExtractor
from core.exporter import ExcelExporter
from core.llm_client import LLMClient
from core.database import get_db_connection, init_db, seed_initial_data, INDICATOR_META
from core.annotation_manager import AnnotationManager
from core.muse_sync import sync_muse_inbox

logger = logging.getLogger("esg_platform")

# 确保数据库已初始化，并自动同步 muse_inbox/ 中的新增 Excel/JSON 抽取成果
init_db()
seed_initial_data()
sync_muse_inbox()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
OUTPUT_DIR = BASE_DIR / "output"
REPORTS_DIR = BASE_DIR / "esg报告"
GITHUB_RAW_PDF_BASE = os.environ.get(
    "GITHUB_RAW_PDF_BASE",
    "https://raw.githubusercontent.com/meilo88/esg-platform/main/esg%E6%8A%A5%E5%91%8A"
)
STORAGE_DIR = BASE_DIR / "storage"
TEMP_UPLOADS_DIR = STORAGE_DIR / "temp_uploads"
ADMIN_WORKPAPER_DIR = STORAGE_DIR / "admin_workpapers"
LLM_CONFIG_PATH = STORAGE_DIR / "llm_config.json"
ADMIN_SESSIONS_PATH = STORAGE_DIR / "admin_sessions.json"

for _d in (OUTPUT_DIR, REPORTS_DIR, STORAGE_DIR, TEMP_UPLOADS_DIR, ADMIN_WORKPAPER_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ==================== 持久化大模型配置加载与保存 ====================
def _write_secure_json(path: Path, data: Dict[str, Any]):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except Exception:
        pass
    tmp.replace(path)


def load_persisted_llm_config():
    """启动时加载管理员持久化的模型配置（若存在）"""
    if not LLM_CONFIG_PATH.is_file():
        return
    try:
        cfg = json.loads(LLM_CONFIG_PATH.read_text(encoding="utf-8"))
        if cfg.get("provider"):
            config.DEFAULT_PROVIDER = cfg["provider"]
        if cfg.get("gemini_api_key"):
            config.GEMINI_API_KEY = cfg["gemini_api_key"]
        if cfg.get("gemini_model"):
            config.GEMINI_MODEL = cfg["gemini_model"]
        if cfg.get("openai_api_key"):
            config.OPENAI_API_KEY = cfg["openai_api_key"]
        if cfg.get("openai_model"):
            config.OPENAI_MODEL = cfg["openai_model"]
        if cfg.get("openai_base_url"):
            config.OPENAI_BASE_URL = cfg["openai_base_url"]
    except Exception as e:
        logger.warning("读取持久化模型配置失败: %s", e)


def save_persisted_llm_config():
    _write_secure_json(LLM_CONFIG_PATH, {
        "provider": config.DEFAULT_PROVIDER,
        "gemini_api_key": config.GEMINI_API_KEY,
        "gemini_model": config.GEMINI_MODEL,
        "openai_api_key": config.OPENAI_API_KEY,
        "openai_model": config.OPENAI_MODEL,
        "openai_base_url": config.OPENAI_BASE_URL,
    })


load_persisted_llm_config()


# ==================== 临时文件自动过期清理机制 ====================
def cleanup_stale_files(max_age_seconds: int = 7200):
    """自动清理超过 2 小时的临时导出表格与管理员暂存上传文件，防止线上磁盘占满"""
    now = time.time()
    for folder in (OUTPUT_DIR, TEMP_UPLOADS_DIR, ADMIN_WORKPAPER_DIR):
        if not folder.exists():
            continue
        for item in folder.iterdir():
            if item.name.startswith(".") or not item.is_file():
                continue
            try:
                if now - item.stat().st_mtime > max_age_seconds:
                    item.unlink(missing_ok=True)
            except Exception:
                pass


# ==================== 管理员安全鉴权、会话持久化与防爆破体系 ====================
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "suibe123")
ACTIVE_ADMIN_TOKENS: Dict[str, float] = {}  # token -> expire_timestamp
FAILED_LOGIN_ATTEMPTS: Dict[str, List[float]] = {}  # client_ip -> [failure_timestamps]
ANALYZE_RATE_BUCKETS: Dict[str, List[float]] = {}  # client_ip -> [request_timestamps]


def _load_admin_sessions():
    if ADMIN_SESSIONS_PATH.is_file():
        try:
            raw = json.loads(ADMIN_SESSIONS_PATH.read_text(encoding="utf-8"))
            now = time.time()
            for tok, exp in raw.items():
                if isinstance(exp, (int, float)) and exp > now:
                    ACTIVE_ADMIN_TOKENS[tok] = float(exp)
        except Exception:
            pass


def _save_admin_sessions():
    now = time.time()
    valid = {k: v for k, v in ACTIVE_ADMIN_TOKENS.items() if v > now}
    ACTIVE_ADMIN_TOKENS.clear()
    ACTIVE_ADMIN_TOKENS.update(valid)
    try:
        _write_secure_json(ADMIN_SESSIONS_PATH, valid)
    except Exception:
        pass


_load_admin_sessions()


def get_client_ip(request: Optional[Request]) -> str:
    if request is None:
        return "127.0.0.1"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "127.0.0.1"


def check_login_rate_limit(ip: str) -> bool:
    """风控：5 分钟内最多尝试 5 次密码，超出即锁定"""
    now = time.time()
    recent = [t for t in FAILED_LOGIN_ATTEMPTS.get(ip, []) if now - t < 300]
    FAILED_LOGIN_ATTEMPTS[ip] = recent
    return len(recent) >= 5


def record_login_failure(ip: str):
    now = time.time()
    recent = [t for t in FAILED_LOGIN_ATTEMPTS.get(ip, []) if now - t < 300]
    recent.append(now)
    FAILED_LOGIN_ATTEMPTS[ip] = recent


def check_analyze_rate_limit(ip: str) -> bool:
    """公网防刷保护：单个访客 IP 在 5 分钟内最多发起 10 次 PDF 智能抽取"""
    now = time.time()
    recent = [t for t in ANALYZE_RATE_BUCKETS.get(ip, []) if now - t < 300]
    if len(recent) >= 10:
        ANALYZE_RATE_BUCKETS[ip] = recent
        return True
    recent.append(now)
    ANALYZE_RATE_BUCKETS[ip] = recent
    return False


def verify_token(token: Optional[str]) -> bool:
    if not token:
        return False
    now = time.time()
    exp = ACTIVE_ADMIN_TOKENS.get(token)
    if not exp and ADMIN_SESSIONS_PATH.is_file():
        _load_admin_sessions()
        exp = ACTIVE_ADMIN_TOKENS.get(token)
    if exp and exp > now:
        return True
    if exp:
        ACTIVE_ADMIN_TOKENS.pop(token, None)
        _save_admin_sessions()
    return False


def extract_token_from_request(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    header_val = request.headers.get("X-Admin-Token")
    if header_val:
        return header_val.strip()
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return None


def require_admin(request: Request, query_token: Optional[str] = None):
    token = query_token or extract_token_from_request(request)
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="未授权：此操作仅限管理员，请先登录管理后台")


# 生产环境隐藏默认 Swagger 文档暴露（可通过 ENABLE_DOCS=1 开启）
_enable_docs = os.getenv("ENABLE_DOCS", "0") == "1"
app = FastAPI(
    title="可持续发展报告指标平台",
    description="基于沪深北交易所可持续发展报告指引，提供上市公司核心定量指标检索、趋势对比与AI智能抽取",
    version="2.1.0",
    docs_url="/docs" if _enable_docs else None,
    redoc_url="/redoc" if _enable_docs else None,
)

_allowed_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False if _allowed_origins == ["*"] else True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Token"],
)


@app.middleware("http")
async def add_security_and_cache_headers(request: Request, call_next):
    response = await call_next(request)
    # 生产级安全响应头
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


class AdminLoginModel(BaseModel):
    password: str


class SettingsModel(BaseModel):
    provider: str
    api_key: Optional[str] = ""
    model: Optional[str] = None
    base_url: Optional[str] = None


# ==================== 健康检查 API（供云平台负载均衡探测） ====================
@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "version": "2.1.0"}


# ==================== 管理员鉴权与会话 API ====================
@app.post("/api/admin/login")
async def admin_login(payload: AdminLoginModel, request: Request):
    ip = get_client_ip(request)
    if check_login_rate_limit(ip):
        raise HTTPException(status_code=429, detail="安全风控拦截：密码错误次数过多，请 5 分钟后再试")

    submitted = (payload.password or "").strip()
    if not secrets.compare_digest(submitted, ADMIN_PASSWORD):
        record_login_failure(ip)
        raise HTTPException(status_code=401, detail="管理密码错误，无法进入管理后台")

    FAILED_LOGIN_ATTEMPTS.pop(ip, None)

    token = secrets.token_hex(32)
    ACTIVE_ADMIN_TOKENS[token] = time.time() + 86400  # 24小时有效
    _save_admin_sessions()
    return {"status": "ok", "token": token, "message": "管理员鉴权成功", "expires_in": 86400}


@app.post("/api/admin/logout")
async def admin_logout(request: Request):
    token = extract_token_from_request(request)
    if token and token in ACTIVE_ADMIN_TOKENS:
        del ACTIVE_ADMIN_TOKENS[token]
        _save_admin_sessions()
    return {"status": "ok", "message": "已成功退出管理员工作台"}


@app.get("/api/admin/verify")
async def admin_verify_status(request: Request):
    token = extract_token_from_request(request)
    return {"is_admin": verify_token(token)}


@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(
            content=index_file.read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-cache, must-revalidate"}
        )
    return "<h1>可持续发展报告指标平台运行中</h1>"


# ==================== 1. 统计概览 API ====================
@app.get("/api/stats")
async def get_platform_stats():
    """获取平台整体指标库统计数据（四大核心统计指标）"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM companies")
    total_companies = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM reports")
    total_reports = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM reports WHERE status = '已人工核对'")
    verified_reports = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM kpi_records")
    total_kpis = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM kpi_records WHERE audit_status IN ('已人工核对', '人工已修正')")
    verified_kpis = c.fetchone()[0]

    conn.close()
    return {
        "total_companies": total_companies,
        "total_reports": total_reports,
        "processed_reports": total_reports,
        "verified_reports": verified_reports,
        "total_kpis": total_kpis,
        "verified_kpis": verified_kpis,
        "verified_rate": f"{round(verified_kpis / max(1, total_kpis) * 100, 1)}%"
    }


# ==================== 2. 公司库、行业与趋势图 API ====================
SHENWAN_L1_ALL = [
    "电子", "电力设备", "汽车", "钢铁", "机械设备", "计算机", "通信", "医药生物",
    "基础化工", "有色金属", "家用电器", "食品饮料", "纺织服饰", "轻工制造", "建筑材料",
    "建筑装饰", "石油石化", "煤炭", "公用事业", "环保", "交通运输", "农林牧渔",
    "商贸零售", "社会服务", "美容护理", "银行", "非银金融", "房地产", "国防军工",
    "传媒", "综合"
]


@app.get("/api/industries")
async def list_industries():
    """获取全31个一级行业列表及当前收录企业统计"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT industry_l1, COUNT(*) as cnt FROM companies GROUP BY industry_l1")
    counts = {r["industry_l1"]: r["cnt"] for r in c.fetchall()}
    conn.close()

    result = []
    for ind in SHENWAN_L1_ALL:
        c_num = counts.get(ind, 0)
        result.append({
            "name": ind,
            "count": c_num,
            "is_ingested": c_num > 0,
            "label": f"{ind} (已收录 {c_num} 家)" if c_num > 0 else f"{ind} (待收录)"
        })
    return {
        "industries": result,
        "total_industries": len(result),
        "ingested_industries": sum(1 for r in result if r["is_ingested"])
    }


@app.get("/api/companies")
async def list_companies(keyword: Optional[str] = None, industry: Optional[str] = None):
    """公司列表查询，支持名称/代码搜索与行业严格筛选"""
    conn = get_db_connection()
    c = conn.cursor()
    query = "SELECT * FROM companies WHERE 1=1"
    params: List[Any] = []

    if keyword:
        kw = keyword.strip()
        query += " AND (code LIKE ? OR name LIKE ?)"
        params.extend([f"%{kw}%", f"%{kw}%"])
    if industry and industry != "全部":
        query += " AND (industry LIKE ? OR industry_l1 = ? OR industry_l2 = ?)"
        params.extend([f"%{industry}%", industry, industry])

    query += " ORDER BY code ASC"
    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]

    for item in rows:
        c.execute("SELECT DISTINCT year FROM reports WHERE company_code = ? ORDER BY year ASC", (item["code"],))
        item["available_years"] = [r[0] for r in c.fetchall()]
        c.execute("SELECT COUNT(*) FROM reports WHERE company_code = ?", (item["code"],))
        item["reports_count"] = c.fetchone()[0]

    conn.close()
    return {"companies": rows}


@app.get("/api/companies/{code}")
async def get_company_detail(code: str, indicator: Optional[str] = "Q01"):
    """获取单家公司详情，以及指定指标跨年份的折线图数据"""
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("SELECT * FROM companies WHERE code = ?", (code,))
    comp = c.fetchone()
    if not comp:
        conn.close()
        raise HTTPException(status_code=404, detail="未找到该企业")

    c.execute("""
    SELECT indicator_code, indicator_name, dimension, std_unit, clause
    FROM kpi_records 
    WHERE company_code = ?
    GROUP BY indicator_code
    ORDER BY indicator_code ASC
    """, (code,))
    available_indicators = [dict(r) for r in c.fetchall()]

    c.execute("""
    SELECT year, std_value, raw_value, raw_unit, std_unit, audit_status, quote, page
    FROM kpi_records
    WHERE company_code = ? AND indicator_code = ?
    ORDER BY year ASC
    """, (code, indicator))
    trend_rows = [dict(r) for r in c.fetchall()]

    c.execute("SELECT COUNT(*) FROM reports WHERE company_code = ?", (code,))
    reports_count = c.fetchone()[0]

    c.execute("""
    SELECT * FROM kpi_records
    WHERE company_code = ? AND year = (SELECT MAX(year) FROM reports WHERE company_code = ?)
    ORDER BY id ASC
    """, (code, code))
    latest_kpis = [dict(r) for r in c.fetchall()]

    conn.close()
    return {
        "company": dict(comp),
        "reports_count": reports_count,
        "available_indicators": available_indicators,
        "selected_indicator": indicator,
        "trend_data": trend_rows,
        "latest_kpis": latest_kpis
    }


# ==================== 3. 报告库 API ====================
@app.get("/api/reports")
async def list_reports(
    year: Optional[int] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None
):
    """报告库列表，支持年份、关键词与状态筛选"""
    conn = get_db_connection()
    c = conn.cursor()
    query = "SELECT * FROM reports WHERE 1=1"
    params: List[Any] = []

    if year:
        query += " AND year = ?"
        params.append(year)
    if keyword and keyword.strip():
        kw = f"%{keyword.strip()}%"
        query += " AND (company_code LIKE ? OR company_name LIKE ? OR title LIKE ?)"
        params.extend([kw, kw, kw])
    if status and status not in ("全部", "官方披露"):
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY year DESC, id DESC"
    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    for item in rows:
        fn = Path(item.get("pdf_filename") or "").name
        item["has_pdf"] = bool(fn)
    conn.close()
    return {"reports": rows}


@app.get("/api/reports/{report_id}")
async def get_report_detail(report_id: int):
    """获取报告详情：分为 Raw KPIs (原始披露项) 与 Standard KPIs (标准指标库) 两个标签页数据"""
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
    rep = c.fetchone()
    if not rep:
        conn.close()
        raise HTTPException(status_code=404, detail="报告不存在")

    c.execute("SELECT * FROM kpi_records WHERE report_id = ? ORDER BY id ASC", (report_id,))
    kpis = [dict(r) for r in c.fetchall()]
    conn.close()

    raw_kpis = [
        {
            "code": k["indicator_code"],
            "raw_name": k["raw_name"] or k["indicator_name"],
            "raw_value": k["raw_value"],
            "raw_unit": k["raw_unit"],
            "year": k["year"],
            "page": k["page"]
        }
        for k in kpis
    ]

    rep_dict = dict(rep)
    fn = Path(rep_dict.get("pdf_filename") or "").name
    rep_dict["has_pdf"] = bool(fn)

    return {
        "report": rep_dict,
        "raw_kpis": raw_kpis,
        "standard_kpis": kpis
    }


@app.get("/api/reports/{report_id}/download-pdf")
async def download_report_pdf(report_id: int):
    """下载特定报告的官方披露原版 PDF 文件（优先本地直出，云端容器无本地文件时自动回源 GitHub Raw CDN）"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
    rep = c.fetchone()
    conn.close()
    if not rep:
        raise HTTPException(status_code=404, detail="未找到该报告记录")

    pdf_filename = Path(rep["pdf_filename"] or "").name
    if not pdf_filename:
        raise HTTPException(status_code=404, detail="该报告暂无关联的 PDF 文件")

    candidate_paths = [
        (REPORTS_DIR / pdf_filename).resolve(),
        (STORAGE_DIR / "reports" / pdf_filename).resolve(),
    ]
    target_file = None
    for p in candidate_paths:
        if p.is_file() and (p.is_relative_to(REPORTS_DIR.resolve()) or p.is_relative_to(STORAGE_DIR.resolve())):
            target_file = p
            break

    encoded_name = quote(pdf_filename)
    if not target_file:
        cloud_pdf_url = f"{GITHUB_RAW_PDF_BASE.rstrip('/')}/{encoded_name}"
        return RedirectResponse(url=cloud_pdf_url, status_code=302)

    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"
    }
    return FileResponse(
        path=str(target_file),
        media_type="application/pdf",
        headers=headers
    )


# ==================== 4. 全行业排名 API ====================
@app.get("/api/rankings")
async def get_rankings(indicator_code: str = "Q01", year: int = 2024):
    """返回指定指标与年度的企业横向对比排名列表"""
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("""
    SELECT k.company_code, k.company_name, c.industry, k.year, k.std_value, k.std_unit, k.audit_status
    FROM kpi_records k
    JOIN companies c ON k.company_code = c.code
    WHERE k.indicator_code = ? AND k.year = ? AND k.std_value IS NOT NULL
    ORDER BY k.std_value DESC
    """, (indicator_code, year))

    rankings = [dict(r) for r in c.fetchall()]
    conn.close()
    return {
        "indicator_code": indicator_code,
        "year": year,
        "rankings": rankings
    }


# ==================== 5. 人工标注底稿导出与回写同步 API (管理员专享，物理隔离目录) ====================
@app.get("/api/annotation/export/{report_id}")
async def export_annotation_excel(report_id: int, request: Request, token: Optional[str] = None):
    """导出针对特定报告的人工标注 Excel 底稿供团队协作（仅限管理员，存放于隔离私有目录）"""
    require_admin(request, token)
    cleanup_stale_files()

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT company_name, year FROM reports WHERE id = ?", (report_id,))
    rep = c.fetchone()
    conn.close()
    if not rep:
        raise HTTPException(status_code=404, detail="未找到该报告记录")

    safe_comp = "".join(ch for ch in rep["company_name"] if ch.isalnum() or ch in ("-", "_"))
    download_name = f"{safe_comp}_{rep['year']}年_ESG人工核验底稿.xlsx"
    internal_name = f"workpaper_rep{report_id}_{secrets.token_hex(4)}.xlsx"
    out_path = str(ADMIN_WORKPAPER_DIR / internal_name)

    AnnotationManager.export_annotation_workbook(report_id, out_path)
    return FileResponse(
        path=out_path,
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.post("/api/annotation/import")
async def import_annotation_excel(request: Request, file: UploadFile = File(...)):
    """上传人工填写的核验 Excel 底稿，自动回写 SQLite 数据库（仅限管理员）"""
    require_admin(request)
    raw_name = Path(file.filename or "").name
    suffix = Path(raw_name).suffix.lower()
    if suffix not in (".xlsx", ".xlsm"):
        raise HTTPException(status_code=400, detail="文件格式非法：仅支持上传 Excel 格式底稿 (.xlsx)")

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="底稿文件大小超出 20MB 限制")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        res = AnnotationManager.import_and_sync_annotation(tmp_path)
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error("导入核验底稿失败: %s", e)
        raise HTTPException(status_code=400, detail="底稿解析失败，请确认使用的是平台导出的标准核验底稿模板")
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


# ==================== 6. 报告智能抽取 API（普通用户私密隔离，管理员支持入库） ====================
@app.get("/api/samples")
async def list_samples():
    """获取内置真实样本报告列表（隐藏服务器物理路径，保障安全）"""
    samples = []
    if REPORTS_DIR.exists():
        for f in sorted(os.listdir(REPORTS_DIR)):
            if f.lower().endswith(".pdf"):
                full_path = REPORTS_DIR / f
                samples.append({
                    "filename": f,
                    "size_mb": round(full_path.stat().st_size / (1024 * 1024), 2)
                })
    return {"samples": samples}


@app.post("/api/settings")
async def update_settings(settings: SettingsModel, request: Request):
    """全局大模型配置（仅限系统管理员操作，持久化保存）"""
    require_admin(request)
    provider = (settings.provider or "openai").lower()
    if provider not in ("gemini", "openai"):
        raise HTTPException(status_code=400, detail="不支持的模型引擎类型")

    api_key_in = (settings.api_key or "").strip()
    if provider == "gemini":
        if api_key_in == "__CLEAR__":
            config.GEMINI_API_KEY = ""
        elif api_key_in:
            config.GEMINI_API_KEY = api_key_in
        if settings.model:
            config.GEMINI_MODEL = settings.model.strip()
        config.DEFAULT_PROVIDER = "gemini"
    else:
        if api_key_in == "__CLEAR__":
            config.OPENAI_API_KEY = ""
        elif api_key_in:
            config.OPENAI_API_KEY = api_key_in
        if settings.model:
            config.OPENAI_MODEL = settings.model.strip()
        if settings.base_url:
            config.OPENAI_BASE_URL = settings.base_url.strip()
        config.DEFAULT_PROVIDER = "openai"

    save_persisted_llm_config()
    return {"status": "ok", "message": f"大模型配置已保存生效（当前引擎: {provider}）"}


@app.get("/api/settings")
async def get_settings(request: Request):
    """查询当前大模型配置状态（仅限管理员，不回传明文密钥）"""
    require_admin(request)
    return {
        "provider": config.DEFAULT_PROVIDER,
        "has_gemini_key": bool(config.GEMINI_API_KEY),
        "gemini_model": config.GEMINI_MODEL,
        "has_openai_key": bool(config.OPENAI_API_KEY),
        "openai_model": config.OPENAI_MODEL,
        "openai_base_url": config.OPENAI_BASE_URL
    }


@app.post("/api/analyze")
async def analyze_report(
    request: Request = None,
    file: Optional[UploadFile] = None,
    sample_filename: Optional[str] = Form(None)
):
    """
    执行单份 ESG 报告智能抽取：
    - 普通用户：独立私密会话，仅提取指标与生成不可猜测的随机令牌数据表下载链接，绝不写入公共数据库、绝不在服务端留存上传的 PDF；
    - 管理员：除提取指标外，暂存上传 PDF 供管理员确认后一键收录发布至公共报告库。
    """
    cleanup_stale_files()
    is_admin_user = verify_token(extract_token_from_request(request))

    if not is_admin_user and request is not None:
        client_ip = get_client_ip(request)
        if check_analyze_rate_limit(client_ip):
            raise HTTPException(status_code=429, detail="请求过于频繁：每 5 分钟最多解析 10 份报告，请稍后再试")

    target_path = None
    is_temp = False
    max_upload_bytes = (150 if is_admin_user else 80) * 1024 * 1024

    try:
        if file is not None and hasattr(file, "filename") and file.filename:
            raw_filename = Path(file.filename).name
            suffix = Path(raw_filename).suffix.lower()
            if suffix != ".pdf":
                raise HTTPException(status_code=400, detail="上传文件格式非法：仅支持上传标准 PDF 格式报告")

            # 分块流式读取并校验文件头与体积上限，防止超大文件打满内存
            total_read = 0
            header_bytes = b""
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                target_path = tmp.name
                is_temp = True
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    if not header_bytes:
                        header_bytes = chunk[:8]
                    total_read += len(chunk)
                    if total_read > max_upload_bytes:
                        raise HTTPException(
                            status_code=400,
                            detail=f"文件体积超出 {max_upload_bytes // (1024 * 1024)}MB 上限"
                        )
                    tmp.write(chunk)

            if total_read < 100 or not header_bytes.startswith(b"%PDF-"):
                raise HTTPException(status_code=400, detail="文件内容无效：未检测到合法的 PDF 文件头")

            display_name = raw_filename
        elif sample_filename and sample_filename != "None":
            safe_sample = Path(sample_filename).name
            sample_path = (REPORTS_DIR / safe_sample).resolve()
            if not sample_path.is_file() or not sample_path.is_relative_to(REPORTS_DIR.resolve()):
                raise HTTPException(status_code=404, detail="样本报告不存在或无权访问")
            target_path = str(sample_path)
            display_name = safe_sample
        else:
            raise HTTPException(status_code=400, detail="请上传 PDF 文件或选择预置样本报告")

        client = LLMClient()
        extractor = ESGExtractor(client)
        result = extractor.process_report(target_path)
        result["summary"]["filename"] = display_name
        result["original_filename"] = display_name

        # 生成带随机安全令牌的纯净【指标数据表】Excel，防止其他访客遍历猜测文件名
        safe_stem = "".join(c for c in Path(display_name).stem if c.isalnum() or c in ("-", "_")) or "ESG报告"
        rand_tag = secrets.token_hex(6)
        excel_filename = f"{safe_stem}__{rand_tag}_ESG指标数据表.xlsx"
        excel_path = str(OUTPUT_DIR / excel_filename)
        ExcelExporter.export_clean_data(result, excel_path)
        result["excel_download_url"] = f"/api/download/{excel_filename}"

        summary = result["summary"]
        company_name = summary["company_name"]
        company_code = summary.get("company_code")
        report_year = summary["report_year"]
        summary["report_title"] = f"{company_name}{report_year}年度可持续发展报告"

        # 仅当当前操作者为已登录管理员时，暂存上传的 PDF 以便其点击“确认收录入库”；普通访客上传的 PDF 绝不留存！
        if is_temp and is_admin_user:
            safe_pdf_name = "".join(c for c in Path(display_name).name if c.isalnum() or c in ("-", "_", "."))
            temp_pdf_id = f"temp_{int(time.time())}_{secrets.token_hex(4)}_{safe_pdf_name}"
            saved_temp_path = TEMP_UPLOADS_DIR / temp_pdf_id
            shutil.copyfile(target_path, saved_temp_path)
            result["temp_pdf_id"] = temp_pdf_id

        # 查询该企业若已存在于公司库，补全其股票代码与行业供管理员参考（只读查询，绝不修改数据库）
        conn = get_db_connection()
        c = conn.cursor()
        comp_info = None
        if company_code:
            c.execute("SELECT code, name, industry_l1 FROM companies WHERE code = ?", (company_code,))
            comp_info = c.fetchone()
        if not comp_info and company_name and company_name != "未知公司":
            c.execute("SELECT code, name, industry_l1 FROM companies WHERE name = ? OR name LIKE ?", (company_name, f"%{company_name[:4]}%"))
            comp_info = c.fetchone()
        if comp_info:
            summary["company_code"] = summary.get("company_code") or comp_info["code"]
            summary["industry_l1"] = comp_info["industry_l1"]

        c.execute(
            "SELECT id FROM reports WHERE (company_name = ? OR company_code = ?) AND year = ?",
            (company_name, summary.get("company_code") or "", report_year)
        )
        existing_rep = c.fetchone()
        conn.close()

        result["is_published"] = bool(existing_rep)
        if existing_rep:
            result["published_report_id"] = existing_rep["id"]

        return result

    except HTTPException:
        raise
    except RuntimeError as re_err:
        # LLMClient 已脱敏的业务可读异常
        raise HTTPException(status_code=502, detail=str(re_err))
    except Exception as e:
        logger.exception("PDF 解析或指标抽取异常: %s", type(e).__name__)
        raise HTTPException(status_code=500, detail="报告解析处理异常，请确认上传的文件为未加密的标准 PDF 报告")
    finally:
        if is_temp and target_path and os.path.exists(target_path):
            try:
                os.remove(target_path)
            except Exception:
                pass


# ==================== 7. 管理员报告正式收录入库发布 API ====================
class PublishReportModel(BaseModel):
    company_name: str
    company_code: Optional[str] = None
    industry: Optional[str] = None
    industry_l1: Optional[str] = "电子"
    industry_l2: Optional[str] = None
    year: int
    title: Optional[str] = None
    total_pages: int = 0
    disclosure_rate: str = "0.0%"
    verified_rate: str = "0.0%"
    temp_pdf_id: Optional[str] = None
    original_filename: Optional[str] = None
    indicators: List[Dict[str, Any]]


@app.post("/api/admin/reports/publish")
async def publish_report_to_db(payload: PublishReportModel, request: Request):
    """
    管理员专属收录通道：经管理员审查后，将新解析的报告正式入库发布至平台公共报告库。
    发布后，所有前台普通访客均可在【报告库】与【公司库】中查阅并导出。
    """
    require_admin(request)

    conn = get_db_connection()
    c = conn.cursor()

    ind_l1 = (payload.industry_l1 or "电子").strip()
    if ind_l1 not in SHENWAN_L1_ALL:
        ind_l1 = "综合"
    ind_l2 = (payload.industry_l2 or ind_l1).strip()
    ind_full = (payload.industry or f"{ind_l1} · {ind_l2}").strip()

    # 匹配或创建公司
    clean_req_code = (payload.company_code or "").strip()
    comp_row = None
    if clean_req_code:
        c.execute("SELECT code, name FROM companies WHERE code = ?", (clean_req_code,))
        comp_row = c.fetchone()
    if not comp_row:
        c.execute("SELECT code, name FROM companies WHERE name = ?", (payload.company_name.strip(),))
        comp_row = c.fetchone()

    if comp_row:
        company_code = comp_row["code"]
    else:
        company_code = clean_req_code or f"A{int(payload.year % 100):02d}{int(time.time() % 10000):04d}"
        c.execute("""
        INSERT INTO companies (code, name, industry, industry_l1, industry_l2, exchange, description)
        VALUES (?, ?, ?, ?, ?, 'A股上市公司', '经平台管理员审阅收录的A股上市公司')
        """, (company_code, payload.company_name.strip(), ind_full, ind_l1, ind_l2))

    report_title = (payload.title or f"{payload.company_name}{payload.year}年度可持续发展报告").strip()

    # 检查是否已收录过该报告（先校验防重，再落盘 PDF）
    c.execute("SELECT id FROM reports WHERE company_code = ? AND year = ?", (company_code, payload.year))
    rep_row = c.fetchone()
    if rep_row:
        conn.close()
        raise HTTPException(status_code=400, detail=f"《{report_title}》已收录入库，请勿重复发布！")

    # 持久化 PDF 至 esg报告/ 官方目录
    raw_orig = Path(payload.original_filename or "").name
    final_pdf_name = raw_orig if raw_orig.lower().endswith(".pdf") else f"{payload.company_name}{payload.year}可持续发展报告.pdf"
    if payload.temp_pdf_id:
        temp_file = (TEMP_UPLOADS_DIR / Path(payload.temp_pdf_id).name).resolve()
        if temp_file.is_file() and temp_file.is_relative_to(TEMP_UPLOADS_DIR.resolve()):
            target_dest = REPORTS_DIR / final_pdf_name
            if target_dest.exists():
                final_pdf_name = f"{company_code}_{payload.year}_{final_pdf_name}"
                target_dest = REPORTS_DIR / final_pdf_name
            shutil.copyfile(temp_file, target_dest)
            temp_file.unlink(missing_ok=True)
    elif not (REPORTS_DIR / final_pdf_name).exists():
        final_pdf_name = ""

    c.execute("""
    INSERT INTO reports (company_code, company_name, year, title, pdf_filename, total_pages, status, disclosure_rate, verified_rate, created_at)
    VALUES (?, ?, ?, ?, ?, ?, 'AI初抽，待核查', ?, ?, datetime('now', 'localtime'))
    """, (company_code, payload.company_name.strip(), payload.year, report_title, final_pdf_name, payload.total_pages, payload.disclosure_rate, payload.verified_rate))
    rep_id = c.lastrowid

    # 批量入库指标（初始状态严格标记为 AI初抽，待核查）
    for ind in payload.indicators:
        code = ind.get("code")
        meta = INDICATOR_META.get(code, (ind.get("name") or code, "环境维度 (E)", ind.get("clause") or "", ind.get("std_unit") or ""))
        dim = ind.get("dimension") or meta[1]
        ind_name = ind.get("name") or meta[0]
        ind_clause = ind.get("clause") or meta[2]
        ind_std_unit = ind.get("std_unit") or meta[3]

        c.execute("""
        INSERT INTO kpi_records (report_id, company_code, company_name, year, indicator_code, indicator_name, dimension, clause, raw_value, raw_unit, std_value, std_unit, conv_note, page, quote, verified_in_page, status, audit_status, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'AI初抽，待核查', datetime('now', 'localtime'))
        """, (
            rep_id, company_code, payload.company_name.strip(), payload.year,
            code, ind_name, dim, ind_clause,
            ind.get("raw_value"), ind.get("raw_unit"), ind.get("std_value"), ind_std_unit,
            ind.get("conv_note"), ind.get("page"), ind.get("quote"), 1 if ind.get("verified_in_page") else 0,
            ind.get("status") or "已披露"
        ))
    conn.commit()
    conn.close()

    return {
        "status": "ok",
        "report_id": rep_id,
        "company_code": company_code,
        "company_name": payload.company_name.strip(),
        "title": report_title,
        "kpis_inserted": len(payload.indicators),
        "message": f"报告《{report_title}》已成功收录发布至平台报告库！"
    }


# ==================== 8. 普通用户专属纯净指标数据表导出 API ====================
@app.get("/api/reports/{report_id}/export-data")
async def export_report_clean_data(report_id: int):
    """面向所有用户：导出官方已收录报告的纯净指标数据表 Excel（不含任何核验标注工作列）"""
    cleanup_stale_files()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
    rep = c.fetchone()
    if not rep:
        conn.close()
        raise HTTPException(status_code=404, detail="未找到该报告记录")

    c.execute("SELECT * FROM kpi_records WHERE report_id = ? ORDER BY id ASC", (report_id,))
    records = [dict(r) for r in c.fetchall()]
    conn.close()

    safe_name = "".join(ch for ch in rep["company_name"] if ch.isalnum() or ch in ("-", "_"))
    download_filename = f"{safe_name}_{rep['year']}年_可持续发展指标数据表.xlsx"
    internal_filename = f"clean_rep{report_id}_{rep['year']}.xlsx"
    out_path = str(OUTPUT_DIR / internal_filename)
    ExcelExporter.export_clean_data_from_db(dict(rep), records, out_path)
    return FileResponse(
        path=out_path,
        filename=download_filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.get("/api/download/{filename}")
async def download_excel(filename: str):
    """下载普通用户临时生成的纯净指标数据表 Excel（严格防范路径遍历与管理员底稿越权访问）"""
    safe_name = Path(filename).name
    lower_name = safe_name.lower()
    if "annotation" in lower_name or "workpaper" in lower_name or "核验底稿" in safe_name:
        raise HTTPException(status_code=403, detail="无权访问内部核验底稿")

    file_path = (OUTPUT_DIR / safe_name).resolve()
    if not file_path.is_file() or not file_path.is_relative_to(OUTPUT_DIR.resolve()):
        raise HTTPException(status_code=404, detail="文件不存在或已过期清理，请重新导出")

    # 还原清爽的用户下载文件名（隐藏内部随机防猜测后缀 __hex）
    clean_dl_name = re.sub(r"__[0-9a-f]{12}_", "_", safe_name)
    return FileResponse(
        path=str(file_path),
        filename=clean_dl_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    is_dev = os.environ.get("ENV", "development").lower() != "production"
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=is_dev)
