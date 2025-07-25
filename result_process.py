import re
import sys

def parse_report(file_path):
    # 初始化统计数据结构
    overall = {
        'total': 0,
        'correct': 0,
        'fc_triggered': 0
    }
    
    levels = {
        '1': {'total': 0, 'correct': 0, 'fc_triggered': 0},
        '2': {'total': 0, 'correct': 0, 'fc_triggered': 0},
        '3': {'total': 0, 'correct': 0, 'fc_triggered': 0}
    }
    
    # 读取文件内容
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 分割题目块
    question_blocks = re.split(r'\n---\n', content)
    
    # 解析每个题目块
    for block in question_blocks:
        if not block.strip():
            continue
        
        # 提取难度级别
        level_match = re.search(r'\(Level (\d)\)', block)
        if not level_match:
            continue
        level = level_match.group(1)
        
        # 只处理1-3级题目
        if level not in ['1', '2', '3']:
            continue
        
        # 更新总体和级别统计
        overall['total'] += 1
        levels[level]['total'] += 1
        
        # 检查是否正确
        if '✅' in block.split('\n')[0]:
            overall['correct'] += 1
            levels[level]['correct'] += 1
        
        # 检查Function Calling
        fc_match = re.search(r'\*\*Function Calling\*\*: (\w+)', block)
        if fc_match and fc_match.group(1) == 'True':
            overall['fc_triggered'] += 1
            levels[level]['fc_triggered'] += 1
    
    # 计算准确率和触发率
    def calculate_rates(data):
        total = data['total']
        return {
            'total': total,
            'correct': data['correct'],
            'accuracy': data['correct'] / total if total > 0 else 0,
            'fc_triggered': data['fc_triggered'],
            'fc_rate': data['fc_triggered'] / total if total > 0 else 0
        }
    
    overall_stats = calculate_rates(overall)
    level_stats = {level: calculate_rates(levels[level]) for level in levels}
    
    # 格式化输出结果
    def format_output(stats):
        return (
            f"- 题数: {stats['total']}\n"
            f"- 正确: {stats['correct']}\n"
            f"- 准确率: {stats['accuracy']:.2%}\n"
            f"- Function Calling 触发率: {stats['fc_rate']:.2%}"
        )
    
    # 生成最终报告
    report = [
        "## 总体结果",
        f"- **总题数**: {overall_stats['total']}",
        f"- **正确数**: {overall_stats['correct']}",
        f"- **准确率**: {overall_stats['accuracy']:.2%}",
        f"- **Function Calling 触发数**: {overall_stats['fc_triggered']}",
        f"- **Function Calling 触发率**: {overall_stats['fc_rate']:.2%}",
        "\n## 按难度统计"
    ]
    
    for level in sorted(level_stats.keys()):
        report.extend([
            f"\n### Level {level}",
            format_output(level_stats[level])
        ])
    
    return '\n'.join(report)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("请提供报告文件路径")
        sys.exit(1)
    
    result = parse_report(sys.argv[1])
    print(result)