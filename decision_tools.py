#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
决策工具箱：冷却队列 + 跨维度成本核算
=====================================
补齐 Personal Agent 玩法 2、3 中「状态记忆 / 公式计算」两块：

  cooldown  —— 3 天冷却队列：近期选过的不重复推荐，无合适选项则保持静默
  cost      —— 跨维度成本核算：电价 + 优惠 + 停车免扣时长 折算综合成本并排序

只依赖 Python 标准库。状态持久化在 .agent_state/cooldown.json。

用法示例：
  python3 decision_tools.py cooldown add "楼下牛肉面"
  python3 decision_tools.py cooldown check "楼下牛肉面" "隔壁轻食" "公司食堂"
  python3 decision_tools.py cooldown list
  python3 decision_tools.py cost --demo
  python3 decision_tools.py cost stations.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(BASE, ".agent_state")
STATE_FILE = os.path.join(STATE_DIR, "cooldown.json")
COOL_DAYS = 3


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"items": {}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"items": {}}


def save_state(st):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


# ------------------------------------------------------------ 冷却队列


def cmd_cooldown(args):
    st = load_state()
    items = st.setdefault("items", {})
    now = datetime.now()
    act = args.action

    if act == "add":
        if not args.names:
            raise SystemExit("cooldown add 后面要跟名称，例如：cooldown add \"楼下牛肉面\"")
        for n in args.names:
            items[n] = now.strftime("%Y-%m-%d %H:%M")
        save_state(st)
        print(f"[已记录] {len(args.names)} 项进入 {args.days} 天冷却队列：{', '.join(args.names)}")

    elif act == "check":
        if not args.names:
            raise SystemExit("cooldown check 后面要跟候选名称")
        fresh, blocked = [], []
        for n in args.names:
            ts = items.get(n)
            if ts:
                try:
                    last = datetime.strptime(ts, "%Y-%m-%d %H:%M")
                    left = args.days - (now - last).days
                    if left > 0:
                        blocked.append((n, left))
                        continue
                except ValueError:
                    pass
            fresh.append(n)
        if fresh:
            print(f"[可推荐 {len(fresh)} 项] " + " / ".join(fresh))
            for n, left in blocked:
                print(f"  · 冷却中：{n}（还需 {left} 天）")
        else:
            # 笔记里的关键设计：没有合适选项就保持静默，不制造信息垃圾
            print("（静默：候选全部处于冷却期，本次不推送）")

    elif act == "list":
        if not items:
            print("冷却队列为空。")
        else:
            print(f"冷却队列（{args.days} 天）：")
            for n, ts in sorted(items.items(), key=lambda kv: -datetime.strptime(kv[1], "%Y-%m-%d %H:%M").timestamp()):
                print(f"  · {n}　最后选择：{ts}")

    elif act == "clear":
        save_state({"items": {}})
        print("冷却队列已清空。")


# -------------------------------------------------------- 跨维度成本核算


DEMO_STATIONS = [
    {"name": "A 商场快充", "price": 1.28, "discount": 5.0, "free_min": 120, "idle": 0.6},
    {"name": "B 路边快充", "price": 0.98, "discount": 0.0, "free_min": 15,  "idle": 0.9},
    {"name": "C 园区慢充", "price": 0.79, "discount": 2.0, "free_min": 0,   "idle": 0.3},
    {"name": "D 品牌超充", "price": 1.45, "discount": 10.0, "free_min": 90, "idle": 0.8},
    # 电价全场最低，但停车免费 0 分钟且停车费 25 元/小时 —— 单看单价必踩坑
    {"name": "E 地库特惠桩", "price": 0.65, "discount": 0.0, "free_min": 0,
     "idle": 0.5, "parking_rate": 25},
]


def cmd_cost(args):
    if args.demo:
        stations = DEMO_STATIONS
        print("[演示模式] 使用内置充电桩示例数据\n")
    else:
        with open(args.file, "r", encoding="utf-8") as f:
            stations = json.load(f)

    rows = []
    for s in stations:
        kwh = float(s.get("kwh", args.kwh))
        park_min = float(s.get("park_min", args.park))
        price = float(s["price"])
        discount = float(s.get("discount", 0))
        free = float(s.get("free_min", 0))
        over = max(0.0, park_min - free) / 60.0
        rate = float(s.get("parking_rate", args.parking_rate))
        parking_fee = over * rate
        total = kwh * price - discount + parking_fee
        rows.append({
            "name": s["name"], "kwh": kwh, "elec": kwh * price,
            "discount": discount, "parking": parking_fee,
            "total": total, "idle": float(s.get("idle", 0)),
        })
    rows.sort(key=lambda r: r["total"])

    print(f"综合成本口径：{args.kwh:g} 度电 · 停留 {args.park:g} 分钟 · 超时停车 ¥{args.parking_rate:g}/小时")
    print(f"{'排名':<4}{'站点':<14}{'电费':>9}{'优惠':>8}{'停车费':>9}{'综合成本':>11}{'空闲桩比':>9}")
    print("-" * 66)
    for i, r in enumerate(rows, 1):
        print(f"{i:<4}{r['name']:<14}{r['elec']:>9.2f}{-r['discount']:>8.2f}"
              f"{r['parking']:>9.2f}{r['total']:>11.2f}{r['idle']*100:>8.0f}%")
    print("-" * 66)
    best = rows[0]
    naive = min(rows, key=lambda r: r["elec"])
    print(f"结论：综合成本最低 → {best['name']}（¥{best['total']:.2f}）")
    if naive["name"] != best["name"]:
        print(f"注意：只看电价会选 {naive['name']}（电费 ¥{naive['elec']:.2f}），"
              f"但算上优惠与停车费反而贵 ¥{naive['total']-best['total']:.2f}。")


def main():
    ap = argparse.ArgumentParser(description="冷却队列 + 跨维度成本核算")
    sub = ap.add_subparsers(dest="cmd", required=True)

    cd = sub.add_parser("cooldown", help="3 天冷却队列（状态记忆）")
    cd.add_argument("action", choices=["add", "check", "list", "clear"])
    cd.add_argument("names", nargs="*", help="候选名称")
    cd.add_argument("--days", type=int, default=COOL_DAYS, help="冷却天数（默认 3）")

    co = sub.add_parser("cost", help="跨维度综合成本核算")
    co.add_argument("file", nargs="?", help="站点数据 JSON 文件")
    co.add_argument("--demo", action="store_true", help="使用内置示例数据")
    co.add_argument("--kwh", type=float, default=45, help="充电度数（默认 45）")
    co.add_argument("--park", type=float, default=70, help="预计停留分钟（默认 70）")
    co.add_argument("--parking-rate", type=float, default=8, help="超时停车费 元/小时（默认 8）")

    a = ap.parse_args()
    if a.cmd == "cooldown":
        cmd_cooldown(a)
    else:
        if not (a.demo or a.file):
            raise SystemExit("cost 需要提供 JSON 文件，或使用 --demo。")
        cmd_cost(a)


if __name__ == "__main__":
    main()
