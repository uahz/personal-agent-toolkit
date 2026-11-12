# Personal Agent Toolkit

把小红书《Personal Agent 的七种邪修用法》里可复刻的玩法，落地成一套**能直接跑的本地工具**。不依赖任何第三方服务，全部 Python 标准库。

> 为什么叫「可复刻」：原笔记里「自动穿透支付宝账单」依赖特定平台的数据打通能力，别的产品拿不到。本仓库采用**半自动方案**——你导出账单 CSV，工具负责特征扫描与决策计算。

## 包含什么

| 模块 | 对应玩法 | 做什么 |
|---|---|---|
| `bill_audit.py` | 隐蔽扣费与账单审计 | 按「固定商户 + 固定周期 + 固定金额」扫描疑似自动续费，输出扣款周期、年化成本、月度支出与 TOP 商户 |
| `decision_tools.py cooldown` | 带状态与冷却期的自动化 | 3 天冷却队列：近期选过的不重复推荐，候选全在冷却期时**保持静默**，不制造信息垃圾 |
| `decision_tools.py cost` | 复杂要素成本核算 | 跨维度公式：电价 + 优惠 + 停车免扣时长折算综合成本并排序，兼顾空闲桩比 |
| `自定义MCP配置指南.md` | 自定义 MCP / CLI | WorkBuddy 接入本地 Obsidian、Home Assistant、NAS 的配置模板与排障 |
| `落地状态清单.md` | — | 落地进度、待办与已知风险 |

## 快速开始

```bash
# 1. 账单审计（把支付宝/微信导出的账单 CSV 换成你的文件）
python3 bill_audit.py 账单.csv --threshold 3000

# 没有真实账单？先看演示效果
python3 bill_audit.py --demo

# 2. 冷却队列
python3 decision_tools.py cooldown add "楼下牛肉面"
python3 decision_tools.py cooldown check "楼下牛肉面" "隔壁轻食" "公司食堂"
python3 decision_tools.py cooldown list

# 3. 跨维度成本核算
python3 decision_tools.py cost --demo
python3 decision_tools.py cost stations.json --kwh 45 --park 70 --parking-rate 8
```

`cost` 的站点 JSON 格式：

```json
[
  {"name": "A 商场快充", "price": 1.28, "discount": 5.0, "free_min": 120, "idle": 0.6},
  {"name": "B 路边快充", "price": 0.98, "discount": 0.0, "free_min": 15,  "idle": 0.9}
]
```

字段：`price` 元/度、`discount` 直减金额、`free_min` 免费停车分钟、`idle` 空闲桩比例；可选 `kwh`、`park_min`、`parking_rate`（覆盖全局参数）。

## 为什么值得算这一下

演示数据里，只看度电单价会选「E 地库特惠桩」（电费 ¥29.25 全场最低），但它停车免费 0 分钟且停车费 25 元/小时。综合成本算下来是 ¥58.42，反而比 C 园区慢充（¥42.88）**多花 ¥15.53**。单维搜索和跨维决策的差距就在这里。

## 配套自动化

已在 WorkBuddy 上配置两个定时任务（可按需暂停/删除）：

- **月度账单体检**：每月 1 日 09:00，提醒导出账单、跑扫描、给出关闭续费入口
- **冲动消费冷静期盘点**：每周日 20:00，7 天冷静期 + 比价决策，无记录时静默

## 隐私与安全

- **真实账单是私人数据，请勿提交到仓库**；`.gitignore` 已排除根目录的 `*账单*.csv` 与自动生成的报告
- `examples/` 里的 `demo_bill.csv` 与 `bill_audit_report.md` 是**模拟数据**，仅用于演示
- 冷却队列状态存于 `.agent_state/`，已排除，不会公开
- MCP 密钥请放环境变量，不要明文写入 `mcp.json`

## 目录

```
.
├── bill_audit.py               # 账单自动续费扫描
├── decision_tools.py           # 冷却队列 + 综合成本核算
├── 自定义MCP配置指南.md
├── 落地状态清单.md
├── examples/
│   ├── demo_bill.csv           # 模拟账单
│   └── bill_audit_report.md    # 示例报告
└── .gitignore
```

## 已知限制

1. 账单 CSV 表头依赖支付宝/微信导出模板，平台改版可能需要调整列名映射
2. 充电桩场景使用手工录入的站点数据，未接实时桩位 API
3. 原笔记配图里的另外 3 种玩法未抓取，暂未纳入
