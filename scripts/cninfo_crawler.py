import os
import sys
import time
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE_DIR / "esg报告"
REPORTS_DIR.mkdir(exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'X-Requested-With': 'XMLHttpRequest'
}

# 申万行业标准映射表 (申万一级 -> 申万二级 -> 代表企业)
SHENWAN_INDUSTRY_MAP = {
    "002241": ("电子", "消费电子", "歌尔股份有限公司"),
    "002475": ("电子", "消费电子", "立讯精密工业股份有限公司"),
    "601138": ("电子", "消费电子", "富士康工业互联网股份有限公司"),
    "002600": ("电子", "消费电子", "广东领益智造股份有限公司"),
    "300433": ("电子", "消费电子", "蓝思科技股份有限公司"),
    "002938": ("电子", "元件", "鹏鼎控股（深圳）股份有限公司"),
    "601231": ("电子", "消费电子", "环旭电子股份有限公司"),
    "300782": ("电子", "半导体", "江苏卓胜微电子股份有限公司"),
    
    "300750": ("电力设备", "电池", "宁德时代新能源科技股份有限公司"),
    "600019": ("钢铁", "普钢", "宝山钢铁股份有限公司"),
    "002594": ("汽车", "乘用车", "比亚迪股份有限公司")
}

def search_cninfo_reports(keyword: str, page_num: int = 1, page_size: int = 10) -> List[Dict[str, Any]]:
    """查询巨潮资讯网官方披露报告"""
    url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
    data = {
        'searchkey': keyword,
        'tabName': 'fulltext',
        'pageSize': page_size,
        'pageNum': page_num,
        'column': 'szse',
        'plate': '',
        'secid': '',
        'category': '',
        'trade': '',
        'seDate': ''
    }
    try:
        r = requests.post(url, headers=HEADERS, data=data, timeout=12)
        if r.status_code == 200:
            res = r.json()
            return res.get('announcements') or []
    except Exception as e:
        print(f"查询巨潮资讯网失败: {e}")
    return []

def download_cninfo_pdf(adjunct_url: str, target_filename: str) -> Optional[str]:
    """从巨潮资讯网静态存储下载 PDF"""
    if not adjunct_url.startswith("http"):
        pdf_url = f"http://static.cninfo.com.cn/{adjunct_url}"
    else:
        pdf_url = adjunct_url

    target_path = REPORTS_DIR / target_filename
    if target_path.exists() and target_path.stat().st_size > 1024 * 50:
        print(f"文件已存在，跳过下载: {target_filename} ({target_path.stat().st_size / 1024 / 1024:.2f} MB)")
        return str(target_path)

    print(f"正在从巨潮资讯网下载: {pdf_url} -> {target_filename} ...")
    try:
        r = requests.get(pdf_url, headers=HEADERS, stream=True, timeout=60)
        if r.status_code == 200:
            with open(target_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
            size_mb = target_path.stat().st_size / (1024 * 1024)
            print(f"下载成功: {target_filename} ({size_mb:.2f} MB)")
            return str(target_path)
        else:
            print(f"下载失败，HTTP状态码: {r.status_code}")
    except Exception as e:
        print(f"下载异常: {e}")
    return None

if __name__ == "__main__":
    print("=== 巨潮资讯网 (cninfo) 电子制造行业可持续发展报告爬取工具 ===")
    
    # 待批量下载的权威电子制造业 ESG / 可持续发展报告清单
    target_tasks = [
        {
            "code": "601138",
            "name": "工业富联",
            "year": 2025,
            "title": "富士康工业互联网股份有限公司2025年可持续发展报告",
            "url": "finalpage/2026-04-29/1225231683.PDF",
            "filename": "工业富联2025年可持续发展报告.pdf"
        },
        {
            "code": "002938",
            "name": "鹏鼎控股",
            "year": 2025,
            "title": "鹏鼎控股（深圳）股份有限公司2025年可持续发展报告",
            "url": "finalpage/2026-03-31/1225062312.PDF",
            "filename": "鹏鼎控股2025年可持续发展报告.pdf"
        },
        {
            "code": "300433",
            "name": "蓝思科技",
            "year": 2024,
            "title": "蓝思科技2024年度可持续发展报告",
            "url": "finalpage/2025-03-28/1222928876.PDF",
            "filename": "蓝思科技2024年度可持续发展报告.pdf"
        }
    ]

    for t in target_tasks:
        download_cninfo_pdf(t["url"], t["filename"])
        time.sleep(1)

    print("\n所有指定报告下载处理完成！")
