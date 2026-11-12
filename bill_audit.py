#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
账单自动续费扫描器（账单审计）
================================
灵感：Personal Agent「隐蔽扣费与账单审计」玩法。
输入支付宝/微信导出的账单 CSV，按「固定商户 + 固定周期 + 固定金额」特征
扫描疑似自动续费，输出：扣款周期、最近扣款日、年化成本、月度支出汇总。

用法：
    python3 bill_audit.py 你的账单.csv
    python3 bill_audit.py 你的账单.csv --threshold 3000   # 月支出告警阈值（元）

支持：支付宝(手机端导出) / 微信支付的账单 CSV，自动识别编码与表头。
只依赖 Python 标准库，无需安装任何第三方包。
"""

import argparse
import csv
import io
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

# ---------------------------------------------------------------- CSV 读取


def read_csv_auto(path):
    """自动尝试常见编码读取账单文件。"""
    raw = open(path, "rb").read()
    last_err = None
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return io.StringIO(raw.decode(enc))
        except UnicodeDecodeError as e:
            last_err = e
    raise SystemExit(f"无法解码文件（请确认为支付宝/微信导出的 CSV）：{last_err}")


def pick(cols, *keys):
    """在表头里模糊匹配列名（兼容支付宝/微信的不同叫法）。"""
    for k in keys:
        for c in cols:
            if k in c:
                return c
    return None


def parse_bill(path):
    """解析账单，返回支出记录列表 [{date, merchant, item, amount}]。"""
    text = read_csv_auto(path)
    lines = text.read().splitlines()

    # 找表头行：包含「交易时间」或「交易对方」的第一行
    header_idx, header = None, None
    for i, ln in enumerate(lines):
        if ("交易时间" in ln or "交易日期" in ln) and ("交易对方" in ln or "交易双方" in ln):
            header_idx, header = i, next(csv.reader(io.StringIO(ln)))
            break
    if header_idx is None:
        raise SystemExit("未找到账单表头（需要包含「交易时间」「交易对方」列），请确认导出的是完整账单 CSV。")

    c_time = pick(header, "交易时间", "交易日期")
    c_party = pick(header, "交易对方", "交易双方", "对方")
    c_item = pick(header, "商品说明", "商品", "备注")
    c_flow = pick(header, "收/支", "收支", "类型")
    c_amt = pick(header, "金额", "金额(元)")

    if not (c_time and c_party and c_amt):
        raise SystemExit(f"表头缺少关键列：{header}")

    rows, skipped = [], 0
    for ln in lines[header_idx + 1:]:
        if not ln.strip() or set(ln.strip()) <= {",", " ", "-"}:
            continue
        try:
            cells = next(csv.reader(io.StringIO(ln)))
        except StopIteration:
            continue
        if len(cells) != len(header):
            skipped += 1
            continue
        rec = dict(zip(header, cells))
        # 收/支过滤：只要支出（微信列值形如「支出」；支付宝可能带「不计收支」）
        if c_flow and ("收入" in rec.get(c_flow, "") or "不计" in rec.get(c_flow, "")):
            continue
        date_s = rec.get(c_time, "").strip().strip('"')
        amount_s = re.sub(r"[^\d.\-]", "", rec.get(c_amt, ""))
        try:
            dt = datetime.strptime(date_s.split(" ")[0], "%Y-%m-%d")
        except ValueError:
            try:
                dt = datetime.strptime(date_s, "%Y/%m/%d")
            except ValueError:
                skipped += 1
                continue
        try:
            amt = float(amount_s)
        except ValueError:
            skipped += 1
            continue
        rows.append({
            "date": dt,
            "merchant": rec.get(c_party, "未知商户").strip(),
            "item": (rec.get(c_item, "") or "").strip(),
            "amount": amt,
        })
    print(f"[解析] 共读入支出记录 {len(rows)} 条" + (f"，跳过异常行 {skipped} 条" if skipped else ""))
    return rows

# ---------------------------------------------------------- 自动续费识别


def guess_cycle(dates):
    """根据同一商户的扣款日期序列，推断扣款周期（天）。返回 None 表示看不出周期。"""
    if len(dates) < 2:
        return None
    gaps = sorted((b - a).days for a, b in zip(dates, dates[1:]))
    med = gaps[len(gaps) // 2]
    for lo, hi, name in ((6, 8, "周付"), (25, 35, "月付"), (85, 95, "季付"), (350, 380, "年付")):
        if lo <= med <= hi:
            return name, med
    return None


def find_recurring(rows):
    """按商户聚合，找「金额一致 + 有固定周期」的疑似自动续费。"""
    by_merchant = defaultdict(list)
    for r in rows:
        by_merchant[r["merchant"]].append(r)

    hits = []
    for m, recs in by_merchant.items():
        if len(recs) < 2:
            continue
        amounts = [round(r["amount"], 2) for r in recs]
        # 金额完全一致（续费典型特征）或极小差异
        if max(amounts) - min(amounts) > 0.01:
            continue
        recs.sort(key=lambda r: r["date"])
        cyc = guess_cycle([r["date"] for r in recs])
        if cyc:
            cycle_name, days = cyc
            amt = amounts[0]
            per_year = {"周付": 52, "月付": 12, "季付": 4, "年付": 1}[cycle_name]
            hits.append({
                "merchant": m,
                "amount": amt,
                "count": len(recs),
                "cycle": f"{cycle_name}(约{days}天)",
                "per_year": per_year,
                "yearly": round(amt * per_year, 2),
                "last": recs[-1]["date"].strftime("%Y-%m-%d"),
                "first": recs[0]["date"].strftime("%Y-%m-%d"),
                "item": recs[-1]["item"][:30],
            })
    hits.sort(key=lambda h: -h["yearly"])
    return hits

# ----------------------------------------------------------------- 报告


def report(rows, hits, threshold, csv_path):
    total = sum(r["amount"] for r in rows)
    by_month = defaultdict(float)
    for r in rows:
        by_month[r["date"].strftime("%Y-%m")] += r["amount"]
    by_merchant = defaultdict(float)
    for r in rows:
        by_merchant[r["merchant"]] += r["amount"]
    top = sorted(by_merchant.items(), key=lambda kv: -kv[1])[:10]

    L = []
    L.append("# 账单体检报告")
    L.append("")
    L.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}　|　支出记录：{len(rows)} 条　|　总支出：¥{total:,.2f}")
    L.append("")

    # 1. 疑似自动续费
    L.append("## 一、疑似自动续费/隐形扣费（重点核查）")
    if not hits:
        L.append("")
        L.append("未发现「固定商户 + 固定金额 + 固定周期」的连续扣款。✅")
    else:
        L.append("")
        L.append("| 商户 | 单笔金额 | 扣款周期 | 已扣次数 | 最近扣款 | 首次扣款 | 年化成本 | 付款内容 |")
        L.append("|---|---|---|---|---|---|---|---|")
        for h in hits:
            L.append(f"| {h['merchant']} | ¥{h['amount']:.2f} | {h['cycle']} | {h['count']} | {h['last']} | {h['first']} | **¥{h['yearly']:,.2f}** | {h['item']} |")
        yearly_sum = sum(h["yearly"] for h in hits)
        L.append("")
        L.append(f"**疑似续费年化合计：¥{yearly_sum:,.2f}** —— 逐条确认，用不上的马上去对应 App 关闭自动续费。")
    L.append("")

    # 2. 月度支出与告警
    L.append("## 二、月度支出")
    L.append("")
    L.append("| 月份 | 支出 |")
    L.append("|---|---|")
    for m in sorted(by_month):
        flag = ""
        if threshold and by_month[m] > threshold:
            flag = f" ⚠️ 超过阈值 ¥{threshold:,.0f}"
        L.append(f"| {m} | ¥{by_month[m]:,.2f}{flag} |")
    L.append("")

    # 3. TOP 商户
    L.append("## 三、支出 TOP 10 商户")
    L.append("")
    L.append("| 商户 | 累计支出 | 占比 |")
    L.append("|---|---|---|")
    for m, v in top:
        L.append(f"| {m} | ¥{v:,.2f} | {v/total*100:.1f}% |")
    L.append("")

    L.append("## 四、行动建议")
    L.append("")
    L.append("1. 表一里每一项都去对应 App 的「设置-支付-自动扣款/订阅管理」确认并关闭不用的；")
    L.append("2. 支付宝入口：我的 → 设置 → 支付设置 → 免密支付/自动扣款；微信入口：我 → 服务 → 钱包 → 支付设置 → 自动续费；")
    L.append("3. 建议每月跑一次本脚本（可配合自动化定时任务提醒），把被动扣费变成主动防御。")

    out = "\n".join(L)
    out_path = os.path.join(os.path.dirname(os.path.abspath(csv_path)), "bill_audit_report.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out)
    return out, out_path

# --------------------------------------------------------------- 演示模式


def make_demo_csv(path):
    """生成一份演示账单：3 个伪装成月付的自动续费 + 若干零散消费。"""
    from datetime import timedelta
    import csv
    import random
    random.seed(7)
    rows = []
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    subs = [("爱奇艺黄金会员", 25.00, "自动续费-月卡"),
            ("网易云音乐黑胶VIP", 15.00, "连续包月"),
            ("某云盘超级会员", 30.00, "自动续费")]
    for name, amt, item in subs:
        for k in range(4):
            d = today - timedelta(days=30 * k + random.randint(-2, 2))
            rows.append([d.strftime("%Y-%m-%d"), name, item, "支出", f"{amt:.2f}"])
    misc = [("美团平台商户", 35.5, "外卖"), ("滴滴出行", 22.0, "打车"),
            ("盒马鲜生", 128.4, "生鲜采购"), ("京东商城", 299.0, "数码配件"),
            ("便利店", 12.5, "早餐")]
    for name, amt, item in misc:
        for _ in range(3):
            d = today - timedelta(days=random.randint(0, 90))
            rows.append([d.strftime("%Y-%m-%d"), name, item, "支出",
                         f"{amt * random.uniform(0.5, 1.5):.2f}"])
    rows.sort(key=lambda r: r[0])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["交易时间", "交易对方", "商品说明", "收/支", "金额(元)"])
        w.writerows(rows)
    return path


# ----------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description="账单自动续费扫描器")
    ap.add_argument("csv", nargs="?", help="支付宝/微信导出的账单 CSV 路径")
    ap.add_argument("--threshold", type=float, default=0, help="月度支出告警阈值（元），0 为不告警")
    ap.add_argument("--demo", action="store_true", help="不喂真实账单，直接生成演示数据出报告")
    a = ap.parse_args()

    if a.demo:
        a.csv = make_demo_csv(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "demo_bill.csv"))
        print("[演示模式] 已生成示例账单，以下报告为模拟数据，仅用于查看效果\n")
    elif not a.csv:
        raise SystemExit("请提供账单 CSV 路径，或使用 --demo 查看演示效果。")

    rows = parse_bill(a.csv)
    if not rows:
        raise SystemExit("没有解析到任何支出记录。")

    hits = find_recurring(rows)
    out, out_path = report(rows, hits, a.threshold, a.csv)
    print(out)
    print(f"\n[完成] 报告已保存：{out_path}")


if __name__ == "__main__":
    main()
