import sys
import os
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import (
    get_platform_stats,
    list_companies,
    list_industries,
    get_company_detail,
    list_reports,
    get_report_detail,
    get_rankings
)
from core.database import get_db_connection, init_db, seed_initial_data
from core.annotation_manager import AnnotationManager
from core.rules_engine import RulesEngine
import openpyxl

async def run_tests():
    print("=" * 60)
    print("1. 重新初始化并灌入数据库...")
    init_db(drop_first=True)
    seed_initial_data()
    print("   -> 数据库初始化成功！")

    print("\n2. 测试系统概览 API (get_platform_stats)...")
    stats = await get_platform_stats()
    print(f"   -> 公司数: {stats['total_companies']}, 报告数: {stats['total_reports']}, 披露指标总计: {stats['total_kpis']}, 核验率: {stats['verified_rate']}")
    assert stats['total_companies'] == 18
    assert stats['total_reports'] == 35
    assert stats['total_kpis'] == 945
    assert stats['verified_reports'] == 0
    assert stats['verified_rate'] == "0.0%"

    print("\n3. 测试申万一级全31个行业列表 API (list_industries)...")
    ind_res = await list_industries()
    print(f"   -> 申万一级全行业总数: {ind_res['total_industries']}, 已收录行业数: {ind_res['ingested_industries']}")
    assert ind_res['total_industries'] == 31
    assert ind_res['ingested_industries'] == 12

    print("\n4. 测试公司列表与申万一级行业筛选 API (list_companies)...")
    comp_res = await list_companies()
    companies = comp_res["companies"]
    print(f"   -> 获取到 {len(companies)} 家公司 (全部行业)")
    assert len(companies) == 18

    # 测试按申万一级行业筛选
    elec_res = await list_companies(industry="电子")
    print(f"   -> 申万一级【电子】收录: {len(elec_res['companies'])} 家")
    assert len(elec_res['companies']) == 6

    empty_res = await list_companies(industry="国防军工")
    print(f"   -> 申万一级【国防军工】待收录行业返回: {len(empty_res['companies'])} 家")
    assert len(empty_res['companies']) == 0

    print("\n5. 测试公司详情与所有 26 项指标手风琴及趋势图 (get_company_detail)...")
    # 歌尔股份
    goertek_detail = await get_company_detail("002241", "Q01")
    assert len(goertek_detail["available_indicators"]) == 27
    assert len(goertek_detail["latest_kpis"]) == 27
    assert len(goertek_detail["trend_data"]) == 3
    print(f"   -> 歌尔股份: 指标总数 {len(goertek_detail['available_indicators'])}, 最新年份指标数 {len(goertek_detail['latest_kpis'])}, Q01 历史年份数 {len(goertek_detail['trend_data'])}")

    print("\n6. 测试多指标历史趋势分析 (get_company_detail 各指标)...")
    for code in ["Q01", "Q08", "Q15", "Q21", "Q22", "Q25", "Q26", "Q29", "Q32"]:
        detail_res = await get_company_detail("002475", code)
        trend = detail_res["trend_data"]
        assert len(trend) == 3
        print(f"   -> 立讯精密 [{code}] 历史趋势点数: {len(trend)}, 最新值: {trend[-1]['std_value']} {trend[-1]['std_unit']}")

    print("\n7. 测试全行业横向对比排名 (get_rankings)...")
    for test_code in ["Q01", "Q12", "Q16", "Q21", "Q25"]:
        rank_res = await get_rankings(test_code, 2024)
        rankings = rank_res["rankings"]
        assert len(rankings) >= 6
        print(f"   -> 指标 {test_code} 2024 榜首: {rankings[0]['company_name']} ({rankings[0]['std_value']:,} {rankings[0]['std_unit']})")

    print("\n8. 测试单份报告详情与 26 项三大维度分类及官方 PDF 关联 (get_report_detail)...")
    rep_detail = await get_report_detail(1)
    assert rep_detail["report"]["has_pdf"] is True
    standard_kpis = rep_detail["standard_kpis"]
    raw_kpis = rep_detail["raw_kpis"]
    assert len(standard_kpis) == 27
    assert len(raw_kpis) == 27
    dims = set(k["dimension"] for k in standard_kpis)
    print(f"   -> 报告详情包含 {len(standard_kpis)} 项标准指标，原始披露提取 {len(raw_kpis)} 项，PDF 关联存在: {rep_detail['report']['has_pdf']}")
    print(f"   -> 涵盖维度: {dims}")
    assert any("环境" in d for d in dims)
    assert any("社会" in d for d in dims)
    assert any("治理" in d for d in dims)

    print("\n9. 测试规则引擎扩展核验项 (audit_consistency)...")
    sample_audit_dict = {
        "Q01": {"std_val": 100000.0, "status": "已披露", "verified_in_page": True, "name": "温室气体排放总量"},
        "Q02": {"std_val": 20000.0, "status": "已披露", "verified_in_page": True, "name": "范围1 直接排放量"},
        "Q03A": {"std_val": 80000.0, "status": "已披露", "verified_in_page": True, "name": "范围2 间接排放量（基于位置法）"},
        "Q17": {"std_val": 88.5, "status": "已披露", "verified_in_page": True, "name": "工业水资源循环利用率"},
        "Q22": {"std_val": 5000.0, "status": "已披露", "verified_in_page": True, "name": "研发人员总数"},
        "Q25": {"std_val": 25000.0, "status": "已披露", "verified_in_page": True, "name": "期末在职员工总数"},
        "Q27": {"std_val": 0.0, "status": "已披露", "verified_in_page": True, "name": "生产安全事故起数及因工死亡人数"},
        "Q31": {"std_val": 0.0, "status": "已披露", "verified_in_page": True, "name": "商业贿赂与贪腐诉讼案件数"},
        "Q32": {"std_val": 9.0, "ratio_pct": 33.33, "status": "已披露", "verified_in_page": True, "name": "董事会成员人数及独立董事占比"}
    }
    anomalies = RulesEngine.audit_consistency(sample_audit_dict)
    codes = [a["code"] for a in anomalies]
    print(f"   -> 规则引擎触发审计结论数量: {len(anomalies)} 项")
    print(f"   -> 触发的审计代码: {codes}")
    assert "AUDIT_GHG_SUM_VERIFIED" in codes
    assert "AUDIT_WATER_RECYCLE_EXCELLENT" in codes
    assert "AUDIT_RD_STAFF_RATIO" in codes
    assert "AUDIT_INDEPENDENT_DIRECTOR_COMPLIANT" in codes
    assert "AUDIT_SAFETY_ZERO_INCIDENT" in codes
    assert "AUDIT_CORRUPTION_ZERO_LAWSUIT" in codes

    print("\n10. 测试 Excel 人工标注底稿导出与回写闭环 (含模版行与协作指南页)...")
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    excel_path = str(out_dir / "test_human_audit_rep1.xlsx")
    
    # 导出
    res_path = AnnotationManager.export_annotation_workbook(1, excel_path)
    print(f"   -> 成功导出底稿到: {res_path}")
    
    # 检查导出的工作表包含底稿与指南
    wb = openpyxl.load_workbook(excel_path)
    assert "人工核验与标注底稿" in wb.sheetnames
    assert "核验标准与协作规范" in wb.sheetnames
    print(f"   -> 工作簿包含两大规范工作表: {wb.sheetnames}")

    ws = wb["人工核验与标注底稿"]
    # 验证示范模版行
    assert "示例" in str(ws.cell(row=4, column=1).value)
    assert "示例" in str(ws.cell(row=5, column=1).value)
    assert "示例" in str(ws.cell(row=6, column=1).value)
    print("   -> 成功校验 3 行填报示范模版行（示范核验属实、修正原值、未披露）")
    
    # 修改 Excel 真实数据行模拟人工核验
    found_q01 = False
    for r in range(7, ws.max_row + 1):
        code = ws.cell(row=r, column=2).value
        if code == "Q01":
            ws.cell(row=r, column=12, value="核验属实")
            ws.cell(row=r, column=15, value="审计师王五与年报能源管理底稿比对无误")
            found_q01 = True
        elif code == "Q02":
            ws.cell(row=r, column=12, value="修正原值")
            ws.cell(row=r, column=13, value=35800.0) # 修正值
            ws.cell(row=r, column=14, value="tCO2e")
            ws.cell(row=r, column=15, value="发现一处发电机柴油漏计，人工补正+400tCO2e")
    
    assert found_q01, "未在 Excel 中找到 Q01"
    wb.save(excel_path)
    print("   -> 已在 Excel 中模拟人工审核标记并保存")

    # 导入回写
    import_res = AnnotationManager.import_and_sync_annotation(excel_path)
    print(f"   -> 导入结果: 修正 {import_res['records_corrected']} 项, 确认 {import_res['records_updated']} 项, 涉及报告数: {import_res['reports_updated']}")
    assert import_res['records_corrected'] >= 1
    assert import_res['records_updated'] >= 1

    # 校验数据库回写状态
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT audit_status, std_value, reviewer_note FROM kpi_records WHERE report_id = 1 AND indicator_code = 'Q02'")
    row = c.fetchone()
    print(f"   -> 数据库中 Q02 回写状态: {row['audit_status']}, 修正后数值: {row['std_value']}, 复核说明: {row['reviewer_note']}")
    assert row['audit_status'] == "人工已修正"
    conn.close()

    print("\n11. 测试管理后台安全鉴权 (suibe123)、防爆破、配置隔离与底稿防越权下载...")
    import config as app_config
    from app import (
        admin_login,
        admin_logout,
        AdminLoginModel,
        update_settings,
        get_settings,
        SettingsModel,
        download_excel,
        export_annotation_excel,
        health_check,
        list_samples,
        analyze_report,
        LLM_CONFIG_PATH,
        ADMIN_SESSIONS_PATH,
    )
    from fastapi import HTTPException

    had_llm_cfg_before = LLM_CONFIG_PATH.exists()
    prev_llm_cfg_bytes = LLM_CONFIG_PATH.read_bytes() if had_llm_cfg_before else None

    health_res = await health_check()
    assert health_res["status"] == "healthy"
    samples_res = await list_samples()
    assert len(samples_res["samples"]) >= 13
    assert all("path" not in s for s in samples_res["samples"]), "样本接口不应暴露服务器物理绝对路径"
    print(f"   -> 健康检查通过，样本列表共 {len(samples_res['samples'])} 份且已隐藏物理路径")

    rep_kw_res = await list_reports(keyword="比亚迪")
    assert len(rep_kw_res["reports"]) == 3
    rep_status_res = await list_reports(status="AI抽取，待核查")
    assert len(rep_status_res["reports"]) == 35
    print("   -> 报告库关键词检索与状态筛选校验通过")

    class MockRequest:
        def __init__(self, headers=None, client_ip="192.168.1.100"):
            self.headers = headers or {}
            class Client:
                host = client_ip
            self.client = Client()

    # 1. 错误密码拒绝
    try:
        await admin_login(AdminLoginModel(password="wrongpass"), MockRequest())
        assert False, "错误密码应当被拒绝"
    except HTTPException as e:
        assert e.status_code == 401
        print("   -> 成功校验：提交错误密码被严格拦截 (HTTP 401)")

    # 2. 正确密码 suibe123 成功获取 Token
    login_res = await admin_login(AdminLoginModel(password="suibe123"), MockRequest())
    assert login_res["status"] == "ok"
    token = login_res["token"]
    print("   -> 成功校验：提交正确密码 suibe123 成功通过鉴权，生成安全 Token")

    # 3. 未授权访问管理配置读写接口均被拦截
    for fn_call in (
        lambda: update_settings(SettingsModel(provider="openai", api_key="sk-test"), MockRequest()),
        lambda: get_settings(MockRequest()),
    ):
        try:
            await fn_call()
            assert False, "无 Token 访问管理员配置接口应被拦截"
        except HTTPException as e:
            assert e.status_code == 401
    print("   -> 成功校验：普通未授权访客读写大模型配置均被拒绝 (HTTP 401)")

    # 4. 携带有效 Token 访问管理员接口放行，且查询配置不回传明文 Key
    auth_req = MockRequest(headers={"X-Admin-Token": token})
    setting_res = await update_settings(SettingsModel(provider="gemini", api_key="sk-valid-key"), auth_req)
    assert setting_res["status"] == "ok"
    got_cfg = await get_settings(auth_req)
    assert got_cfg["has_gemini_key"] is True
    assert "api_key" not in got_cfg and "sk-valid-key" not in str(got_cfg)
    await update_settings(SettingsModel(provider="gemini", api_key="__CLEAR__"), auth_req)
    print("   -> 成功校验：管理员配置持久化、脱敏读取与清空还原正常")

    # 5. 未授权导出底稿拦截 & 公开下载接口拦截核验底稿文件名
    try:
        await export_annotation_excel(1, MockRequest())
        assert False, "普通访客导出团队核验底稿应被拦截"
    except HTTPException as e:
        assert e.status_code == 401
        print("   -> 成功校验：普通访客直接调用核验底稿导出被拒绝 (HTTP 401)")

    try:
        await download_excel("ESG_Annotation_Report_1.xlsx")
        assert False, "公开下载接口不应允许下载内部核验底稿"
    except HTTPException as e:
        assert e.status_code == 403
        print("   -> 成功校验：公开下载接口严格阻断核验底稿文件名访问 (HTTP 403)")

    # 6. 防路径遍历攻击校验
    try:
        await download_excel("../../etc/passwd")
        assert False, "路径遍历攻击应当被拒绝"
    except HTTPException as e:
        assert e.status_code == 404
        print("   -> 成功校验：路径遍历注入攻击被严格拦截 (HTTP 404)")

    print("\n12. 测试普通用户导出干净指标数据与私密智能抽取 API...")
    from app import export_report_clean_data, publish_report_to_db, PublishReportModel
    clean_data_resp = await export_report_clean_data(1)
    clean_file_path = clean_data_resp.path
    assert os.path.exists(clean_file_path)
    wb_clean = openpyxl.load_workbook(clean_file_path)
    assert len(wb_clean.sheetnames) == 1
    assert "ESG定量披露指标数据" in wb_clean.sheetnames
    assert "核验标准与协作规范" not in wb_clean.sheetnames
    ws_clean = wb_clean["ESG定量披露指标数据"]
    headers = [ws_clean.cell(row=3, column=c).value for c in range(1, ws_clean.max_column + 1)]
    assert "指标代码" in headers
    assert "标准化数值" in headers
    assert "【人工核验结论】" not in headers
    assert "【人工修正数值】" not in headers
    assert "是否标注" not in headers
    print("   -> 成功校验：普通用户导出的是干净的单工作表指标数据，零标注列与零指南页！")

    # 测试智能抽取端到端解析 (27项指标 + 范围2双口径 + 随机防猜测下载令牌)
    sample_pdf_name = samples_res["samples"][0]["filename"]
    analyze_res = await analyze_report(
        request=MockRequest(client_ip="10.0.0.88"),
        file=None,
        sample_filename=sample_pdf_name
    )
    assert len(analyze_res["indicators"]) == 27
    ind_codes = {i["code"] for i in analyze_res["indicators"]}
    assert "Q03A" in ind_codes and "Q03B" in ind_codes
    dl_token_name = analyze_res["excel_download_url"].split("/api/download/")[-1]
    assert "__" in dl_token_name
    dl_resp = await download_excel(dl_token_name)
    assert os.path.exists(dl_resp.path)
    print(f"   -> 成功校验：智能抽取精确返回 {len(analyze_res['indicators'])} 项核心指标（含 Q03A/Q03B），随机安全下载链接有效！")

    print("\n13. 测试管理员专属收录入库发布 API (/api/admin/reports/publish)...")
    test_pub_payload = PublishReportModel(
        company_name="测试新能源股份有限公司",
        company_code="688999",
        industry="电力设备 · 光伏设备",
        industry_l1="电力设备",
        industry_l2="光伏设备",
        year=2024,
        title="测试新能源2024年度环境、社会与管治报告",
        total_pages=98,
        disclosure_rate="88.5%",
        verified_rate="88.5%",
        indicators=[
            {
                "code": "Q01",
                "name": "温室气体排放总量",
                "std_value": 45000.0,
                "std_unit": "tCO2e",
                "raw_value": 45000.0,
                "raw_unit": "吨",
                "clause": "沪深指引第21条",
                "page": 28,
                "quote": "2024年度温室气体排放总量为45,000吨二氧化碳当量",
                "verified_in_page": True
            }
        ]
    )

    try:
        await publish_report_to_db(test_pub_payload, MockRequest())
        assert False, "普通访客发布报告入库应被拒绝"
    except HTTPException as e:
        assert e.status_code == 401
        print("   -> 成功校验：未授权访客调用收录入库发布接口被拒绝 (HTTP 401)")

    pub_res = await publish_report_to_db(test_pub_payload, auth_req)
    assert pub_res["status"] == "ok"
    assert pub_res["company_code"] == "688999"
    new_report_id = pub_res["report_id"]
    print(f"   -> 成功校验：管理员携带 Token 成功将新报告入库，生成 report_id={new_report_id}")

    new_stats = await get_platform_stats()
    assert new_stats['total_reports'] == 36
    assert new_stats['total_companies'] == 19

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT audit_status FROM kpi_records WHERE report_id = ? AND indicator_code = 'Q01'", (new_report_id,))
    kpi_row = c.fetchone()
    assert kpi_row["audit_status"] == "AI初抽，待核查"
    conn.close()
    print("   -> 成功校验：新收录报告的所有指标初始状态严格标识为【AI初抽，待核查】！")

    try:
        await publish_report_to_db(test_pub_payload, auth_req)
        assert False, "重复发布应当被拒绝"
    except HTTPException as e:
        assert e.status_code == 400
        print("   -> 成功校验：防重复发布机制生效，重复收录被拒绝 (HTTP 400)")

    await admin_logout(auth_req)

    # 测试完成后自动重置回官方基准数据，并清理测试产生的临时配置文件与测试表格
    init_db(drop_first=True)
    seed_initial_data()
    if had_llm_cfg_before and prev_llm_cfg_bytes is not None:
        LLM_CONFIG_PATH.write_bytes(prev_llm_cfg_bytes)
    else:
        LLM_CONFIG_PATH.unlink(missing_ok=True)
        app_config.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        app_config.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    ADMIN_SESSIONS_PATH.unlink(missing_ok=True)
    for p in (excel_path, clean_file_path, dl_resp.path):
        if p and os.path.exists(p):
            os.remove(p)

    print("   -> 自动化测试完成，数据库与运行目录已重置回纯净官方披露基准状态！")

    print("\n" + "=" * 60)
    print("🎉 恭喜！全流程单元与公网安全集成测试 100% 全部通过！")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_tests())
