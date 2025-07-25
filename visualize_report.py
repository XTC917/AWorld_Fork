import re
import matplotlib.pyplot as plt

input_file = "gaia_llm_agent_report_20250721_094521.md"

# 莫兰迪色系（低饱和度、柔和色）
MORANDI_COLORS = [
    "#a3a7a6",  # 淡灰绿
    "#b7a69e",  # 莫兰迪棕
    "#b0b7b6",  # 莫兰迪蓝灰
    "#c1b7a4",  # 莫兰迪米
]

def parse_stats(md_path):
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()
    # 提取总体结果
    total = int(re.search(r"总题数\*\*: (\d+)", text).group(1))
    correct = int(re.search(r"正确数\*\*: (\d+)", text).group(1))
    acc = float(re.search(r"准确率\*\*: ([\d.]+)%", text).group(1))
    func_count = int(re.search(r"Function Calling 触发数\*\*: (\d+)", text).group(1))
    func_rate = float(re.search(r"Function Calling 触发率\*\*: ([\d.]+)%", text).group(1))
    # 提取分级统计
    level_stats = {}
    for m in re.finditer(r"### Level (\d+)\n- 题数: (\d+)\n- 正确: (\d+)\n- 准确率: ([\d.]+)%\n- Function Calling 触发率: ([\d.]+)%", text):
        level = m.group(1)
        level_stats[level] = {
            "total": int(m.group(2)),
            "correct": int(m.group(3)),
            "acc": float(m.group(4)),
            "func_rate": float(m.group(5)),
        }
    return {
        "total": total,
        "correct": correct,
        "acc": acc,
        "func_count": func_count,
        "func_rate": func_rate,
        "level_stats": level_stats
    }

def plot_single_bar(title, ylabel, labels, values, color, filename):
    plt.figure(figsize=(8, 5))
    bars = plt.bar(labels, values, color=color)
    plt.ylim(0, 100)
    plt.ylabel(ylabel)
    plt.title(title)
    # 在柱状图上方标注数值
    for bar, val in zip(bars, values):
        plt.text(bar.get_x() + bar.get_width()/2, val + 1, f"{val:.2f}%", ha='center', va='bottom', fontsize=12)
    plt.tight_layout()
    plt.savefig(filename, dpi=150)
    plt.close()
    print(f"Saved: {filename}")

if __name__ == "__main__":
    stats = parse_stats(input_file)
    # Labels: Overall, Level 1, Level 2, Level 3
    labels = ["Overall"] + [f"Level {lv}" for lv in sorted(stats["level_stats"].keys(), key=int)]
    accs = [stats["acc"]] + [stats["level_stats"][lv]["acc"] for lv in sorted(stats["level_stats"].keys(), key=int)]
    func_rates = [stats["func_rate"]] + [stats["level_stats"][lv]["func_rate"] for lv in sorted(stats["level_stats"].keys(), key=int)]
    # 画 accuracy
    plot_single_bar(
        title="Accuracy by Level",
        ylabel="Accuracy (%)",
        labels=labels,
        values=accs,
        color=MORANDI_COLORS[:len(labels)],
        filename="accuracy_by_level.png"
    )
    # 画 function calling rate
    plot_single_bar(
        title="Function Calling Rate by Level",
        ylabel="Function Calling Rate (%)",
        labels=labels,
        values=func_rates,
        color=MORANDI_COLORS[:len(labels)],
        filename="function_calling_by_level.png"
    ) 