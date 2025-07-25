import re
import sys

# 输入输出文件名
input_file = "gaia_llm_agent_report_20250721_094521.md"
output_file = input_file.replace(".md", "_stripped.md")

def strip_report(input_path, output_path):
    with open(input_path, "r", encoding="utf-8") as fin:
        lines = fin.readlines()

    out_lines = []
    skip = False
    for line in lines:
        # 跳过完整回复代码块
        if line.strip().startswith("**完整回复**"):
            skip = True
            continue
        if skip:
            if line.strip().startswith("```"):
                skip = False
            continue
        # 只保留关键信息
        if line.strip().startswith("**问题**") or \
           line.strip().startswith("**正确答案**") or \
           line.strip().startswith("**模型答案**") or \
           line.strip().startswith("**Function Calling**") or \
           line.strip().startswith("### ") or \
           line.strip() == "---" or line.strip() == "":
            out_lines.append(line)

    with open(output_path, "w", encoding="utf-8") as fout:
        fout.writelines(out_lines)
    print(f"已生成精简版报告: {output_path}")

if __name__ == "__main__":
    strip_report(input_file, output_file) 