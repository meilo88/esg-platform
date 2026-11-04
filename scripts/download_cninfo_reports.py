"""
从巨潮资讯网 (www.cninfo.com.cn) 官方接口检索并下载上市公司真实可持续发展 / ESG 报告 PDF。
仅执行官方公告检索与原版 PDF 下载校验，落盘至 esg报告/ 目录并生成 manifest 清单供后续离线精准提取。
"""
import json
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import fitz
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE_DIR / "esg报告"
STORAGE_DIR = BASE_DIR / "storage"
DB_PATH = BASE_DIR / "esg_platform.db"
MANIFEST_PATH = STORAGE_DIR / "cninfo_downloaded_manifest.json"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://www.cninfo.com.cn",
    "Referer": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}

PDF_HEADERS = {
    "Accept": "application/pdf,*/*;q=0.8",
    "Referer": "https://www.cninfo.com.cn/",
    "User-Agent": HEADERS["User-Agent"],
}

# 精选多行业代表性龙头上市公司（补齐已有龙头的多年份序列 + 拓展 8 个核心行业）
TARGET_COMPANIES = [
    # 1. 补齐已有单年份龙头的多年份报告，使历年趋势图形成完整曲线
    {
        "code": "002594",
        "short_name": "比亚迪",
        "name": "比亚迪股份有限公司",
        "industry": "汽车 · 乘用车",
        "industry_l1": "汽车",
        "industry_l2": "乘用车",
        "exchange": "深交所主板",
        "description": "全球新能源汽车及动力电池龙头，全产业链垂直整合制造企业。",
        "max_new": 2,
    },
    {
        "code": "300750",
        "short_name": "宁德时代",
        "name": "宁德时代新能源科技股份有限公司",
        "industry": "电力设备 · 电池",
        "industry_l1": "电力设备",
        "industry_l2": "电池",
        "exchange": "深交所创业板",
        "description": "全球领先的新能源创新科技公司，动力电池与储能系统领军企业。",
        "max_new": 2,
    },
    {
        "code": "600019",
        "short_name": "宝钢股份",
        "name": "宝山钢铁股份有限公司",
        "industry": "钢铁 · 普钢",
        "industry_l1": "钢铁",
        "industry_l2": "普钢",
        "exchange": "上交所主板",
        "description": "中国现代化特大型钢铁联合企业，低碳冶炼行业标杆。",
        "max_new": 2,
    },
    # 2. 新增多行业代表性上市公司（每家抓取最近 2 个年度报告）
    {
        "code": "000333",
        "short_name": "美的集团",
        "name": "美的集团股份有限公司",
        "industry": "家用电器 · 白色家电",
        "industry_l1": "家用电器",
        "industry_l2": "白色家电",
        "exchange": "深交所主板",
        "description": "全球化科技集团，涵盖智能家居、工业技术、楼宇科技与机器人自动化。",
        "max_new": 2,
    },
    {
        "code": "600519",
        "short_name": "贵州茅台",
        "name": "贵州茅台酒股份有限公司",
        "industry": "食品饮料 · 白酒",
        "industry_l1": "食品饮料",
        "industry_l2": "白酒",
        "exchange": "上交所主板",
        "description": "中国酱香型白酒龙头企业，长期系统披露环境、社会及治理绩效。",
        "max_new": 2,
    },
    {
        "code": "300760",
        "short_name": "迈瑞医疗",
        "name": "深圳迈瑞生物医疗电子股份有限公司",
        "industry": "医药生物 · 医疗器械",
        "industry_l1": "医药生物",
        "industry_l2": "医疗器械",
        "exchange": "深交所创业板",
        "description": "全球领先的医疗器械与解决方案供应商，生命信息、体外诊断与医学影像龙头。",
        "max_new": 2,
    },
    {
        "code": "000063",
        "short_name": "中兴通讯",
        "name": "中兴通讯股份有限公司",
        "industry": "通信 · 通信设备",
        "industry_l1": "通信",
        "industry_l2": "通信设备",
        "exchange": "深交所主板",
        "description": "全球领先的综合通信与算力基础设施解决方案提供商。",
        "max_new": 2,
    },
    {
        "code": "002415",
        "short_name": "海康威视",
        "name": "杭州海康威视数字技术股份有限公司",
        "industry": "计算机 · 安防数字化",
        "industry_l1": "计算机",
        "industry_l2": "安防数字化",
        "exchange": "深交所主板",
        "description": "以视频为核心的智能物联网解决方案和大数据服务提供商。",
        "max_new": 2,
    },
    {
        "code": "600309",
        "short_name": "万华化学",
        "name": "万华化学集团股份有限公司",
        "industry": "基础化工 · 化学制品",
        "industry_l1": "基础化工",
        "industry_l2": "化学制品",
        "exchange": "上交所主板",
        "description": "全球化运营的化工新材料领军企业，聚氨酯及精细化学品龙头。",
        "max_new": 2,
    },
    {
        "code": "601899",
        "short_name": "紫金矿业",
        "name": "紫金矿业集团股份有限公司",
        "industry": "有色金属 · 工业金属",
        "industry_l1": "有色金属",
        "industry_l2": "工业金属",
        "exchange": "上交所主板",
        "description": "大型跨国矿业集团，铜、金、锌及新能源矿产资源开发龙头。",
        "max_new": 2,
    },
    {
        "code": "300274",
        "short_name": "阳光电源",
        "name": "阳光电源股份有限公司",
        "industry": "电力设备 · 光伏储能",
        "industry_l1": "电力设备",
        "industry_l2": "光伏储能",
        "exchange": "深交所创业板",
        "description": "专注于太阳能、风能、储能、氢能等新能源电源设备的全球领军企业。",
        "max_new": 2,
    },
    {
        "code": "600900",
        "short_name": "长江电力",
        "name": "中国长江电力股份有限公司",
        "industry": "公用事业 · 水力发电",
        "industry_l1": "公用事业",
        "industry_l2": "水力发电",
        "exchange": "上交所主板",
        "description": "全球最大的水电上市公司，清洁能源发电与流域梯级调度标杆企业。",
        "max_new": 2,
    },
]

INCLUDE_KEYWORDS = (
    "可持续发展报告",
    "环境、社会及管治",
    "环境、社会与管治",
    "环境、社会及治理",
    "环境、社会与治理",
    "环境、社会和公司治理",
    "ESG报告",
    "ESG暨可持续发展报告",
    "社会责任报告",
    "企业社会责任",
)

EXCLUDE_KEYWORDS = (
    "英文",
    "English",
    "ENGLISH",
    "摘要",
    "审核意见",
    "审验声明",
    "鉴证报告",
    "核查声明",
    "议案",
    "制度",
    "细则",
    "指引",
    "更正",
    "补充",
    "取消",
    "提示性公告",
    "半年度",
    "年半年度",
    "H股公告",
    "海外监管",
)


def load_existing_company_years() -> Set[Tuple[str, int]]:
    existing: Set[Tuple[str, int]] = set()
    if not DB_PATH.exists():
        return existing
    conn = sqlite3.connect(str(DB_PATH))
    for code, yr in conn.execute("SELECT company_code, year FROM reports"):
        existing.add((str(code), int(yr)))
    conn.close()
    return existing


def fetch_org_id_map(session: requests.Session) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    try:
        resp = session.get("https://www.cninfo.com.cn/new/data/szse_stock.json", headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            for item in resp.json().get("stockList", []):
                code = str(item.get("code") or "").strip()
                org_id = str(item.get("orgId") or "").strip()
                if code and org_id:
                    mapping[code] = org_id
    except Exception as e:
        print(f"[WARN] szse_stock.json 批量映射获取异常: {e}")
    return mapping


def lookup_org_id_fallback(session: requests.Session, code: str) -> Optional[str]:
    try:
        resp = session.post(
            "https://www.cninfo.com.cn/new/information/topSearch/query",
            headers=HEADERS,
            data={"keyWord": code, "maxNum": 10},
            timeout=12,
        )
        if resp.status_code == 200:
            for item in resp.json():
                if str(item.get("code")) == code and item.get("orgId"):
                    return str(item["orgId"])
    except Exception as e:
        print(f"[WARN] topSearch 查询 {code} 失败: {e}")
    return None


def infer_report_year(clean_title: str, ann_time_ms: Optional[int]) -> Optional[int]:
    m = re.search(r"(202[2-6])\s*年", clean_title)
    if m:
        return int(m.group(1))
    m2 = re.search(r"(202[2-6])", clean_title)
    if m2:
        return int(m2.group(1))
    if ann_time_ms:
        pub_dt = datetime.fromtimestamp(ann_time_ms / 1000.0)
        if pub_dt.month <= 9:
            return pub_dt.year - 1
        return pub_dt.year
    return None


def is_valid_esg_announcement(clean_title: str, adjunct_url: str, adjunct_size_kb: int) -> bool:
    if not adjunct_url or not adjunct_url.lower().endswith(".pdf"):
        return False
    if not any(k in clean_title for k in INCLUDE_KEYWORDS):
        return False
    if any(bad in clean_title for bad in EXCLUDE_KEYWORDS):
        return False
    # 过滤小于 300KB 的简短公告或大于 65MB 的超大原图画册
    if adjunct_size_kb and (adjunct_size_kb < 300 or adjunct_size_kb > 66560):
        return False
    return True


def query_company_esg_announcements(
    session: requests.Session, code: str, org_id: str
) -> List[Dict]:
    column = "sse" if code.startswith("6") else "szse"
    seen_ids = set()
    candidates = []

    for kw in ("可持续发展", "ESG", "社会责任", "环境"):
        payload = {
            "pageNum": 1,
            "pageSize": 30,
            "column": column,
            "tabName": "fulltext",
            "plate": "",
            "stock": f"{code},{org_id}",
            "searchkey": kw,
            "secid": "",
            "category": "",
            "trade": "",
            "seDate": "2023-01-01~2026-10-27",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "false",
        }
        try:
            resp = session.post(
                "https://www.cninfo.com.cn/new/hisAnnouncement/query",
                headers=HEADERS,
                data=payload,
                timeout=15,
            )
            if resp.status_code != 200:
                continue
            anns = resp.json().get("announcements") or []
            for ann in anns:
                ann_id = ann.get("announcementId") or ann.get("adjunctUrl")
                if ann_id in seen_ids:
                    continue
                seen_ids.add(ann_id)

                raw_title = str(ann.get("announcementTitle") or "")
                clean_title = re.sub(r"<[^>]+>", "", raw_title).strip()
                adjunct_url = str(ann.get("adjunctUrl") or "").strip()
                adjunct_size = int(ann.get("adjunctSize") or 0)

                if not is_valid_esg_announcement(clean_title, adjunct_url, adjunct_size):
                    continue

                yr = infer_report_year(clean_title, ann.get("announcementTime"))
                if yr not in (2022, 2023, 2024, 2025):
                    continue

                candidates.append({
                    "year": yr,
                    "title": clean_title,
                    "adjunct_url": adjunct_url,
                    "adjunct_size_kb": adjunct_size,
                    "announcement_time": ann.get("announcementTime") or 0,
                })
        except Exception as e:
            print(f"[WARN] 检索 {code} ({kw}) 异常: {e}")
        time.sleep(0.15)

    # 若沪市代码在 sse 栏目未命中，兜底检索全市场 szse 统一索引
    if not candidates and column == "sse":
        for kw in ("可持续发展", "ESG", "社会责任"):
            payload = {
                "pageNum": 1,
                "pageSize": 30,
                "column": "szse",
                "tabName": "fulltext",
                "plate": "",
                "stock": f"{code},{org_id}",
                "searchkey": kw,
                "seDate": "2023-01-01~2026-10-27",
                "isHLtitle": "false",
            }
            try:
                resp = session.post(
                    "https://www.cninfo.com.cn/new/hisAnnouncement/query",
                    headers=HEADERS,
                    data=payload,
                    timeout=15,
                )
                if resp.status_code == 200:
                    for ann in resp.json().get("announcements") or []:
                        ann_id = ann.get("announcementId") or ann.get("adjunctUrl")
                        if ann_id in seen_ids:
                            continue
                        seen_ids.add(ann_id)
                        clean_title = re.sub(r"<[^>]+>", "", str(ann.get("announcementTitle") or "")).strip()
                        adjunct_url = str(ann.get("adjunctUrl") or "").strip()
                        adjunct_size = int(ann.get("adjunctSize") or 0)
                        if not is_valid_esg_announcement(clean_title, adjunct_url, adjunct_size):
                            continue
                        yr = infer_report_year(clean_title, ann.get("announcementTime"))
                        if yr in (2022, 2023, 2024, 2025):
                            candidates.append({
                                "year": yr,
                                "title": clean_title,
                                "adjunct_url": adjunct_url,
                                "adjunct_size_kb": adjunct_size,
                                "announcement_time": ann.get("announcementTime") or 0,
                            })
            except Exception:
                pass

    # 按报告年度降序、发布时间降序排列
    candidates.sort(key=lambda x: (x["year"], x["announcement_time"]), reverse=True)
    return candidates


def verify_and_inspect_pdf(pdf_path: Path, expected_year: int) -> Tuple[bool, int, int]:
    """验证 PDF 完整性、页数、可提取文本层，并核实报告内部真实统计基准年度"""
    try:
        doc = fitz.open(str(pdf_path))
        page_count = doc.page_count
        if page_count < 22:
            doc.close()
            return False, 0, expected_year

        # 抽样前5页与后10页检测是否具备真实可提取文本层（排除纯扫描图片版）
        sample_indices = sorted(set(list(range(min(6, page_count))) + list(range(max(0, page_count - 10), page_count))))
        total_chars = 0
        head_text = ""
        for idx in sample_indices:
            t = doc[idx].get_text("text") or ""
            total_chars += len(t.strip())
            if idx < 5:
                head_text += "\n" + t
        doc.close()

        if total_chars < 1200:
            return False, page_count, expected_year

        # 核查报告时间范围描述，例如 "2024年1月1日至2024年12月31日"
        period_match = re.search(
            r"(202[2-5])\s*年\s*1\s*月\s*1\s*日\s*(?:至|—|-|~|到)\s*(202[2-5])\s*年\s*12\s*月\s*31\s*日",
            head_text,
        )
        actual_year = expected_year
        if period_match and period_match.group(1) == period_match.group(2):
            actual_year = int(period_match.group(1))

        return True, page_count, actual_year
    except Exception as e:
        print(f"[WARN] PDF 校验失败 ({pdf_path.name}): {e}")
        return False, 0, expected_year


def download_pdf(session: requests.Session, adjunct_url: str, dest_path: Path, max_mb: int = 65) -> bool:
    for scheme in ("https", "http"):
        url = f"{scheme}://static.cninfo.com.cn/{adjunct_url.lstrip('/')}"
        try:
            with session.get(url, headers=PDF_HEADERS, stream=True, timeout=45) as r:
                if r.status_code != 200:
                    continue
                cl = int(r.headers.get("Content-Length") or 0)
                if cl > max_mb * 1024 * 1024:
                    print(f"   -> 跳过超大文件 ({cl / 1024 / 1024:.1f} MB > {max_mb} MB)")
                    return False

                total = 0
                first_chunk = b""
                tmp_path = dest_path.with_suffix(".part")
                with open(tmp_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=256 * 1024):
                        if not chunk:
                            continue
                        if not first_chunk:
                            first_chunk = chunk[:8]
                        total += len(chunk)
                        if total > max_mb * 1024 * 1024:
                            tmp_path.unlink(missing_ok=True)
                            return False
                        f.write(chunk)

                if total < 300 * 1024 or not first_chunk.startswith(b"%PDF-"):
                    tmp_path.unlink(missing_ok=True)
                    continue

                tmp_path.replace(dest_path)
                return True
        except Exception as e:
            print(f"   -> 下载异常 ({url}): {e}")
    return False


def main():
    existing_pairs = load_existing_company_years()
    print(f"当前数据库已收录报告数: {len(existing_pairs)} 份")

    session = requests.Session()
    org_map = fetch_org_id_map(session)
    print(f"已加载巨潮股票映射表: {len(org_map)} 条")

    downloaded_records = []
    max_total_downloads = 24

    for comp in TARGET_COMPANIES:
        if len(downloaded_records) >= max_total_downloads:
            break

        code = comp["code"]
        short_name = comp["short_name"]
        org_id = org_map.get(code) or lookup_org_id_fallback(session, code)
        if not org_id:
            print(f"[SKIP] 未找到 {code} {short_name} 的巨潮 orgId")
            continue

        print(f"\n正在检索 [{code}] {short_name} (orgId={org_id})...")
        anns = query_company_esg_announcements(session, code, org_id)
        print(f"   -> 找到 {len(anns)} 条候选年度 ESG/可持续发展报告公告")

        added_for_comp = 0
        covered_years_for_comp = {yr for (c, yr) in existing_pairs if c == code}

        for ann in anns:
            if added_for_comp >= comp["max_new"] or len(downloaded_records) >= max_total_downloads:
                break

            cand_year = ann["year"]
            if cand_year in covered_years_for_comp:
                continue

            safe_filename = f"{short_name}{cand_year}年度可持续发展报告.pdf"
            dest_path = REPORTS_DIR / safe_filename

            print(f"   -> 下载候选: [{cand_year}] {ann['title']} ({ann['adjunct_size_kb']} KB)")
            ok = download_pdf(session, ann["adjunct_url"], dest_path)
            if not ok:
                continue

            valid, pages, actual_year = verify_and_inspect_pdf(dest_path, cand_year)
            if not valid:
                print(f"   -> 丢弃无效或纯扫描版 PDF: {dest_path.name}")
                dest_path.unlink(missing_ok=True)
                continue

            if actual_year in covered_years_for_comp:
                print(f"   -> 报告内部基准年为 {actual_year}，库中已存在，跳过重复")
                dest_path.unlink(missing_ok=True)
                continue

            if actual_year != cand_year:
                final_filename = f"{short_name}{actual_year}年度可持续发展报告.pdf"
                final_path = REPORTS_DIR / final_filename
                dest_path.replace(final_path)
                dest_path = final_path

            size_mb = round(dest_path.stat().st_size / (1024 * 1024), 2)
            official_title = ann["title"]
            if not official_title.startswith(short_name) and comp["name"][:2] not in official_title:
                official_title = f"{short_name}：{official_title}"

            rec = {
                "code": code,
                "short_name": short_name,
                "company_name": comp["name"],
                "industry": comp["industry"],
                "industry_l1": comp["industry_l1"],
                "industry_l2": comp["industry_l2"],
                "exchange": comp["exchange"],
                "description": comp["description"],
                "year": actual_year,
                "title": official_title,
                "pdf_filename": dest_path.name,
                "total_pages": pages,
                "size_mb": size_mb,
                "cninfo_url": f"https://static.cninfo.com.cn/{ann['adjunct_url'].lstrip('/')}",
            }
            downloaded_records.append(rec)
            covered_years_for_comp.add(actual_year)
            existing_pairs.add((code, actual_year))
            added_for_comp += 1
            print(f"   [OK] 已保存: {dest_path.name} ({pages} 页, {size_mb} MB, 基准年={actual_year})")
            time.sleep(0.3)

    MANIFEST_PATH.write_text(
        json.dumps(downloaded_records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("\n" + "=" * 60)
    print(f"巨潮资讯网下载完成！成功新增 {len(downloaded_records)} 份官方原版 PDF 报告")
    print(f"清单已保存至: {MANIFEST_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
