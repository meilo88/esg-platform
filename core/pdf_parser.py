import re
import unicodedata
import fitz
from typing import Dict, List, Any, Optional

class PDFParser:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.pages_text: List[str] = []
        with fitz.open(pdf_path) as doc:
            self.total_pages = len(doc)
            for i in range(self.total_pages):
                self.pages_text.append(doc[i].get_text())

    def extract_basic_info(self) -> Dict[str, Any]:
        """识别公司名称、股票代码和报告基准年度"""
        first_pages_text = "\n".join(self.pages_text[:min(6, self.total_pages)])
        
        # 提取年份，优先寻找如 2024年度、2024 可持续发展报告
        year_match = re.search(r"(202[0-9])\s*(?:年度|年)?\s*(?:可持续发展|环境、社会|ESG|社会责任)", first_pages_text)
        if not year_match:
            year_match = re.search(r"(202[0-9])\s*年度", first_pages_text)
        report_year = int(year_match.group(1)) if year_match else 2024
        
        # 提取 A 股 6 位股票代码
        company_code = None
        code_patterns = [
            r"(?:股票代码|证券代码|A股代码|股份代码)[：:\s]*([0368]\d{5})\b",
            r"\b([0368]\d{5})\.(?:SZ|SH|BJ)\b"
        ]
        for cpat in code_patterns:
            cm = re.search(cpat, first_pages_text, re.IGNORECASE)
            if cm:
                company_code = cm.group(1)
                break

        # 提取公司名称
        company_name = "未知公司"
        company_patterns = [
            r"([\u4e00-\u9fa5（）()]{2,22}(?:股份有限公司|科技股份有限公司|精密工业股份有限公司|集团股份有限公司|新能源科技股份有限公司))",
            r"([\u4e00-\u9fa5]{2,14}(?:股份|精密|科技|重工|电子|制造|汽车|钢铁))"
        ]
        for pat in company_patterns:
            m = re.search(pat, first_pages_text)
            if m:
                cand = m.group(1).strip()
                # 排除监管机构等干扰词
                if not any(bad in cand for bad in ["证券交易所", "证监会"]):
                    company_name = cand
                    break

        return {
            "company_name": company_name,
            "company_code": company_code,
            "report_year": report_year,
            "total_pages": self.total_pages
        }

    def find_kpi_summary_pages(self) -> List[int]:
        """定位报告结尾附录及核心关键绩效数据附表页面（通常集中了80%以上的定量指标）"""
        kpi_keywords = [
            "关键绩效数据", "关键绩效指标", "环境绩效表", "社会绩效表",
            "ESG绩效表", "关键定量数据", "绩效数据表", "环境关键绩效", "治理绩效", "定量绩效"
        ]
        scored_pages = []
        appendix_threshold = max(1, int(self.total_pages * 0.65))
        for i, text in enumerate(self.pages_text):
            page_no = i + 1
            kw_hits = sum(1 for kw in kpi_keywords if kw in text)
            # 统计页面内的定量指标常见单位密度
            unit_hits = sum(text.count(u) for u in ["吨二氧化碳", "tCO2e", "兆瓦时", "MWh", "吨标准煤", "危险废物", "研发投入", "员工总"])
            score = kw_hits * 20 + (min(unit_hits, 15) * 3 if (kw_hits > 0 or page_no >= appendix_threshold) else 0)
            if page_no >= appendix_threshold and score > 0:
                score += 15  # 报告后部附录表格优先加权
            if score >= 20:
                scored_pages.append((page_no, score))

        scored_pages.sort(key=lambda x: x[1], reverse=True)
        return [p for p, _ in scored_pages[:6]]

    def find_candidate_pages(self, keywords: List[str], max_pages: int = 4) -> List[int]:
        """按指标关键词检索最匹配的候选页面（1-indexed）"""
        scores = []
        for i, text in enumerate(self.pages_text):
            score = 0
            for kw in keywords:
                # 关键词匹配加权
                count = text.count(kw)
                if count > 0:
                    score += count * (5 if len(kw) > 3 else 2)
            if score > 0:
                # 关键绩效附表页面额外加权
                if any(kpi_kw in text for kpi_kw in ["关键绩效", "绩效表", "附录"]):
                    score += 15
                scores.append((i + 1, score))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return [p for p, s in scores[:max_pages]]

    def get_page_text(self, page_num: int) -> str:
        """获取指定页面的完整文本（1-indexed）"""
        if 1 <= page_num <= self.total_pages:
            return self.pages_text[page_num - 1]
        return ""

    def verify_quote_in_page(self, quote: str, page_num: int) -> bool:
        """
        核心防幻觉算法：
        校验模型返回的原文片段（evidence quote）是否确实存在于指定页面的文本中。
        支持空格标点归一化、自动去除角标/脚注数字、多行关键短语段落核对。
        """
        if not quote or not (1 <= page_num <= self.total_pages):
            return False
        
        page_text = self.pages_text[page_num - 1]
        
        def clean_str(s: str) -> str:
            norm = unicodedata.normalize('NFKC', s)
            return re.sub(r"[\s\u3000\xa0\n\r\t，。；：、（）()]+", "", norm).lower()
        
        cleaned_quote = clean_str(quote)
        cleaned_page = clean_str(page_text)
        
        if not cleaned_quote:
            return False
            
        # 1. 严格子串直接匹配
        if cleaned_quote in cleaned_page:
            return True
            
        # 2. 自动移除角标/脚注数字模式 (如 '总取水量6' -> '总取水量')
        c_page_no_footnote = re.sub(r"([^\d])\d{1,2}(?=[^\d]|$)", r"\1", cleaned_page)
        c_quote_no_footnote = re.sub(r"([^\d])\d{1,2}(?=[^\d]|$)", r"\1", cleaned_quote)
        if c_quote_no_footnote in c_page_no_footnote:
            return True
            
        # 3. 分行或分词段落校验：若引用的各有效词元（如指标名、数值）均在页内出现
        lines = [clean_str(line) for line in quote.splitlines() if len(clean_str(line)) >= 2]
        if len(lines) >= 2 and all(line in cleaned_page for line in lines):
            return True

        tokens = [clean_str(t) for t in re.split(r"[\s\n\r|/：:]+", quote) if len(clean_str(t)) >= 2]
        if len(tokens) >= 2 and all(tok in cleaned_page for tok in tokens):
            return True
            
        # 4. 前后子串容错（针对超长引文）
        if len(cleaned_quote) > 20:
            if cleaned_quote[:15] in cleaned_page and cleaned_quote[-15:] in cleaned_page:
                return True
                
        return False
