import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import openpyxl

from core.database import get_db_connection, INDICATOR_META
from core.rules_engine import RulesEngine
from core.pdf_parser import PDFParser

logger = logging.getLogger("esg_platform.muse_sync")

BASE_DIR = Path(__file__).resolve().parent.parent
MUSE_INBOX_DIR = BASE_DIR / "muse_inbox"
REPORTS_DIR = BASE_DIR / "esg报告"


def _parse_excel_workpaper(xlsx_path: Path) -> List[Dict[str, Any]]:
    """
    解析 Muse 生成并上传到 muse_inbox/ 的 Excel 文件。
    支持两种格式：
    1) 包含 '报告信息'（或第一行元数据）与 '指标数据' 的标准模板
    2) 单表结构：包含 company_code, company_name, year, pdf_filename 及各指标行
    """
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    sheet = wb.active

    meta: Dict[str, Any] = {
        "company_code": "",
        "company_name": "",
        "industry_l1": "其他",
        "industry_l2": "综合",
        "exchange": "上交所 (SH)",
        "year": 2024,
        "title": "",
        "pdf_filename": "",
        "indicators": {}
    }

    # 如果存在专门的元数据键值区（前10行第一列为字段名）
    rows = list(sheet.iter_rows(values_only=True))
    header_row_idx = 0
    for idx, r in enumerate(rows[:15]):
        if not r or all(c is None for c in r):
            continue
        first_cell = str(r[0] or "").strip()
        if first_cell in ("指标代码", "code", "indicator_code", "编号"):
            header_row_idx = idx
            break
        second_val = str(r[1] or "").strip() if len(r) > 1 and r[1] is not None else ""
        if first_cell in ("股票代码", "company_code", "证券代码"):
            meta["company_code"] = second_val.zfill(6) if second_val.isdigit() else second_val
        elif first_cell in ("公司名称", "company_name", "企业名称"):
            meta["company_name"] = second_val
        elif first_cell in ("一级行业", "industry_l1"):
            meta["industry_l1"] = second_val
        elif first_cell in ("二级行业", "industry_l2"):
            meta["industry_l2"] = second_val
        elif first_cell in ("交易所", "exchange"):
            meta["exchange"] = second_val
        elif first_cell in ("报告年份", "year", "报告年度"):
            try:
                meta["year"] = int(float(second_val))
            except Exception:
                pass
        elif first_cell in ("报告标题", "title"):
            meta["title"] = second_val
        elif first_cell in ("PDF文件名", "pdf_filename", "关联PDF"):
            meta["pdf_filename"] = second_val

    if header_row_idx < len(rows):
        headers = [str(c or "").strip().lower() for c in rows[header_row_idx]]
        col_map = {}
        for i, h in enumerate(headers):
            if h in ("指标代码", "code", "indicator_code", "编号"):
                col_map["code"] = i
            elif h in ("披露数值", "原值", "value", "raw_value", "数值"):
                col_map["value"] = i
            elif h in ("披露单位", "原单位", "unit", "raw_unit", "单位"):
                col_map["unit"] = i
            elif h in ("页码", "所在页码", "page"):
                col_map["page"] = i
            elif h in ("原文证据", "原文摘录", "quote", "证据片段", "原文依据"):
                col_map["quote"] = i
            elif h in ("股票代码", "company_code"):
                col_map["company_code"] = i
            elif h in ("公司名称", "company_name"):
                col_map["company_name"] = i
            elif h in ("报告年份", "year"):
                col_map["year"] = i
            elif h in ("pdf文件名", "pdf_filename"):
                col_map["pdf_filename"] = i

        for r in rows[header_row_idx + 1:]:
            if not r or all(c is None for c in r):
                continue
            code_idx = col_map.get("code", 0)
            code = str(r[code_idx] or "").strip().upper() if code_idx < len(r) else ""
            if code not in INDICATOR_META:
                continue

            if "company_code" in col_map and not meta["company_code"]:
                v = str(r[col_map["company_code"]] or "").strip()
                meta["company_code"] = v.zfill(6) if v.isdigit() else v
            if "company_name" in col_map and not meta["company_name"]:
                meta["company_name"] = str(r[col_map["company_name"]] or "").strip()
            if "year" in col_map and r[col_map["year"]]:
                try:
                    meta["year"] = int(float(str(r[col_map["year"]])))
                except Exception:
                    pass
            if "pdf_filename" in col_map and not meta["pdf_filename"]:
                meta["pdf_filename"] = str(r[col_map["pdf_filename"]] or "").strip()

            val_raw = r[col_map["value"]] if "value" in col_map and col_map["value"] < len(r) else None
            unit_raw = str(r[col_map["unit"]] or "").strip() if "unit" in col_map and col_map["unit"] < len(r) else ""
            page_raw = r[col_map["page"]] if "page" in col_map and col_map["page"] < len(r) else 0
            quote_raw = str(r[col_map["quote"]] or "").strip() if "quote" in col_map and col_map["quote"] < len(r) else ""

            meta["indicators"][code] = {
                "value": val_raw,
                "unit": unit_raw,
                "page": page_raw,
                "quote": quote_raw
            }

    wb.close()
    if meta["company_code"] and meta["company_name"]:
        return [meta]
    return []


def ingest_single_report(rep_obj: Dict[str, Any]) -> bool:
    """将单份标准化报告对象核验并写入 SQLite 数据库"""
    comp_code = str(rep_obj.get("company_code") or rep_obj.get("code") or "").strip()
    if comp_code.isdigit() and len(comp_code) < 6:
        comp_code = comp_code.zfill(6)
    comp_name = str(rep_obj.get("company_name") or "").strip()
    if not comp_code or not comp_name:
        return False

    year = int(rep_obj.get("year") or rep_obj.get("report_year") or 2024)
    ind_l1 = str(rep_obj.get("industry_l1") or "其他").strip()
    ind_l2 = str(rep_obj.get("industry_l2") or "综合").strip()
    industry = str(rep_obj.get("industry") or f"{ind_l1} · {ind_l2}").strip()
    exchange = str(rep_obj.get("exchange") or ("上交所 (SH)" if comp_code.startswith("6") else "深交所 (SZ)")).strip()
    desc = str(rep_obj.get("description") or f"{comp_name} 可持续发展报告收录企业").strip()

    pdf_filename = str(rep_obj.get("pdf_filename") or "").strip()
    title = str(rep_obj.get("title") or f"{comp_name}{year}年度可持续发展报告").strip()

    pdf_path = REPORTS_DIR / pdf_filename if pdf_filename else None
    parser: Optional[PDFParser] = None
    total_pages = int(rep_obj.get("total_pages") or 0)
    if pdf_path and pdf_path.is_file():
        try:
            parser = PDFParser(str(pdf_path))
            total_pages = parser.total_pages
        except Exception as e:
            logger.warning("打开 PDF 进行核验失败 (%s): %s", pdf_filename, e)

    indicators_in = rep_obj.get("indicators") or rep_obj.get("data") or {}
    status_label = str(rep_obj.get("status") or "AI抽取，待核查")

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. 确保公司记录存在
    cursor.execute("SELECT code FROM companies WHERE code = ?", (comp_code,))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO companies (code, name, industry, industry_l1, industry_l2, exchange, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (comp_code, comp_name, industry, ind_l1, ind_l2, exchange, desc))

    # 2. 检查报告是否已存在（存在则更新，不存在则新增）
    cursor.execute("SELECT id FROM reports WHERE company_code = ? AND year = ?", (comp_code, year))
    existing_rep = cursor.fetchone()
    if existing_rep:
        rep_id = existing_rep["id"]
        cursor.execute("DELETE FROM kpi_records WHERE report_id = ?", (rep_id,))
    else:
        cursor.execute("""
            INSERT INTO reports (company_code, company_name, year, title, pdf_filename, total_pages, status, disclosure_rate, verified_rate, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, '0.0%', '0.0%', datetime('now', 'localtime'))
        """, (comp_code, comp_name, year, title, pdf_filename, total_pages, status_label))
        rep_id = cursor.lastrowid

    disclosed_count = 0
    for code, meta in INDICATOR_META.items():
        name, dimension, clause, def_std_unit = meta
        raw_item = indicators_in.get(code)

        raw_val = None
        raw_unit = ""
        std_val = None
        std_unit = def_std_unit
        conv_note = "报告未做定量披露"
        page = 0
        quote = ""
        verified = 0
        row_status = "未披露"

        if isinstance(raw_item, (list, tuple)) and len(raw_item) >= 7:
            raw_val, raw_unit, std_val, std_unit, conv_note, page, quote = raw_item[:7]
            verified = 1 if quote else 0
            row_status = "已披露" if raw_val is not None else "未披露"
        elif isinstance(raw_item, dict):
            raw_val = RulesEngine.parse_numeric(raw_item.get("value") if "value" in raw_item else raw_item.get("raw_value"))
            raw_unit = str(raw_item.get("unit") or raw_item.get("raw_unit") or "").strip()
            try:
                page = int(float(str(raw_item.get("page") or 0)))
            except Exception:
                page = 0
            quote = str(raw_item.get("quote") or "").strip()

            if raw_val is not None:
                if code == "Q30":
                    std_val = 1.0 if raw_val >= 1 else 0.0
                    std_unit = "类别字段"
                    conv_note = str(raw_item.get("conv_note") or ("出具独立鉴证声明" if std_val == 1.0 else "未附独立鉴证"))
                else:
                    std_val, std_unit, conv_note = RulesEngine.standardize_unit(code, raw_val, raw_unit)
                    if std_val is None and "校正为未披露" in str(conv_note):
                        raw_val = None

            if raw_val is not None:
                row_status = "已披露"
                if parser and quote and page > 0:
                    verified = 1 if parser.verify_quote_in_page(quote, page) else 0
                elif quote:
                    verified = 1

        if row_status == "已披露" and raw_val is not None:
            disclosed_count += 1

        cursor.execute("""
            INSERT INTO kpi_records (
                report_id, company_code, company_name, year,
                indicator_code, indicator_name, dimension, clause,
                raw_name, raw_value, raw_unit, std_value, std_unit, conv_note,
                page, quote, verified_in_page, status, audit_status, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
        """, (
            rep_id, comp_code, comp_name, year,
            code, name, dimension, clause,
            name if row_status == "已披露" else None,
            raw_val, raw_unit if row_status == "已披露" else None,
            std_val, std_unit, conv_note,
            page if row_status == "已披露" else None,
            quote if row_status == "已披露" else None,
            verified, row_status,
            "已人工核对" if status_label == "已人工核对" else "AI抽取待核查"
        ))

    disc_rate = f"{round(disclosed_count / len(INDICATOR_META) * 100, 1)}%"
    cursor.execute("""
        UPDATE reports SET title = ?, pdf_filename = ?, total_pages = ?, status = ?, disclosure_rate = ?
        WHERE id = ?
    """, (title, pdf_filename, total_pages, status_label, disc_rate, rep_id))

    conn.commit()
    conn.close()
    return True


def sync_muse_inbox() -> Dict[str, Any]:
    """
    自动扫描 muse_inbox/ 目录下的所有 .json 与 .xlsx 文件，
    自动核验并同步入库到 esg_platform.db。
    """
    MUSE_INBOX_DIR.mkdir(parents=True, exist_ok=True)
    synced_reports = 0
    files_processed = []

    for fpath in sorted(MUSE_INBOX_DIR.iterdir()):
        if fpath.name.startswith(".") or fpath.name.startswith("~$"):
            continue
        suffix = fpath.suffix.lower()
        try:
            if suffix == ".json":
                payload = json.loads(fpath.read_text(encoding="utf-8"))
                items = payload if isinstance(payload, list) else [payload]
                for item in items:
                    if isinstance(item, dict) and ingest_single_report(item):
                        synced_reports += 1
                files_processed.append(fpath.name)
            elif suffix == ".xlsx":
                items = _parse_excel_workpaper(fpath)
                for item in items:
                    if ingest_single_report(item):
                        synced_reports += 1
                files_processed.append(fpath.name)
        except Exception as e:
            logger.error("解析 muse_inbox 文件失败 (%s): %s", fpath.name, e)

    return {
        "files_processed": files_processed,
        "synced_reports": synced_reports
    }
