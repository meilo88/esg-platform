import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from typing import Dict, Any, List

class ExcelExporter:
    """
    负责生成面向普通用户的纯净【指标数据表】Excel，
    与管理员专享的【人工核验底稿】形成严格的角色与格式隔离。
    """

    @staticmethod
    def export_clean_data(review_data: Dict[str, Any], output_path: str) -> str:
        """
        面向普通访客：导出纯净的 ESG 定量披露指标数据表
        无人工标注列、无核验状态列、无第二张审计规范 Sheet
        """
        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        title_font = Font(name="微软雅黑", size=13, bold=True, color="1E3A8A")
        sub_font = Font(name="微软雅黑", size=9, color="4B5563")
        header_font = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
        cell_font = Font(name="微软雅黑", size=9)
        
        header_fill = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid")
        zebra_fill = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")
        
        thin_border = Border(
            left=Side(style='thin', color='E5E7EB'),
            right=Side(style='thin', color='E5E7EB'),
            top=Side(style='thin', color='E5E7EB'),
            bottom=Side(style='thin', color='E5E7EB')
        )

        ws = wb.create_sheet(title="ESG定量披露指标数据")
        ws.views.sheetView[0].showGridLines = True
        
        summary = review_data.get("summary", {})
        indicators = review_data.get("indicators", [])

        # 标题栏
        ws.merge_cells("A1:K1")
        company_name = summary.get("company_name", "上市企业")
        report_year = summary.get("report_year", "最新")
        ws["A1"] = f"A股上市公司可持续发展报告指标数据表 —— {company_name} ({report_year}年度)"
        ws["A1"].font = title_font
        ws["A1"].alignment = Alignment(vertical="center", indent=1)
        ws.row_dimensions[1].height = 32

        ws.merge_cells("A2:K2")
        ws["A2"] = f"指标标准: 沪深北交易所《上市公司自律监管指引——可持续发展报告（试行）》 | 报告总页数: {summary.get('total_pages', '--')} 页 | 披露指标项数: {len(indicators)} 项"
        ws["A2"].font = sub_font
        ws["A2"].alignment = Alignment(vertical="center", indent=1)
        ws.row_dimensions[2].height = 20

        # 普通用户纯净表头（绝不含任何核验结论、修改数值或说明列）
        headers = [
            "指标代码", "指标名称", "议题维度", "依据指引条款", 
            "报告披露原值", "原单位", "标准化数值", "标准单位", "单位换算说明",
            "报告所在页码", "报告披露原文证据引用"
        ]
        
        ws.row_dimensions[3].height = 26
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=3, column=col_idx, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        for row_idx, item in enumerate(indicators, 4):
            ws.row_dimensions[row_idx].height = 22
            row_data = [
                item.get("code", "--"),
                item.get("name", "--"),
                item.get("dimension", "--"),
                item.get("clause", "--"),
                item.get("raw_value") if item.get("raw_value") is not None else "--",
                item.get("raw_unit") or "--",
                item.get("std_value") if item.get("std_value") is not None else "--",
                item.get("std_unit") or "--",
                item.get("conv_note") or "",
                f"第 {item.get('page')} 页" if item.get("page") else "--",
                item.get("quote") or "--"
            ]
            
            for col_idx, val in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.font = cell_font
                cell.border = thin_border
                
                # 对齐规则
                if col_idx in [1, 3, 6, 8, 10]:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif col_idx in [5, 7]:
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                else:
                    cell.alignment = Alignment(vertical="center")

                # 斑马纹隔行变色
                if row_idx % 2 == 1:
                    cell.fill = zebra_fill

        # 自适应列宽
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.row in [1, 2]:
                    continue
                val_str = str(cell.value or '')
                char_len = sum(2 if ord(c) > 127 else 1 for c in val_str)
                max_len = max(max_len, char_len)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 10), 50)

        wb.save(output_path)
        return output_path

    @staticmethod
    def export_clean_data_from_db(report: Dict[str, Any], records: List[Dict[str, Any]], output_path: str) -> str:
        """
        面向普通访客：将数据库中已收录的报告导出为纯净的【指标数据表】Excel
        """
        review_data = {
            "summary": {
                "company_name": report.get("company_name", ""),
                "report_year": report.get("year", ""),
                "total_pages": report.get("total_pages", 0)
            },
            "indicators": [
                {
                    "code": r.get("indicator_code"),
                    "name": r.get("indicator_name"),
                    "dimension": r.get("dimension"),
                    "clause": r.get("clause"),
                    "raw_value": r.get("raw_value"),
                    "raw_unit": r.get("raw_unit"),
                    "std_value": r.get("std_value"),
                    "std_unit": r.get("std_unit"),
                    "conv_note": r.get("conv_note"),
                    "page": r.get("page"),
                    "quote": r.get("quote")
                }
                for r in records
            ]
        }
        return ExcelExporter.export_clean_data(review_data, output_path)

    # 兼容历史调用别名
    @staticmethod
    def export(review_data: Dict[str, Any], output_path: str) -> str:
        return ExcelExporter.export_clean_data(review_data, output_path)
