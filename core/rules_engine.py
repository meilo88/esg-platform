import re
from typing import Dict, List, Any, Optional, Tuple

class RulesEngine:
    """
    ESG定量指标标准化换算与审计一致性核查引擎
    """
    
    @staticmethod
    def parse_numeric(val: Any) -> Optional[float]:
        """从字符串中安全提取数值（过滤逗号、文字等）"""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        
        s = str(val).strip().replace(",", "").replace("，", "")
        # 匹配浮点数或整数
        m = re.search(r"[-+]?[0-9]*\.?[0-9]+", s)
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                return None
        return None

    @classmethod
    def standardize_unit(cls, metric_code: str, raw_value: Any, raw_unit: str) -> Tuple[Optional[float], str, str]:
        """
        按标准规则统一换算指标数值与单位
        返回: (standard_value, standard_unit, conversion_note)
        """
        num = cls.parse_numeric(raw_value)
        if num is None:
            return None, "", "无数值或无法量化"
            
        unit = str(raw_unit).strip().lower() if raw_unit else ""
        
        # 1. 温室气体与碳减排类 (Q01, Q02, Q03, Q03A, Q03B, Q04, Q08) -> 标准单位: tCO2e
        if metric_code in ["Q01", "Q02", "Q03", "Q03A", "Q03B", "Q04", "Q08"]:
            std_unit = "tCO2e"
            if any(u in unit for u in ["万吨", "万t", "10000t"]):
                return round(num * 10000, 2), std_unit, "原值×10,000 (万吨->吨)"
            elif any(u in unit for u in ["千克", "kg"]):
                return round(num * 0.001, 2), std_unit, "原值÷1,000 (kg->吨)"
            elif any(u in unit for u in ["吨", "t", "tco2e", "公吨"]):
                return round(num, 2), std_unit, "原单位已为公吨"
            else:
                return round(num, 2), std_unit, f"默认按tCO2e计(原单位:{raw_unit})"

        # 2. 废弃物类 (Q09, Q10) -> 标准单位: t
        elif metric_code in ["Q09", "Q10"]:
            std_unit = "t"
            if any(u in unit for u in ["万吨", "万t"]):
                return round(num * 10000, 2), std_unit, "原值×10,000 (万吨->吨)"
            elif any(u in unit for u in ["千克", "kg"]):
                return round(num * 0.001, 2), std_unit, "原值÷1,000 (kg->吨)"
            else:
                return round(num, 2), std_unit, "单位为吨"

        # 3. 能源类 (Q12) -> 标准单位: tce (吨标准煤)
        elif metric_code == "Q12":
            std_unit = "tce"
            if any(u in unit for u in ["mwh", "兆瓦时", "千度"]):
                # 依据《综合能耗计算通则》GB/T 2589: 1 MWh = 0.1229 吨标准煤
                return round(num * 0.1229, 2), std_unit, f"原值 {num} MWh × 0.1229 折标为 tce"
            elif any(u in unit for u in ["万kwh", "万度", "万千瓦时"]):
                return round(num * 1.229, 2), std_unit, f"原值 {num} 万度折标为 tce"
            elif any(u in unit for u in ["tj", "太焦"]):
                return round(num * 34.12, 2), std_unit, f"原值 {num} TJ × 34.12 折标为 tce"
            elif any(u in unit for u in ["gj", "吉焦"]):
                return round(num * 0.03412, 2), std_unit, f"原值 {num} GJ × 0.03412 折标为 tce"
            elif any(u in unit for u in ["万吨标煤", "万吨标准煤"]):
                return round(num * 10000, 2), std_unit, "原值×10,000"
            elif any(u in unit for u in ["吨标煤", "吨标准煤", "tce"]):
                return round(num, 2), std_unit, "原单位已为吨标准煤"
            else:
                return round(num, 2), "tce", f"原单位:{raw_unit}"

        # 4. 电力与清洁能源 (Q13, Q15) -> 标准单位: MWh
        elif metric_code in ["Q13", "Q15"]:
            std_unit = "MWh"
            if any(u in unit for u in ["亿kwh", "亿千瓦时", "亿度"]):
                return round(num * 100000, 2), std_unit, "原值×100,000 (亿kWh->MWh)"
            elif any(u in unit for u in ["万kwh", "万度", "万千瓦时"]):
                return round(num * 10, 2), std_unit, "原值×10 (万度->MWh)"
            elif any(u in unit for u in ["kwh", "度", "千瓦时"]) and "千度" not in unit:
                return round(num / 1000, 2), std_unit, "原值÷1,000 (kWh->MWh)"
            else:
                return round(num, 2), std_unit, "原单位为MWh"

        # 5. 水资源 (Q16) -> 标准单位: t
        elif metric_code == "Q16":
            std_unit = "t"
            if any(u in unit for u in ["ml", "百万升", "千吨", "千立方米"]):
                return round(num * 1000, 2), std_unit, "原值×1,000 (千吨/ML->吨)"
            elif any(u in unit for u in ["万吨", "万立方米", "万m3", "万m³"]):
                return round(num * 10000, 2), std_unit, "原值×10,000"
            else:
                return round(num, 2), std_unit, "按 1立方米 = 1吨 计"

        # 6. 金额类 (Q11环保投入, Q21研发投入, Q24乡村振兴公益捐赠, Q28安全生产投入) -> 标准单位: 万元
        elif metric_code in ["Q11", "Q21", "Q24", "Q28"]:
            std_unit = "万元"
            if any(u in unit for u in ["亿元", "亿"]):
                return round(num * 10000, 2), std_unit, "原值×10,000 (亿元->万元)"
            elif any(u in unit for u in ["百万元", "百万"]):
                return round(num * 100, 2), std_unit, "原值×100 (百万元->万元)"
            elif "万元" in unit or "万" in unit:
                return round(num, 2), std_unit, "单位已为万元"
            elif "元" in unit:
                return round(num / 10000, 2), std_unit, "原值÷10,000 (元->万元)"
            else:
                return round(num, 2), std_unit, "单位为万元"

        # 7. 人数类 (Q22研发人员, Q25员工总数, Q32董事会人数)
        elif metric_code in ["Q22", "Q25"]:
            if "万" in unit:
                return round(num * 10000, 0), "人", "原值×10,000 (万人->人)"
            return round(num, 0), "人", "原值在册人数"

        elif metric_code == "Q32":
            if "%" in unit:
                return round(num, 2), "%", "独立董事占比"
            return round(num, 0), "人", "董事会成员人数"

        # 8. 件数/起数类 (Q23新增专利, Q27安全事故, Q31诉讼案)
        elif metric_code in ["Q23", "Q27", "Q31"]:
            std_u = "起/人" if metric_code == "Q27" else "件"
            return round(num, 0), std_u, "法定统计数量"

        # 9. 学时/小时类 (Q26员工培训, Q29合规廉洁培训)
        elif metric_code in ["Q26", "Q29"]:
            if "万" in unit:
                return round(num * 10000, 1), "小时", "原值×10,000 (万小时->小时)"
            return round(num, 1), "小时", "培训学时"

        # 10. 百分比类 (Q17水循环利用率)
        elif metric_code == "Q17":
            return round(num, 2), "%", "百分比披露"

        # 11. 目标年份类 (Q07)
        elif metric_code == "Q07":
            return round(num, 0), "目标年", "碳减排规划目标年份"

        return round(num, 2), raw_unit or "", "直接保留原值"

    @classmethod
    def audit_consistency(cls, results_dict: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        跨指标审计与一致性稽核
        输入: 指标字典 { "Q01": { "raw_value": ..., "std_val": ..., "verified": ... }, ... }
        输出: 异常警告列表
        """
        anomalies = []

        # 1. 温室气体加总勾稽 (Q01 vs Q02 + Q03A / Q03B)
        q01 = results_dict.get("Q01", {}).get("std_val")
        q02 = results_dict.get("Q02", {}).get("std_val")
        q03a = results_dict.get("Q03A", {}).get("std_val")
        q03b = results_dict.get("Q03B", {}).get("std_val")
        q03 = q03a if q03a is not None else (q03b if q03b is not None else results_dict.get("Q03", {}).get("std_val"))
        q04 = results_dict.get("Q04", {}).get("std_val")

        if q01 and q02 and (q03a is not None or q03b is not None or q03 is not None):
            matched = False
            # 优先检验市场法或位置法
            for s2_val, s2_label in [(q03a, "位置法"), (q03b, "市场法"), (q03, "范围2")]:
                if s2_val is None:
                    continue
                sum_1_2 = q02 + s2_val
                diff_ratio = abs(q01 - sum_1_2) / q01
                if diff_ratio <= 0.02:
                    anomalies.append({
                        "level": "SUCCESS",
                        "code": "AUDIT_GHG_SUM_VERIFIED",
                        "title": "温室气体加总一致",
                        "message": f"总量 {q01:,.0f} tCO2e 与 (范围1: {q02:,.0f} + 范围2({s2_label}): {s2_val:,.0f} = {sum_1_2:,.0f}) 完全勾稽吻合。"
                    })
                    matched = True
                    break
                elif q04 and abs(q01 - (sum_1_2 + q04)) / q01 <= 0.02:
                    anomalies.append({
                        "level": "INFO",
                        "code": "AUDIT_GHG_SCOPE3",
                        "title": "温室气体总量包含范围3",
                        "message": f"总量 {q01:,.0f} tCO2e 与范围1+范围2({s2_label})+范围3加总吻合（口径包含全产业链范围3）。"
                    })
                    matched = True
                    break

            if not matched and q03 is not None:
                sum_1_2 = q02 + q03
                diff_ratio = abs(q01 - sum_1_2) / q01
                anomalies.append({
                    "level": "WARNING",
                    "code": "AUDIT_GHG_SUM_MISMATCH",
                    "title": "温室气体加总存在偏差",
                    "message": f"总量 {q01:,.0f} tCO2e 与 (范围1: {q02:,.0f} + 范围2: {q03:,.0f} = {sum_1_2:,.0f}) 偏差达 {diff_ratio*100:.1f}%，建议核查报告核算边界。"
                })

        # 2. 范围2排放与外购电力的比值合理性核对 (Q03A/Q03B vs Q13)
        q13 = results_dict.get("Q13", {}).get("std_val")
        check_s2 = q03a if q03a is not None else q03
        if check_s2 and q13 and q13 > 0:
            emission_factor = check_s2 / q13
            # 常规区域电网平均排放因子约在 0.35 ~ 0.85 tCO2e/MWh 之间
            if emission_factor < 0.15:
                anomalies.append({
                    "level": "WARNING",
                    "code": "AUDIT_GRID_FACTOR_LOW",
                    "title": "范围2度电排放因子偏低",
                    "message": f"测算隐式排放因子为 {emission_factor:.4f} tCO2e/MWh，显著偏低，可能大比例使用了绿电或市场法核算抵扣。"
                })
            elif emission_factor > 1.2:
                anomalies.append({
                    "level": "WARNING",
                    "code": "AUDIT_GRID_FACTOR_HIGH",
                    "title": "范围2度电排放因子偏高",
                    "message": f"测算隐式排放因子为 {emission_factor:.4f} tCO2e/MWh，偏离电网常规水平，请核实外购热能折算或单位量级。"
                })

        # 3. 废弃物加总校验 (Q09危废 + Q10无害)
        q09 = results_dict.get("Q09", {}).get("std_val")
        q10 = results_dict.get("Q10", {}).get("std_val")
        if q09 and q10:
            total_waste = q09 + q10
            anomalies.append({
                "level": "INFO",
                "code": "AUDIT_WASTE_SUMMARY",
                "title": "废弃物产生总量测算",
                "message": f"有害废弃物 ({q09:,.1f} t) + 无害废弃物 ({q10:,.1f} t) 合计产生量为 {total_waste:,.1f} 吨。"
            })

        # 4. 百分比合法性区间校验 (0% ~ 100%)
        # Q15 清洁能源比例
        q15_info = results_dict.get("Q15", {})
        q15_val = cls.parse_numeric(q15_info.get("ratio_pct"))
        if q15_val is not None:
            if not (0 <= q15_val <= 100):
                anomalies.append({
                    "level": "ERROR",
                    "code": "AUDIT_RATIO_OUT_OF_BOUNDS",
                    "title": "清洁能源占比数值异常",
                    "message": f"清洁能源使用比例披露为 {q15_val}%，超出 [0%, 100%] 合法区间。"
                })

        # Q17 水资源循环利用率校验
        q17 = results_dict.get("Q17", {}).get("std_val")
        if q17 is not None:
            if not (0 <= q17 <= 100):
                anomalies.append({
                    "level": "ERROR",
                    "code": "AUDIT_WATER_RECYCLE_OUT_OF_BOUNDS",
                    "title": "水资源循环利用率异常",
                    "message": f"水资源循环利用率披露为 {q17}%，超出 [0%, 100%] 合法逻辑区间。"
                })
            elif q17 >= 80:
                anomalies.append({
                    "level": "SUCCESS",
                    "code": "AUDIT_WATER_RECYCLE_EXCELLENT",
                    "title": "工业水资源循环利用高水平",
                    "message": f"水资源循环利用率达 {q17:.1f}%，符合高水效与节水型企业标杆要求。"
                })

        # 5. 人力资源与研发人员逻辑勾稽 (Q22 研发人员 vs Q25 员工总数)
        q22 = results_dict.get("Q22", {}).get("std_val")
        q25 = results_dict.get("Q25", {}).get("std_val")
        if q22 and q25 and q25 > 0:
            if q22 > q25:
                anomalies.append({
                    "level": "ERROR",
                    "code": "AUDIT_RD_STAFF_EXCEEDS_TOTAL",
                    "title": "研发人员数超过在职员工总数",
                    "message": f"研发人员总数 ({q22:,.0f} 人) 大于员工总人数 ({q25:,.0f} 人)，存在严重数据逻辑矛盾。"
                })
            else:
                rd_ratio = (q22 / q25) * 100
                anomalies.append({
                    "level": "INFO",
                    "code": "AUDIT_RD_STAFF_RATIO",
                    "title": "研发人员占比测算",
                    "message": f"研发人员 ({q22:,.0f} 人) 占员工总数比例为 {rd_ratio:.1f}%。"
                })

        # 6. 治理合规性与独立董事比例审核 (Q32)
        q32_ratio = results_dict.get("Q32", {}).get("ratio_pct")
        if q32_ratio is None:
            q32_val = results_dict.get("Q32", {}).get("std_val")
            if q32_val and q32_val < 1.0: # 若直接给出小数
                q32_ratio = q32_val * 100
        if q32_ratio is not None:
            if q32_ratio < 33.3:
                anomalies.append({
                    "level": "WARNING",
                    "code": "AUDIT_INDEPENDENT_DIRECTOR_DEFICIT",
                    "title": "独立董事占比低于监管底线",
                    "message": f"独立董事占比测算为 {q32_ratio:.1f}%，低于中国证监会《上市公司独立董事管理办法》规定的不低于1/3 (33.3%) 要求。"
                })
            else:
                anomalies.append({
                    "level": "SUCCESS",
                    "code": "AUDIT_INDEPENDENT_DIRECTOR_COMPLIANT",
                    "title": "独立董事占比符合监管要求",
                    "message": f"独立董事占比达 {q32_ratio:.1f}%，符合证监会关于独董占比不低于1/3的监管合规标准。"
                })

        # 7. 安全生产与工伤零事故核查 (Q27)
        q27 = results_dict.get("Q27", {}).get("std_val")
        if q27 is not None:
            if q27 == 0:
                anomalies.append({
                    "level": "SUCCESS",
                    "code": "AUDIT_SAFETY_ZERO_INCIDENT",
                    "title": "零工亡安全生产达标",
                    "message": "报告期内未发生生产安全事故及因工死亡，达到安全生产规范与劳动者权益保障要求。"
                })
            elif q27 > 0:
                anomalies.append({
                    "level": "WARNING",
                    "code": "AUDIT_SAFETY_CASUALTIES_REPORTED",
                    "title": "报告期内发生安全事故或伤亡",
                    "message": f"报告期内披露安全生产事故/工亡人员共 {q27:,.0f} 起/人，需重点复核安全整改措施与赔付抚恤披露。"
                })

        # 8. 反贪腐及诉讼情况核查 (Q31)
        q31 = results_dict.get("Q31", {}).get("std_val")
        if q31 is not None:
            if q31 == 0:
                anomalies.append({
                    "level": "SUCCESS",
                    "code": "AUDIT_CORRUPTION_ZERO_LAWSUIT",
                    "title": "商业贿赂与贪腐零诉讼",
                    "message": "报告期内无涉及贪腐或不正当竞争的立案诉讼案件，廉洁内控合规良好。"
                })
            elif q31 > 0:
                anomalies.append({
                    "level": "WARNING",
                    "code": "AUDIT_CORRUPTION_LAWSUITS_EXIST",
                    "title": "存在商业贪腐诉讼案件",
                    "message": f"报告期内涉及商业贿赂或贪腐诉讼案件 {q31} 件，需核验企业内控合规审计声明。"
                })

        # 9. 原文片段真实性校验状态汇总
        unverified_count = 0
        for code, item in results_dict.items():
            if item.get("status") == "已披露" and not item.get("verified_in_page", False):
                unverified_count += 1
                anomalies.append({
                    "level": "WARNING",
                    "code": f"AUDIT_UNVERIFIED_{code}",
                    "title": f"指标 {code} 原文片段未能在对应页匹配",
                    "message": f"指标 {code}（{item.get('name')}）所提供的原文引文字段无法在第 {item.get('page')} 页找到，需人工复核防模型幻觉。"
                })

        # 10. 第三方鉴证状态与审计意见
        q30 = results_dict.get("Q30", {})
        if q30.get("is_assured"):
            anomalies.append({
                "level": "SUCCESS",
                "code": "AUDIT_ASSURANCE_PRESENT",
                "title": "已获取第三方独立鉴证",
                "message": f"报告由【{q30.get('agency', '第三方机构')}】提供独立鉴证/审验，依据标准: {q30.get('standard', '相关鉴证标准')}。"
            })
        else:
            anomalies.append({
                "level": "INFO",
                "code": "AUDIT_ASSURANCE_NONE",
                "title": "未见独立第三方鉴证声明",
                "message": "报告未附第三方独立鉴证声明，建议审阅人员重点核验核心环境数据底稿。"
            })

        return anomalies
