import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# 自动加载项目根目录下的 .env 环境变量配置（无需额外第三方依赖，线上环境变量优先级更高）
_env_file = BASE_DIR / ".env"
if _env_file.is_file():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        _k = _k.strip()
        _v = _v.strip().strip('"').strip("'")
        if _k and _k not in os.environ:
            os.environ[_k] = _v

# 大模型配置（支持从环境变量/.env加载，或管理员后台动态持久化设置）
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "deepseek-chat")

# 默认供应商: "gemini" 或 "openai" (兼容 deepseek/qwen)
DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "gemini" if GEMINI_API_KEY else "openai")

# 核心可持续发展指标定义（严格依据上交所14号指引《上市公司自律监管指引第14号——可持续发展报告（试行）》三大维度 21 个核心议题）
INDICATORS = [
    # ==================== 1. 环境信息披露维度 (E - 14项) ====================
    {
        "code": "Q01",
        "name": "温室气体排放总量",
        "dimension": "环境维度 (E)",
        "clause": "第二十四条第一款",
        "standard_unit": "tCO2e",
        "priority": "必做指标",
        "keywords": ["温室气体", "温室气体排放总量", "排放总量", "总排放量", "tCO2e", "二氧化碳当量"],
        "description": "报告期内温室气体排放总量，通常包含范围1和范围2直接与间接排放总量。"
    },
    {
        "code": "Q02",
        "name": "范围1 直接排放量",
        "dimension": "环境维度 (E)",
        "clause": "第二十四条第一款",
        "standard_unit": "tCO2e",
        "priority": "必做指标",
        "keywords": ["范围一", "范围 1", "范围1", "直接温室气体排放", "直接排放", "Scope 1"],
        "description": "企业拥有或控制的排放源产生的直接温室气体排放。"
    },
    {
        "code": "Q03A",
        "name": "范围2 间接排放量（基于位置法）",
        "dimension": "环境维度 (E)",
        "clause": "第二十四条第一款",
        "standard_unit": "tCO2e",
        "priority": "必做指标",
        "keywords": ["范围二", "范围2", "基于位置", "位置法", "能源间接", "Scope 2 Location-based"],
        "description": "外购电力、热力或蒸汽等消耗引起的间接温室气体排放（基于所在区域电网平均排放因子计算）。"
    },
    {
        "code": "Q03B",
        "name": "范围2 间接排放量（基于市场法）",
        "dimension": "环境维度 (E)",
        "clause": "第二十四条第一款",
        "standard_unit": "tCO2e",
        "priority": "必做指标",
        "keywords": ["范围二", "范围2", "基于市场", "市场法", "绿电抵扣", "Scope 2 Market-based"],
        "description": "外购电力、热力等消耗引起的间接温室气体排放（计入绿电交易或可再生能源凭证等市场化合同抵扣）。"
    },
    {
        "code": "Q04",
        "name": "范围3 价值链其他间接排放量",
        "dimension": "环境维度 (E)",
        "clause": "第二十四条第一款",
        "standard_unit": "tCO2e",
        "priority": "鼓励披露",
        "keywords": ["范围三", "范围 3", "范围3", "价值链排放", "Scope 3", "其他间接"],
        "description": "价值链上下游发生的其他间接温室气体排放。"
    },
    {
        "code": "Q07",
        "name": "温室气体减排目标与规划",
        "dimension": "环境维度 (E)",
        "clause": "第二十七条第一款",
        "standard_unit": "目标年/比例(%)",
        "priority": "必做指标",
        "keywords": ["减排目标", "碳达峰", "碳中和", "基准年", "目标年", "降碳目标"],
        "description": "企业设定的未来温室气体减排规划、达峰中和路径与目标年指标。"
    },
    {
        "code": "Q08",
        "name": "年度节能与技改工程减碳量",
        "dimension": "环境维度 (E)",
        "clause": "第二十六条",
        "standard_unit": "tCO2e",
        "priority": "核心指标",
        "keywords": ["节能减排量", "工程减碳量", "技改节能量", "二氧化碳减排量", "年度减排", "节能降碳项目"],
        "description": "企业通过能效提升、余热回收及工艺革新等节能减碳工程直接实现的温室气体减排量。"
    },
    {
        "code": "Q09",
        "name": "有害废弃物（危险废物）产生量",
        "dimension": "环境维度 (E)",
        "clause": "第三十一条（一）",
        "standard_unit": "t",
        "priority": "必做指标",
        "keywords": ["危险废物", "有害废弃物", "危废产生量", "危废总量"],
        "description": "生产经营过程中产生的有害废弃物或危险废物总量。"
    },
    {
        "code": "Q10",
        "name": "一般固体废弃物产生量",
        "dimension": "环境维度 (E)",
        "clause": "第三十一条（一）",
        "standard_unit": "t",
        "priority": "必做指标",
        "keywords": ["无害废弃物", "一般固体废物", "一般工业固废", "无害固废", "固废产生总量"],
        "description": "生产经营过程中产生的一般工业固体废弃物总量。"
    },
    {
        "code": "Q11",
        "name": "环保与生态治理专项资金投入",
        "dimension": "环境维度 (E)",
        "clause": "第三十条（一）",
        "standard_unit": "万元",
        "priority": "核心指标",
        "keywords": ["环保投入", "环保资金投入", "污染治理投入", "生态环境保护投入", "环保支出"],
        "description": "报告期内用于污染治理设施建设、运维、绿化及生态保护的年度专项资金投入。"
    },
    {
        "code": "Q12",
        "name": "综合能源消耗总量",
        "dimension": "环境维度 (E)",
        "clause": "第三十五条（一）",
        "standard_unit": "tce",
        "priority": "必做指标",
        "keywords": ["综合能源", "能源消耗总量", "能源消费总量", "总能耗", "吨标准煤", "tce"],
        "description": "企业消耗的各类能源经折标折算后的综合能源消耗总量。"
    },
    {
        "code": "Q13",
        "name": "外购电力消耗总量",
        "dimension": "环境维度 (E)",
        "clause": "第三十五条（一）",
        "standard_unit": "MWh",
        "priority": "必做指标",
        "keywords": ["外购电力", "电力消耗", "用电量", "市政供电", "MWh", "千瓦时"],
        "description": "外购电力总用量（与范围2排放存在核算勾稽关系）。"
    },
    {
        "code": "Q15",
        "name": "清洁能源使用量及占比",
        "dimension": "环境维度 (E)",
        "clause": "第三十五条（二）",
        "standard_unit": "MWh / %",
        "priority": "必做指标",
        "keywords": ["清洁能源", "可再生能源", "绿电", "光伏用电", "清洁能源使用比例"],
        "description": "清洁能源或可再生能源的使用总量及占总能耗的百分比。"
    },
    {
        "code": "Q16",
        "name": "水资源消耗总量（总取水量）",
        "dimension": "环境维度 (E)",
        "clause": "第三十六条（一）",
        "standard_unit": "t",
        "priority": "必做指标",
        "keywords": ["总耗水量", "总取水量", "新鲜水用量", "用水量", "耗水总量"],
        "description": "企业生产与运营的总耗水量或总取水量。"
    },
    {
        "code": "Q17",
        "name": "工业水资源循环利用率",
        "dimension": "环境维度 (E)",
        "clause": "第三十六条（一）",
        "standard_unit": "%",
        "priority": "核心指标",
        "keywords": ["水重复利用率", "水循环利用率", "中水回用率", "循环用水比例"],
        "description": "生产过程中经处理循环重复利用的水量占工业总用水量的比例。"
    },

    # ==================== 2. 社会责任信息披露维度 (S - 8项) ====================
    {
        "code": "Q21",
        "name": "研发投入金额及占营业收入比例",
        "dimension": "社会维度 (S)",
        "clause": "第四十二条（二）",
        "standard_unit": "万元 / %",
        "priority": "必做指标",
        "keywords": ["研发投入", "研发费用", "研发支出", "研发投入占营收比例", "研发投入占营业收入"],
        "description": "企业年度研发资金总投入及占营业收入比例（可与财务报表交叉校验）。"
    },
    {
        "code": "Q22",
        "name": "研发人员总数及占员工总数比例",
        "dimension": "社会维度 (S)",
        "clause": "第四十二条（二）",
        "standard_unit": "人 / %",
        "priority": "核心指标",
        "keywords": ["研发人员", "研发技术人员", "研发人员数量", "研发人员占比", "科技创新人才"],
        "description": "报告期末专职从事科技创新与产品技术研发的人员总数及占比。"
    },
    {
        "code": "Q23",
        "name": "报告期内新增专利授权数量",
        "dimension": "社会维度 (S)",
        "clause": "第四十二条（二）",
        "standard_unit": "件",
        "priority": "核心指标",
        "keywords": ["新增专利", "专利授权", "发明专利", "累计授权专利", "新增授权专利"],
        "description": "年度内获国家知识产权局或国际机构正式授权的有效专利件数。"
    },
    {
        "code": "Q24",
        "name": "乡村振兴与社会公益慈善捐赠金额",
        "dimension": "社会维度 (S)",
        "clause": "第四十条",
        "standard_unit": "万元",
        "priority": "核心指标",
        "keywords": ["对外捐赠", "公益捐赠", "乡村振兴投入", "慈善捐款", "精准扶贫", "社会公益支出"],
        "description": "报告期内投入精准帮扶、乡村振兴产业发展及社会公益慈善捐赠资金总额。"
    },
    {
        "code": "Q25",
        "name": "期末在职员工总数及女性员工占比",
        "dimension": "社会维度 (S)",
        "clause": "第五十条（一）",
        "standard_unit": "人 / %",
        "priority": "必做指标",
        "keywords": ["员工总人数", "员工总数", "在职员工", "女性员工", "女性比例", "在册员工"],
        "description": "报告期末在册全职员工总人数及女性职工比例。"
    },
    {
        "code": "Q26",
        "name": "员工专业培训与技能提升总学时",
        "dimension": "社会维度 (S)",
        "clause": "第五十条（一）",
        "standard_unit": "小时",
        "priority": "核心指标",
        "keywords": ["员工培训", "培训总时长", "培训学时", "人均培训学时", "员工培训总时数"],
        "description": "报告期内开展全员职业技能、安全及职业发展培训的总课时累计数。"
    },
    {
        "code": "Q27",
        "name": "生产安全事故起数及因工死亡人数",
        "dimension": "社会维度 (S)",
        "clause": "第五十条（二）",
        "standard_unit": "起 / 人",
        "priority": "必做指标",
        "keywords": ["安全事故", "生产安全事故", "因工死亡", "工亡人数", "伤亡事故"],
        "description": "报告期内发生的生产安全事故起数及工伤死亡员工人数。"
    },
    {
        "code": "Q28",
        "name": "安全生产与职业健康保障专项资金投入",
        "dimension": "社会维度 (S)",
        "clause": "第五十条（二）",
        "standard_unit": "万元",
        "priority": "核心指标",
        "keywords": ["安全生产投入", "安全投入", "安全防护支出", "职业病防治投入", "劳动保护投入"],
        "description": "用于安全防护设备采购改造、劳防用品配备及职业病危害防治的年度专项资金。"
    },

    # ==================== 3. 公司治理与独立鉴证维度 (G - 4项) ====================
    {
        "code": "Q29",
        "name": "反商业贿赂及反贪污廉洁培训学时",
        "dimension": "治理维度 (G)",
        "clause": "第五十五条（三）",
        "standard_unit": "小时",
        "priority": "必做指标",
        "keywords": ["反商业贿赂", "反贪污", "反腐败培训", "廉洁培训", "商业道德培训"],
        "description": "接受反商业贿赂及反贪污廉洁合规培训的总学时或人次。"
    },
    {
        "code": "Q30",
        "name": "第三方独立审验与鉴证情况",
        "dimension": "治理维度 (G)",
        "clause": "第五十八条",
        "standard_unit": "类别字段",
        "priority": "必做指标",
        "keywords": ["鉴证报告", "审验声明", "独立审验", "第三方鉴证", "AA1000", "ISAE 3000", "ISAE 3410", "有限保证", "合理保证"],
        "description": "是否有第三方独立机构出具审验/鉴证声明，含机构名称、审验依据及保证程度。"
    },
    {
        "code": "Q31",
        "name": "商业贿赂与贪腐不正当竞争诉讼案件数",
        "dimension": "治理维度 (G)",
        "clause": "第五十五条（三）",
        "standard_unit": "件",
        "priority": "核心指标",
        "keywords": ["贪腐诉讼", "贿赂案件", "贪腐立案", "不正当竞争案件", "贪污诉讼"],
        "description": "报告期内发生的涉及商业贿赂、贪腐或重大不正当竞争且已立案或结案的诉讼案件数。"
    },
    {
        "code": "Q32",
        "name": "董事会成员人数及独立董事占比",
        "dimension": "治理维度 (G)",
        "clause": "第十八条",
        "standard_unit": "人 / %",
        "priority": "核心指标",
        "keywords": ["董事会人数", "独立董事", "独董比例", "独立董事人数", "董事会结构"],
        "description": "董事会总人数及独立董事人数所占比例（证监会规定独立董事比例不得低于三分之一）。"
    }
]
