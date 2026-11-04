import json
from typing import Dict, Any, List, Optional
import config
from core.pdf_parser import PDFParser
from core.llm_client import LLMClient
from core.rules_engine import RulesEngine

class ESGExtractor:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    def process_report(self, pdf_path: str, progress_callback=None) -> Dict[str, Any]:
        """
        处理单份 ESG 报告的完整端到端审阅链路
        """
        if progress_callback:
            progress_callback(10, "正在深度解析 PDF 页面结构与排版...")
            
        parser = PDFParser(pdf_path)
        basic_info = parser.extract_basic_info()
        
        if progress_callback:
            progress_callback(30, f"已识别: {basic_info['company_name']} ({basic_info['report_year']}年度)，正在智能定位关键数据页...")

        # 1. 智能定位关键候选页（优先保障报告后部关键绩效附表页不被截断！）
        kpi_pages = parser.find_kpi_summary_pages()
        assurance_pages = parser.find_candidate_pages(["鉴证", "审验", "AA1000", "ISAE 3000", "独立声明"], max_pages=2)
        intro_pages = [p for p in [1, 2] if p <= parser.total_pages]

        priority_pages = []
        for p in kpi_pages + assurance_pages + intro_pages:
            if 1 <= p <= parser.total_pages and p not in priority_pages:
                priority_pages.append(p)

        # 针对每个指标补充专有候选页，填满最多 14 页预算
        for ind in config.INDICATORS:
            if len(priority_pages) >= 14:
                break
            cands = parser.find_candidate_pages(ind["keywords"][:3], max_pages=1)
            for p in cands:
                if 1 <= p <= parser.total_pages and p not in priority_pages:
                    priority_pages.append(p)
                    if len(priority_pages) >= 14:
                        break

        target_pages = sorted(priority_pages)
        kpi_page_set = set(kpi_pages)

        if progress_callback:
            progress_callback(50, f"已截取 {len(target_pages)} 个核心数据页（含绩效附表页），正在结构化提取 27 项核心指标...")

        # 2. 组装输入上下文（对关键绩效附表页放宽字符上限以防表格截断）
        context_blocks = []
        for p in target_pages:
            p_text = parser.get_page_text(p).strip()
            max_chars = 4800 if p in kpi_page_set else 3000
            if len(p_text) > max_chars:
                p_text = p_text[:max_chars] + "\n...[页面文本过长截断]"
            tag = "（关键绩效附表页）" if p in kpi_page_set else ""
            context_blocks.append(f"--- 【报告第 {p} 页{tag}】 ---\n{p_text}")
        
        context_str = "\n\n".join(context_blocks)

        # 3. 构建完整 27 项指标提取 Prompt
        indicators_desc = []
        for ind in config.INDICATORS:
            indicators_desc.append(
                f"- {ind['code']}: {ind['name']} (指引条款: {ind['clause']}，标准单位: {ind['standard_unit']})\n  定位关键词: {','.join(ind['keywords'][:5])}"
            )
        indicators_str = "\n".join(indicators_desc)

        prompt = f"""
你是一名资深 A 股上市公司可持续发展（ESG）报告审计与数据专家。请基于下方提供的真实报告页面文本（优先查阅标注为“关键绩效附表页”的附录汇总表，未包含项再从正文页查找），准确提取全部 {len(config.INDICATORS)} 项核心指标的数据与原文证据。

【报告预识别基础信息】：
- 候选公司名称：{basic_info['company_name']}
- 候选股票代码：{basic_info.get('company_code') or '待识别'}
- 候选基准年度：{basic_info['report_year']}

【需提取的 {len(config.INDICATORS)} 项核心指标清单】：
{indicators_str}

【严格提取规范】：
1. 严禁编造或猜测任何数值！原文未披露的指标，必须将 value 设为 null，status 设为 "未披露"。
2. 范围2间接排放必须区分：Q03A（基于位置法 Location-based）与 Q03B（基于市场法 Market-based）；若报告仅披露单一“范围2排放”且未注明市场法绿电抵扣，默认填入 Q03A，Q03B 标为 "未披露"。
3. 每个已披露指标必须给出与该页原文一致的原句或表格行文本 quote，以及准确的报告页码 page（整数）。
4. 区分报告当期实际值与未来规划目标值：除 Q07（减排目标年份填入 value，如 2030）外，其余定量指标均提取报告基准年度（{basic_info['report_year']}年）当期实际数据。
5. 复合型指标提取约定：
   - Q15（清洁能源）：value 填使用量数值，unit 填原单位，ratio_pct 填占比数字（不含%号）；
   - Q21（研发投入）：value 填投入金额数值，unit 填原单位（如亿元/万元），ratio_pct 填占营收比例；
   - Q22（研发人员）：value 填人数，unit 填 "人"，ratio_pct 填占总员工比例；
   - Q25（员工总数）：value 填总人数，unit 填 "人"，female_ratio_pct 填女性员工占比；
   - Q27（安全事故）：value 填安全事故起数或因工死亡人数（若明确零事故/零死亡则填 0），unit 填 "起/人"；
   - Q30（第三方独立鉴证）：is_assured 填 true/false，value 填 1（有鉴证）或 0（无鉴证），agency 填审验机构名，standard 填审验标准（如 AA1000 / ISAE 3000）；
   - Q32（董事会构成）：value 填董事会总人数，unit 填 "人"，ratio_pct 填独立董事占比数字（不含%号）。

【报告候选页面原文】：
{context_str}

请仅输出严格合法的 JSON 对象（包含全部 {len(config.INDICATORS)} 个指标键 Q01~Q32）：
{{
  "company_name": "识别到的上市公司全称",
  "company_code": "6位A股代码或null",
  "report_year": {basic_info['report_year']},
  "indicators": {{
    "Q01": {{"value": 数值或null, "unit": "原单位", "year": {basic_info['report_year']}, "page": 页码整数, "quote": "原文精确片段", "status": "已披露/未披露"}},
    "Q02": {{"value": 数值或null, "unit": "原单位", "year": {basic_info['report_year']}, "page": 页码整数, "quote": "原文精确片段", "status": "已披露/未披露"}},
    "Q03A": {{"value": 数值或null, "unit": "原单位", "year": {basic_info['report_year']}, "page": 页码整数, "quote": "原文精确片段", "status": "已披露/未披露"}},
    "Q03B": {{"value": 数值或null, "unit": "原单位", "year": {basic_info['report_year']}, "page": 页码整数, "quote": "原文精确片段", "status": "已披露/未披露"}},
    "Q07": {{"value": 目标年份整数或null, "unit": "目标年", "base_year": 基准年或null, "target_year": 目标年或null, "target_val": "减排目标描述", "page": 页码整数, "quote": "原文精确片段", "status": "已披露/未披露"}},
    "Q30": {{"value": 1或0, "unit": "类别字段", "is_assured": true或false, "agency": "机构名称", "standard": "鉴证标准", "page": 页码整数, "quote": "原文精确片段", "status": "已披露/未披露"}}
  }}
}}
"""
        system_instruction = "你是一名严谨的上市公司可持续发展报告数据提取引擎。只输出合法的 JSON 对象，不要包含 Markdown 代码块包裹或任何额外解释。"
        
        raw_result = self.llm.call_json(prompt, system_instruction, basic_info=basic_info, parser=parser)

        if progress_callback:
            progress_callback(80, "指标抽取完成，正在执行原文逐字证据链核验与标准单位换算...")

        # 4. 后处理：逐字证据链校验与规则换算
        extracted_indicators = raw_result.get("indicators", {})
        # 兼容旧版单键 Q03 自动回退至 Q03A
        if "Q03" in extracted_indicators and "Q03A" not in extracted_indicators:
            extracted_indicators["Q03A"] = extracted_indicators["Q03"]

        processed_table = []
        audit_input_dict = {}

        for ind in config.INDICATORS:
            code = ind["code"]
            data = extracted_indicators.get(code, {}) or {}
            
            raw_val = data.get("value")
            if code == "Q07" and raw_val is None and data.get("target_year"):
                raw_val = data.get("target_year")
            if code == "Q30" and raw_val is None and "is_assured" in data:
                raw_val = 1.0 if data.get("is_assured") else 0.0

            raw_unit = data.get("unit", "")
            page_num = data.get("page") or 0
            try:
                page_num = int(page_num)
            except (ValueError, TypeError):
                page_num = 0
            quote = data.get("quote", "") or ""
            status = data.get("status") or ("已披露" if raw_val is not None else "未披露")
            
            # 原文片段核验
            verified = False
            if quote and page_num:
                verified = parser.verify_quote_in_page(quote, page_num)
            
            # 标准单位换算
            if code == "Q30":
                std_val = 1.0 if (data.get("is_assured") or raw_val == 1) else 0.0
                std_unit = "类别字段"
                conv_note = f"{data.get('agency') or '独立审验'} ({data.get('standard') or '鉴证声明'})".strip() if std_val == 1.0 else "未附第三方独立鉴证"
            else:
                std_val, std_unit, conv_note = RulesEngine.standardize_unit(code, raw_val, raw_unit)
                if code == "Q07" and data.get("target_val"):
                    conv_note = str(data.get("target_val"))
            
            item_row = {
                "code": code,
                "name": ind["name"],
                "dimension": ind["dimension"],
                "clause": ind["clause"],
                "raw_value": raw_val,
                "raw_unit": raw_unit,
                "std_value": std_val,
                "std_unit": std_unit or ind["standard_unit"],
                "conv_note": conv_note,
                "data_year": data.get("year", basic_info["report_year"]),
                "page": page_num,
                "quote": quote,
                "verified_in_page": verified,
                "status": status,
                "ratio_pct": data.get("ratio_pct") or data.get("female_ratio_pct"),
                "is_assured": bool(data.get("is_assured", False) or (code == "Q30" and std_val == 1.0)),
                "agency": data.get("agency", ""),
                "standard": data.get("standard", ""),
                "target_year": data.get("target_year"),
                "target_val": data.get("target_val")
            }
            
            processed_table.append(item_row)
            audit_input_dict[code] = {
                "name": ind["name"],
                "std_val": std_val,
                "status": status,
                "verified_in_page": verified,
                "page": page_num,
                "is_assured": item_row["is_assured"],
                "agency": data.get("agency", ""),
                "standard": data.get("standard", ""),
                "ratio_pct": item_row["ratio_pct"]
            }

        if progress_callback:
            progress_callback(95, "正在执行跨指标勾稽关系与合规一致性检测...")

        # 5. 跨指标一致性核查
        anomalies = RulesEngine.audit_consistency(audit_input_dict)

        # 6. 计算整体摘要统计
        disclosed_count = sum(1 for row in processed_table if "已披露" in str(row["status"]) and row["raw_value"] is not None)
        verified_count = sum(1 for row in processed_table if row["verified_in_page"])
        total_count = len(processed_table)
        
        summary = {
            "company_name": raw_result.get("company_name") or basic_info["company_name"],
            "company_code": raw_result.get("company_code") or basic_info.get("company_code"),
            "report_year": raw_result.get("report_year") or basic_info["report_year"],
            "total_pages": parser.total_pages,
            "target_pages_analyzed": target_pages,
            "disclosed_count": disclosed_count,
            "undisclosed_count": total_count - disclosed_count,
            "disclosure_rate": f"{round(disclosed_count / total_count * 100, 1)}%",
            "verified_count": verified_count,
            "verification_rate": f"{round(verified_count / max(1, disclosed_count) * 100, 1)}%",
            "anomalies_count": len([a for a in anomalies if a["level"] in ["WARNING", "ERROR"]])
        }

        if progress_callback:
            progress_callback(100, "审阅与核查全部完成！")

        return {
            "summary": summary,
            "indicators": processed_table,
            "anomalies": anomalies
        }
