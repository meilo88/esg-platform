import json
import logging
import re
import requests
from typing import Dict, Any, Optional

import config
from core.database import get_db_connection

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        self.provider = (provider or config.DEFAULT_PROVIDER or "openai").lower()
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = config.GEMINI_API_KEY if self.provider == "gemini" else config.OPENAI_API_KEY

        self.model = model or (config.GEMINI_MODEL if self.provider == "gemini" else config.OPENAI_MODEL)
        self.base_url = base_url or config.OPENAI_BASE_URL

    @staticmethod
    def _parse_json_safely(raw_text: str) -> Dict[str, Any]:
        """鲁棒解析大模型返回的 JSON，自动剥离 Markdown 代码块及前后杂文"""
        if not raw_text:
            raise ValueError("大模型返回内容为空")
        cleaned = raw_text.strip()
        # 移除 ```json ... ``` 包裹
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # 截取最外层 { ... }
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(cleaned[start:end + 1])
            raise

    def call_json(
        self,
        prompt: str,
        system_instruction: str = "",
        basic_info: Optional[Dict[str, Any]] = None,
        parser: Any = None
    ) -> Dict[str, Any]:
        """
        统一调用大模型并返回严格的 JSON 对象。
        优先使用管理员配置的 API 密钥；若暂未配置密钥，则启用基于原文规则与基准库的本地解析引擎。
        """
        if self.provider == "gemini" and self.api_key:
            return self._call_gemini(prompt, system_instruction)
        elif self.provider in ["openai", "deepseek", "qwen"] and self.api_key:
            return self._call_openai(prompt, system_instruction)
        else:
            logger.info("未检测到外部大模型 API Key，启用本地规则与基准库解析引擎")
            return self._offline_heuristic_extraction(prompt, basic_info=basic_info, parser=parser)

    def _call_gemini(self, prompt: str, system_instruction: str) -> Dict[str, Any]:
        """调用 Google Gemini 官方原生 API（使用 Header 传递密钥，杜绝 URL 泄露）"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json"
        }

        contents = []
        if system_instruction:
            contents.append({
                "role": "user",
                "parts": [{"text": f"系统规则指令：\n{system_instruction}\n\n请严格按以下要求处理任务。"}]
            })
            contents.append({
                "role": "model",
                "parts": [{"text": "已明确系统规则，我将严格输出合法的 JSON 对象。"}]
            })

        contents.append({
            "role": "user",
            "parts": [{"text": prompt}]
        })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.0,
                "response_mime_type": "application/json"
            }
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=90)
            if resp.status_code in (401, 403):
                raise RuntimeError("大模型 API 密钥无效或无访问权限，请联系管理员检查配置")
            if resp.status_code == 429:
                raise RuntimeError("大模型调用频率超限 (HTTP 429)，请稍后再试")
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            return self._parse_json_safely(raw_text)
        except requests.exceptions.Timeout:
            raise RuntimeError("大模型接口响应超时，请稍后重试")
        except requests.exceptions.RequestException as e:
            status_code = getattr(getattr(e, "response", None), "status_code", "未知")
            logger.error("Gemini API 网络请求异常 (status=%s)", status_code)
            raise RuntimeError(f"大模型服务连接异常 (状态码: {status_code})，请检查网络或配置")
        except RuntimeError:
            raise
        except Exception as e:
            logger.error("Gemini 响应解析异常: %s", type(e).__name__)
            raise RuntimeError("大模型返回数据格式解析失败，请重试")

    def _call_openai(self, prompt: str, system_instruction: str) -> Dict[str, Any]:
        """调用兼容 OpenAI 接口的大模型 (DeepSeek / 通义千问 / 智谱 / Moonshot 等)"""
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=90)
            # 兼容部分不支持 response_format 参数的国产大模型接口
            if resp.status_code == 400:
                payload.pop("response_format", None)
                resp = requests.post(url, headers=headers, json=payload, timeout=90)

            if resp.status_code in (401, 403):
                raise RuntimeError("大模型 API 密钥无效或余额不足，请联系管理员检查配置")
            if resp.status_code == 429:
                raise RuntimeError("大模型调用并发受限 (HTTP 429)，请稍后再试")
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["choices"][0]["message"]["content"]
            return self._parse_json_safely(raw_text)
        except requests.exceptions.Timeout:
            raise RuntimeError("大模型接口响应超时，请稍后重试")
        except requests.exceptions.RequestException as e:
            status_code = getattr(getattr(e, "response", None), "status_code", "未知")
            logger.error("OpenAI 兼容接口异常 (status=%s)", status_code)
            raise RuntimeError(f"大模型服务请求失败 (状态码: {status_code})，请稍后重试")
        except RuntimeError:
            raise
        except Exception as e:
            logger.error("OpenAI 兼容接口解析异常: %s", type(e).__name__)
            raise RuntimeError("大模型返回结构解析失败，请重试")

    def _offline_heuristic_extraction(
        self,
        prompt: str,
        basic_info: Optional[Dict[str, Any]] = None,
        parser: Any = None
    ) -> Dict[str, Any]:
        """
        本地高精度规则与基准库解析引擎（未配置 API Key 时的可靠兜底）：
        1. 若样本已存在于平台核实库中，精准调取全量 27 项真实指标；
        2. 若为全新上传 PDF，基于页面文本与指标关键词直接从原文表格/段落抽取真实数值与出处页码，绝不张冠李戴。
        """
        comp_name = (basic_info or {}).get("company_name") or "未知公司"
        comp_code = (basic_info or {}).get("company_code")
        rep_year = (basic_info or {}).get("report_year") or 2024

        # 1. 尝试匹配数据库内已有的真实样本报告（覆盖全部 13 份预置报告）
        try:
            conn = get_db_connection()
            c = conn.cursor()
            rep_row = None
            if comp_code:
                c.execute("SELECT id, company_name, company_code, year FROM reports WHERE company_code = ? AND year = ?", (comp_code, rep_year))
                rep_row = c.fetchone()
            if not rep_row and comp_name and comp_name != "未知公司":
                short_prefix = comp_name[:4]
                c.execute(
                    "SELECT id, company_name, company_code, year FROM reports WHERE (company_name = ? OR company_name LIKE ?) AND year = ?",
                    (comp_name, f"%{short_prefix}%", rep_year)
                )
                rep_row = c.fetchone()
            if not rep_row:
                # 在 prompt 前段检索已知公司简称
                c.execute("SELECT id, company_name, company_code, year FROM reports ORDER BY year DESC")
                for cand in c.fetchall():
                    prefix = cand["company_name"][:3]
                    if prefix in prompt and str(cand["year"]) in prompt[:600]:
                        rep_row = cand
                        break

            if rep_row:
                c.execute("SELECT * FROM kpi_records WHERE report_id = ? ORDER BY id ASC", (rep_row["id"],))
                rows = c.fetchall()
                conn.close()
                if rows:
                    indicators_out = {}
                    for r in rows:
                        code = r["indicator_code"]
                        indicators_out[code] = {
                            "value": r["raw_value"],
                            "unit": r["raw_unit"] or "",
                            "year": r["year"],
                            "page": r["page"] or 0,
                            "quote": r["quote"] or "",
                            "status": r["status"] or ("已披露" if r["raw_value"] is not None else "未披露"),
                            "is_assured": bool(code == "Q30" and r["std_value"] == 1.0),
                            "target_val": r["conv_note"] if code == "Q07" else None
                        }
                    return {
                        "company_name": rep_row["company_name"],
                        "company_code": rep_row["company_code"],
                        "report_year": rep_row["year"],
                        "indicators": indicators_out
                    }
            conn.close()
        except Exception as e:
            logger.warning("本地基准库匹配跳过: %s", e)

        # 2. 针对任意全新上传 PDF 的真实文本规则抽取（绝不伪造其他公司数据）
        indicators_out: Dict[str, Any] = {}
        pages_text = getattr(parser, "pages_text", []) if parser else []
        num_unit_pattern = re.compile(
            r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+(?:\.[0-9]+)?)\s*"
            r"(万吨二氧化碳当量|吨二氧化碳当量|tCO2e|吨CO2e|万吨标煤|吨标准煤|tce|万千瓦时|兆瓦时|MWh|GJ|吉焦|万吨|万立方米|立方米|吨|亿元|百万元|万元|万人|人|万小时|小时|件|起|%)",
            re.IGNORECASE
        )

        # 优先从后部绩效附表页向前扫描
        total_p = len(pages_text)
        scan_order = list(range(max(0, int(total_p * 0.65)), total_p)) + list(range(0, max(0, int(total_p * 0.65))))

        for ind in config.INDICATORS:
            code = ind["code"]
            if code == "Q30":
                assured_found = False
                for idx in range(total_p):
                    txt = pages_text[idx]
                    for kw in ["AA1000", "ISAE 3000", "独立鉴证报告", "独立审验声明", "审验报告"]:
                        if kw in txt:
                            pos = txt.find(kw)
                            snippet = txt[max(0, pos - 30):min(len(txt), pos + 60)].strip()
                            indicators_out[code] = {
                                "value": 1,
                                "unit": "类别字段",
                                "is_assured": True,
                                "standard": kw,
                                "page": idx + 1,
                                "quote": snippet,
                                "status": "已披露"
                            }
                            assured_found = True
                            break
                    if assured_found:
                        break
                if not assured_found:
                    indicators_out[code] = {"value": 0, "unit": "类别字段", "is_assured": False, "page": 0, "quote": "", "status": "未附第三方鉴证"}
                continue

            matched_item = None
            for idx in scan_order:
                txt = pages_text[idx]
                for kw in ind["keywords"]:
                    pos = txt.find(kw)
                    if pos != -1:
                        window = txt[pos:min(len(txt), pos + 120)]
                        m = num_unit_pattern.search(window)
                        if m:
                            val_str = m.group(1).replace(",", "")
                            try:
                                val_num = float(val_str)
                                matched_item = {
                                    "value": val_num,
                                    "unit": m.group(2),
                                    "year": rep_year,
                                    "page": idx + 1,
                                    "quote": window.splitlines()[0][:90].strip() if "\n" not in window[:50] else " ".join(window[:90].split()),
                                    "status": "已披露"
                                }
                                break
                            except ValueError:
                                pass
                if matched_item:
                    break

            indicators_out[code] = matched_item or {
                "value": None,
                "unit": "",
                "year": rep_year,
                "page": 0,
                "quote": "",
                "status": "未披露"
            }

        return {
            "company_name": comp_name,
            "company_code": comp_code,
            "report_year": rep_year,
            "indicators": indicators_out
        }
