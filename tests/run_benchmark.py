import os
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.extractor import ESGExtractor
from core.exporter import ExcelExporter

def run_benchmark():
    reports_dir = Path("esg报告")
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    
    reports = sorted([f for f in os.listdir(reports_dir) if f.endswith(".pdf")])
    print(f"=== 开始执行 ESG 报告自动化基准评测 (共 {len(reports)} 份样本) ===")
    
    extractor = ESGExtractor()
    benchmark_results = []

    for idx, r_name in enumerate(reports, 1):
        pdf_path = str(reports_dir / r_name)
        start_time = time.time()
        print(f"\n[{idx}/{len(reports)}] 正在评测: {r_name} ...")
        
        try:
            res = extractor.process_report(pdf_path)
            duration = round(time.time() - start_time, 2)
            summary = res["summary"]
            
            # 导出底稿
            excel_name = f"Benchmark_{Path(r_name).stem}.xlsx"
            excel_path = str(output_dir / excel_name)
            ExcelExporter.export(res, excel_path)
            
            record = {
                "file": r_name,
                "company": summary["company_name"],
                "year": summary["report_year"],
                "total_pages": summary["total_pages"],
                "analyzed_pages": len(summary["target_pages_analyzed"]),
                "disclosure_rate": summary["disclosure_rate"],
                "disclosed_count": summary["disclosed_count"],
                "verification_rate": summary["verification_rate"],
                "verified_count": summary["verified_count"],
                "anomalies_count": summary["anomalies_count"],
                "duration_seconds": duration,
                "excel_path": excel_path,
                "status": "PASS"
            }
            benchmark_results.append(record)
            print(f"  -> 成功: 披露率 {summary['disclosure_rate']}, 防幻觉核验率 {summary['verification_rate']}, 异常检出 {summary['anomalies_count']} 项, 耗时 {duration}s")
            
        except Exception as e:
            print(f"  -> 失败: {e}")
            benchmark_results.append({
                "file": r_name,
                "status": "FAIL",
                "error": str(e)
            })

    # 保存评测汇总
    report_json_path = "tests/benchmark_results.json"
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_results, f, ensure_ascii=False, indent=2)

    print(f"\n=== 基准测试完成！结果已写入: {report_json_path} ===")

if __name__ == "__main__":
    run_benchmark()
