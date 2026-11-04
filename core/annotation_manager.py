import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime
from typing import Dict, Any, List

from core.database import get_db_connection
from core.rules_engine import RulesEngine

class AnnotationManager:
    """
    负责导出人工标注底稿 Excel，以及导入人工核验结果并回写 SQLite 数据库
    """

    @staticmethod
    def export_annotation_workbook(report_id: int, output_path: str) -> str:
        """导出特定报告的待核验标注 Excel 底稿"""
        conn = get_db_connection()
        cursor = conn.cursor()

        # 获取报告信息
        cursor.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
        rep = cursor.fetchone()
        if not rep:
            conn.close()
            raise ValueError(f"未找到 ID 为 {report_id} 的报告")

        # 获取指标列表
        cursor.execute("SELECT * FROM kpi_records WHERE report_id = ? ORDER BY id ASC", (report_id,))
        records = cursor.fetchall()
        conn.close()

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "人工核验与标注底稿"
        ws.views.sheetView[0].showGridLines = True

        from openpyxl.worksheet.datavalidation import DataValidation

        # 样式
        title_font = Font(name="微软雅黑", size=13, bold=True, color="1E3A8A")
        sub_font = Font(name="微软雅黑", size=9, color="4B5563")
        header_font = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
        human_header_font = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
        cell_font = Font(name="微软雅黑", size=9)
        bold_font = Font(name="微软雅黑", size=9, bold=True)
        demo_font = Font(name="微软雅黑", size=9, italic=True, bold=True, color="92400E")
        demo_note_font = Font(name="微软雅黑", size=9, color="78350F")
        
        system_header_fill = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid") # 深蓝
        human_header_fill = PatternFill(start_color="059669", end_color="059669", fill_type="solid")  # 翠绿（标注区）
        human_edit_fill = PatternFill(start_color="ECFDF5", end_color="ECFDF5", fill_type="solid")    # 浅绿背景提示可编辑
        demo_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")          # 示范行琥珀黄高亮
        zebra_fill = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")

        thin_border = Border(
            left=Side(style='thin', color='E5E7EB'), right=Side(style='thin', color='E5E7EB'),
            top=Side(style='thin', color='E5E7EB'), bottom=Side(style='thin', color='E5E7EB')
        )
        demo_border = Border(
            left=Side(style='thin', color='FCD34D'), right=Side(style='thin', color='FCD34D'),
            top=Side(style='thin', color='FCD34D'), bottom=Side(style='thin', color='FCD34D')
        )

        # 标题栏
        ws.merge_cells("A1:O1")
        ws["A1"] = f"ESG 定量指标人工鉴证核验底稿 —— {rep['company_name']} ({rep['year']}年度)"
        ws["A1"].font = title_font
        ws["A1"].alignment = Alignment(vertical="center", indent=1)
        ws.row_dimensions[1].height = 32

        ws.merge_cells("A2:O2")
        ws["A2"] = f"报告文件: {rep['pdf_filename']} | 第4~6行为【示范模版行】供团队参考标准填法 | L列为【人工核验结论】下拉选择 | 详见下方第2个标签页《核验标准与协作规范》"
        ws["A2"].font = sub_font
        ws.row_dimensions[2].height = 22

        # 表头
        headers = [
            "记录ID", "指标代码", "指标名称", "维度", 
            "AI初抽原值", "原单位", "标准化数值", "标准单位", "报告页码", "原文证据引用",
            "【当前状态】",
            "【人工核验结论】", "【人工修正数值】", "【人工修正单位】", "【核验复核说明】"
        ]
        ws.row_dimensions[3].height = 28

        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=3, column=col_idx, value=h)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            if col_idx >= 12:
                cell.font = human_header_font
                cell.fill = human_header_fill
            else:
                cell.font = header_font
                cell.fill = system_header_fill

        # ================= 插入 3 行示范模版行（指导队友标准化填报） =================
        demo_rows = [
            [
                "示例-属实", "[示范] Q01", "【示范填法1-核验属实】温室气体排放总量", "环境维度 (E)",
                450000, "吨二氧化碳当量", 450000, "tCO2e", "P80", "报告P80表2：温室气体排放总量450,000吨二氧化碳当量",
                "AI抽取待核查",
                "核验属实", "", "", "与原版PDF第80页表2核对一致，数值与单位属实准确 (属实时数值列留空)"
            ],
            [
                "示例-修正", "[示范] Q02", "【示范填法2-修正原值】范围1 直接排放量", "环境维度 (E)",
                35400, "吨二氧化碳当量", 35400, "tCO2e", "P80", "报告P80：直接排放35,400吨；P25附注发电机柴油排放400吨",
                "AI抽取待核查",
                "修正原值", 35800, "tCO2e", "原初抽遗漏P25附注发电机柴油排放400t，人工补正合计数为35800 (填入修正数值与依据)"
            ],
            [
                "示例-未披露", "[示范] Q04", "【示范填法3-确认未披露】范围3 价值链排放量", "环境维度 (E)",
                "--", "--", "--", "tCO2e", "--", "--",
                "未披露",
                "未披露", "", "", "查阅全文环境与价值链章节，未发现量化披露数值 (确认未披露)"
            ]
        ]

        for d_idx, d_row in enumerate(demo_rows, 4):
            ws.row_dimensions[d_idx].height = 24
            for c_idx, d_val in enumerate(d_row, 1):
                cell = ws.cell(row=d_idx, column=c_idx, value=d_val)
                cell.font = demo_font if c_idx in [1, 2, 3, 12] else demo_note_font
                cell.fill = demo_fill
                cell.border = demo_border
                if c_idx in [1, 2, 4, 6, 8, 9, 11, 12]:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif c_idx in [5, 7, 13]:
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                else:
                    cell.alignment = Alignment(vertical="center")

        # ================= 真实待核验数据行（从第 7 行开始） =================
        data_start_row = 7
        data_end_row = data_start_row + len(records) - 1

        for row_idx, r in enumerate(records, data_start_row):
            ws.row_dimensions[row_idx].height = 22
            row_data = [
                r["id"],
                r["indicator_code"],
                r["indicator_name"],
                r["dimension"],
                r["raw_value"] if r["raw_value"] is not None else "--",
                r["raw_unit"] or "--",
                r["std_value"] if r["std_value"] is not None else "--",
                r["std_unit"] or "--",
                f"P{r['page']}" if r["page"] else "--",
                r["quote"] or "--",
                r["audit_status"],
                "核验属实" if r["audit_status"] == "已人工核对" else "", # 若此前已核对则填充，否则留空待选
                "", # 人工修正数值
                "", # 人工修正单位
                r["reviewer_note"] or ""
            ]

            for col_idx, val in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.font = cell_font
                cell.border = thin_border

                if col_idx in [1, 2, 4, 6, 8, 9, 11]:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif col_idx in [5, 7, 13]:
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                else:
                    cell.alignment = Alignment(vertical="center")

                # 人工输入区高亮 (列 12~15)
                if col_idx >= 12:
                    cell.fill = human_edit_fill
                    cell.font = bold_font
                elif row_idx % 2 == 1:
                    cell.fill = zebra_fill

        # 为真实数据行 L 列添加数据有效性下拉菜单 (DataValidation)
        dv_conclusion = DataValidation(
            type="list", 
            formula1='"核验属实,修正原值,未披露,无法核实"', 
            allow_blank=True
        )
        dv_conclusion.promptTitle = "核验结论标准规范"
        dv_conclusion.prompt = "请从下拉列表中选择标准结论：\n1. 核验属实 (与PDF一致，数值列留空)\n2. 修正原值 (AI抽错，在M列填修正数字)\n3. 未披露 (报告未定量公布)\n4. 无法核实 (存疑需二次研判)"
        dv_conclusion.errorTitle = "输入不规范"
        dv_conclusion.error = "请选择规范的核验结论：核验属实 / 修正原值 / 未披露 / 无法核实"
        ws.add_data_validation(dv_conclusion)
        dv_conclusion.add(f"L{data_start_row}:L{data_end_row}")

        # 调整第1个工作表的列宽
        for col in ws.columns:
            col_letter = get_column_letter(col[0].column)
            if col[0].column in [1, 2]:
                ws.column_dimensions[col_letter].width = 12
            elif col[0].column in [3]:
                ws.column_dimensions[col_letter].width = 30
            elif col[0].column in [10]:
                ws.column_dimensions[col_letter].width = 38
            elif col[0].column in [15]:
                ws.column_dimensions[col_letter].width = 42
            elif col[0].column in [12]:
                ws.column_dimensions[col_letter].width = 16
            elif col[0].column in [13, 14]:
                ws.column_dimensions[col_letter].width = 16
            else:
                ws.column_dimensions[col_letter].width = 14

        # ================= 创建第 2 个工作表：《核验标准与协作规范》 =================
        ws_guide = wb.create_sheet(title="核验标准与协作规范")
        ws_guide.views.sheetView[0].showGridLines = True

        guide_title_font = Font(name="微软雅黑", size=14, bold=True, color="1E3A8A")
        sec_font = Font(name="微软雅黑", size=11, bold=True, color="0F766E")
        tbl_hd_font = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
        normal_font = Font(name="微软雅黑", size=9)
        tbl_hd_fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")
        card_fill = PatternFill(start_color="F0FDFA", end_color="F0FDFA", fill_type="solid")

        ws_guide.merge_cells("A1:F1")
        ws_guide["A1"] = "A股可持续发展报告指标核验底稿 —— 团队协同标注操作规范"
        ws_guide["A1"].font = guide_title_font
        ws_guide["A1"].alignment = Alignment(vertical="center", indent=1)
        ws_guide.row_dimensions[1].height = 36

        ws_guide.merge_cells("A2:F2")
        ws_guide["A2"] = "本规范旨在统一团队人工核验口径，确保底稿数据严肃、准确、可追溯，并支持系统一键导入回写数据库。"
        ws_guide["A2"].font = sub_font
        ws_guide.row_dimensions[2].height = 20

        # 一、核验结论标准定义与填写要求
        ws_guide.cell(row=4, column=1, value="一、四类标准核验结论填写规范对照表").font = sec_font
        guide_headers = ["核验结论", "适用场景说明", "【人工修正数值】列要求", "【人工修正单位】列要求", "【核验复核说明】列要求", "系统入库与回写机制"]
        ws_guide.row_dimensions[5].height = 26
        for c_idx, gh in enumerate(guide_headers, 1):
            cell = ws_guide.cell(row=5, column=c_idx, value=gh)
            cell.font = tbl_hd_font
            cell.fill = tbl_hd_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        guide_rows = [
            [
                "核验属实",
                "AI抽取的数值、计量单位、报告页码及原文引用与原版 PDF 完全吻合且无遗漏。",
                "保持留空（切勿填入任何内容）",
                "保持留空",
                "建议简要填写核验依据，例如：“与PDF第80页表2核对一致，数值无误”",
                "系统将该指标标记为【已人工核对】，累计提升报告整体人工核验比例。"
            ],
            [
                "修正原值",
                "AI抽取的数值有误（如OCR识别错误、图表口径错位、附注遗漏需汇总或扣减）。",
                "必须填写真实披露的数值（纯数字，如 35800 或 12.5，严禁加汉字或逗号）",
                "若原单位有误需填写修正单位（如 tCO2e、万元、人、t），未变则留空",
                "必须详细注明修正依据与错误原因，例如：“原抽取遗漏子公司自备电厂柴油排放400t，合计补正为35800”",
                "系统自动根据新数值与单位重新触发规则引擎换算标准值，状态标记为【人工已修正】。"
            ],
            [
                "未披露",
                "查阅原版 PDF 全文及相关章节后，确认企业在本报告期内未对该指标进行量化披露。",
                "保持留空",
                "保持留空",
                "建议注明：“查阅全文环境/社会章节，确认未披露定量数值”",
                "系统将该指标状态更新为【未披露】，不计入异常缺失，核验结论入库。"
            ],
            [
                "无法核实",
                "报告披露内容模糊、口径与指引定义存在争议、或图表数据冲突需要团队集体研判。",
                "可暂留空或填入争议数值",
                "可暂留空",
                "必须详细记录争议点，例如：“P18图表中能耗含光伏自发自用部分，是否计入待团队研判”",
                "系统将该指标保留为【存疑待定】，不直接覆盖主库数据，等待二次复核。"
            ]
        ]

        for r_idx, g_row in enumerate(guide_rows, 6):
            ws_guide.row_dimensions[r_idx].height = 36
            for c_idx, g_val in enumerate(g_row, 1):
                cell = ws_guide.cell(row=r_idx, column=c_idx, value=g_val)
                cell.font = bold_font if c_idx == 1 else normal_font
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center", wrap_text=True)
                if c_idx == 1:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.fill = card_fill

        # 二、团队协同审签工作流
        ws_guide.cell(row=11, column=1, value="二、团队人机协同核验工作流（四步闭环）").font = sec_font
        flow_steps = [
            ("步骤 1：领取任务与下载原版报告", "在平台【报告库】或【独立报告详情页】点击【下载PDF】，获取上市公司官方披露的高清原版报告。"),
            ("步骤 2：比对原文证据与页码", "在底稿第9列(报告页码)和第10列(原文证据引用)的指引下，快速定位原版PDF相应页面进行逐字逐表比对。"),
            ("步骤 3：填写第12~15列绿色核验区", "在 L 列下拉选择核验结论（核验属实/修正原值/未披露/无法核实），若修正则在 M/N 列录入数字与单位，在 O 列注明说明。"),
            ("步骤 4：保存 Excel 并一键导入回写", "核验完成后保存文件。在平台顶部点击【导入标注底稿】或将 Excel 上传，系统自动校验数据并毫秒级同步回写数据库。")
        ]
        for s_idx, (stitle, sdesc) in enumerate(flow_steps, 12):
            ws_guide.row_dimensions[s_idx].height = 24
            c1 = ws_guide.cell(row=s_idx, column=1, value=stitle)
            c1.font = bold_font
            c1.border = thin_border
            ws_guide.merge_cells(start_row=s_idx, start_column=2, end_row=s_idx, end_column=6)
            c2 = ws_guide.cell(row=s_idx, column=2, value=sdesc)
            c2.font = normal_font
            c2.border = thin_border

        # 三、常见单位换算速查
        ws_guide.cell(row=17, column=1, value="三、常见核心指标单位换算标准表").font = sec_font
        conv_headers = ["指标大类", "原始披露常见单位", "平台标准库单位", "标准换算关系", "填写示例与注意事项"]
        ws_guide.row_dimensions[18].height = 24
        for c_idx, ch in enumerate(conv_headers, 1):
            cell = ws_guide.cell(row=18, column=c_idx, value=ch)
            cell.font = tbl_hd_font
            cell.fill = tbl_hd_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        conv_rows = [
            ["温室气体排放", "万吨二氧化碳当量 (万tCO2e)", "tCO2e (吨二氧化碳当量)", "原值 × 10,000", "若原披露 45.2万吨，修正数值填写 452000，单位填 tCO2e"],
            ["综合能耗", "吨标准煤 (tce) / 兆瓦时 (MWh)", "tce (吨标准煤)", "等价折算标煤", "优先采纳企业披露的折标煤原值；若仅有电力可注明按当量折算"],
            ["水资源消耗", "万立方米 / 万吨", "t (吨 / 立方米)", "原值 × 10,000 (1立方米淡水≈1吨)", "若披露 385万吨，修正数值填写 3850000，单位填 t"],
            ["研发与资金投入", "亿元", "万元", "原值 × 10,000", "若年报披露 39.918亿元，修正数值填写 399180，单位填 万元"],
            ["人员与安全指标", "人 / 万人 / 起", "人 / 起", "万人 × 10,000", "员工总数、研发人数修正填写纯整数；安全事故填起数/死亡人数"]
        ]

        for r_idx, c_row in enumerate(conv_rows, 19):
            ws_guide.row_dimensions[r_idx].height = 24
            for c_idx, c_val in enumerate(c_row, 1):
                cell = ws_guide.cell(row=r_idx, column=c_idx, value=c_val)
                cell.font = bold_font if c_idx in [1, 3] else normal_font
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center")

        # 调整指南页列宽
        ws_guide.column_dimensions["A"].width = 24
        ws_guide.column_dimensions["B"].width = 36
        ws_guide.column_dimensions["C"].width = 28
        ws_guide.column_dimensions["D"].width = 26
        ws_guide.column_dimensions["E"].width = 38
        ws_guide.column_dimensions["F"].width = 32

        wb.save(output_path)
        return output_path

    @staticmethod
    def import_and_sync_annotation(excel_path: str) -> Dict[str, Any]:
        """
        读取人工填写的核验底稿 Excel，自动同步回写 SQLite 数据库
        """
        wb = openpyxl.load_workbook(excel_path, data_only=True)
        # 优先读取 "人工核验与标注底稿" 工作表
        ws = wb["人工核验与标注底稿"] if "人工核验与标注底稿" in wb.sheetnames else wb.active

        conn = get_db_connection()
        cursor = conn.cursor()

        updated_count = 0
        corrected_count = 0
        report_ids_touched = set()

        for row_idx in range(4, ws.max_row + 1):
            record_id_val = str(ws.cell(row=row_idx, column=1).value or "").strip()
            # 自动跳过示范模版行及空行
            if not record_id_val or "示例" in record_id_val or "示范" in record_id_val or "DEMO" in record_id_val.upper():
                continue

            try:
                record_id = int(record_id_val)
                if record_id <= 0:
                    continue
            except (ValueError, TypeError):
                continue

            conclusion = str(ws.cell(row=row_idx, column=12).value or "").strip()
            corrected_val_cell = ws.cell(row=row_idx, column=13).value
            corrected_unit = str(ws.cell(row=row_idx, column=14).value or "").strip()
            notes = str(ws.cell(row=row_idx, column=15).value or "").strip()

            # 过滤占位符提示文字
            if corrected_unit in ["--", "(留空)", "无"]:
                corrected_unit = ""
            if str(corrected_val_cell).strip() in ["", "--", "(留空)", "无"]:
                corrected_val_cell = None

            if not conclusion and corrected_val_cell is None and not notes:
                continue

            # 查出当前库中记录
            cursor.execute("SELECT * FROM kpi_records WHERE id = ?", (record_id,))
            current = cursor.fetchone()
            if not current:
                continue

            report_ids_touched.add(current["report_id"])
            indicator_code = current["indicator_code"]
            audit_status = current["audit_status"]
            std_val = current["std_value"]
            std_unit = current["std_unit"]
            raw_val = current["raw_value"]
            raw_unit = current["raw_unit"]

            if conclusion in ["核验属实", "确认正确", "核实正确", "OK", "正确", "属实", "无误", "一致"]:
                audit_status = "已人工核对"
                updated_count += 1
            elif conclusion in ["修正原值", "数据有误已修正", "修正", "有误", "修改"] or (corrected_val_cell is not None and str(corrected_val_cell).strip() != ""):
                audit_status = "人工已修正"
                corrected_count += 1
                corrected_num = RulesEngine.parse_numeric(corrected_val_cell)
                if corrected_num is not None:
                    raw_val = corrected_num
                    if corrected_unit:
                        raw_unit = corrected_unit
                    # 重新按规则引擎换算标准单位
                    std_val, std_unit, conv_note = RulesEngine.standardize_unit(indicator_code, raw_val, raw_unit)
            elif conclusion in ["未披露", "未披露/漏抽", "报告未披露"]:
                audit_status = "已人工核对"
                status = "未披露"
                cursor.execute("""
                UPDATE kpi_records SET status = ?, audit_status = ?, reviewer_note = ?, updated_at = datetime('now', 'localtime')
                WHERE id = ?
                """, (status, audit_status, notes or "人工核验确认未披露", record_id))
                updated_count += 1
                continue
            elif conclusion in ["无法核实", "存疑", "待确认"]:
                audit_status = "存疑待定"
                cursor.execute("""
                UPDATE kpi_records SET audit_status = ?, reviewer_note = ?, updated_at = datetime('now', 'localtime')
                WHERE id = ?
                """, (audit_status, notes or "人工核验标记为存疑待定", record_id))
                updated_count += 1
                continue

            cursor.execute("""
            UPDATE kpi_records 
            SET raw_value = ?, raw_unit = ?, std_value = ?, std_unit = ?, audit_status = ?, reviewer_note = ?, updated_at = datetime('now', 'localtime')
            WHERE id = ?
            """, (raw_val, raw_unit, std_val, std_unit, audit_status, notes, record_id))

        # 检查受影响的报告整体状态：若报告内大部分指标已人工核验，则将报告标记为 '已人工核对'
        for rep_id in report_ids_touched:
            cursor.execute("SELECT COUNT(*) as total, SUM(CASE WHEN audit_status IN ('已人工核对', '人工已修正') THEN 1 ELSE 0 END) as verified FROM kpi_records WHERE report_id = ?", (rep_id,))
            stats = cursor.fetchone()
            total = stats["total"]
            ver = stats["verified"]
            if total > 0 and ver >= total * 0.8: # 80%以上指标核对即升级
                cursor.execute("UPDATE reports SET status = '已人工核对' WHERE id = ?", (rep_id,))

        conn.commit()
        conn.close()

        return {
            "status": "ok",
            "records_updated": updated_count,
            "records_corrected": corrected_count,
            "total_processed": updated_count + corrected_count,
            "reports_updated": len(report_ids_touched)
        }
