#!/usr/bin/env python3
"""
GAIA 评测脚本 - 简化版
直接调用 Qwen3 模型对 GAIA 数据集进行评测
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Any
import httpx

# 添加agent_deploy目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'agent_deploy'))

# 导入agent
from qwen3_agent.agent import AWorldAgent

# 新增：AWorld llm_agent自动用工具的评测流程
from aworld.agents.llm_agent import Agent as LLM_Agent
from aworld.core.common import Observation, StatefulObservation
from aworld.core.tool.tool_desc import get_tool_desc
from aworld.config.conf import AgentConfig, ModelConfig
from aworld.core.context.base import Context

QWEN3_API_URL = "https://modelfactory.lenovo.com/app-workspace-172-1749106801220-vscode/v1/chat/completions"

class GaiaEvaluator:
    def __init__(self):
        self.results = []
        self.agent = AWorldAgent()
    
    def load_dataset(self) -> List[Dict[str, Any]]:
        """加载GAIA数据集"""
        dataset_path = "examples/gaia/GAIA/2023/metadata.jsonl"
        
        if not os.path.exists(dataset_path):
            print(f"❌ 数据集文件不存在: {dataset_path}")
            return []
        
        dataset = []
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        item = json.loads(line)
                        dataset.append(item)
            print(f"✅ 成功加载 {len(dataset)} 条 GAIA 数据")
            return dataset
        except Exception as e:
            print(f"❌ 加载数据集失败: {e}")
            return []
    
    async def call_agent(self, messages: List[Dict[str, str]]) -> str:
        """通过agent调用Qwen3"""
        try:
            # 构造请求对象
            class MockRequest:
                def __init__(self, messages):
                    self.messages = messages
            
            class MockMessage:
                def __init__(self, role, content):
                    self.role = role
                    self.content = content
            
            # 转换消息格式
            mock_messages = []
            for msg in messages:
                mock_messages.append(MockMessage(msg["role"], msg["content"]))
            
            request = MockRequest(mock_messages)
            
            # 调用agent
            response_content = ""
            async for content in self.agent.run(request=request):
                response_content += content
            
            return response_content
        except Exception as e:
            return f"[Agent调用失败] {e}"
    
    def extract_answer(self, response: str) -> str:
        """从模型回复中提取答案"""
        # 尝试提取 <answer> 标签中的内容
        import re
        match = re.search(r'<answer>(.*?)</answer>', response, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # 如果没有标签，尝试提取最后一段作为答案
        lines = response.strip().split('\n')
        for line in reversed(lines):
            if line.strip() and not line.startswith('#'):
                return line.strip()
        
        return response.strip()
    
    def score_answer(self, predicted: str, correct: str) -> bool:
        """评分函数 - 简单字符串匹配"""
        predicted = predicted.lower().strip()
        correct = correct.lower().strip()
        
        # 直接匹配
        if predicted == correct:
            return True
        
        # 包含关系
        if correct in predicted or predicted in correct:
            return True
        
        # 数字匹配（去除空格和标点）
        import re
        pred_clean = re.sub(r'[^\w]', '', predicted)
        corr_clean = re.sub(r'[^\w]', '', correct)
        if pred_clean == corr_clean:
            return True
        
        return False
    
    async def evaluate_single_question(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """评测单个问题"""
        question = item["Question"]
        correct_answer = item["Final answer"]
        task_id = item["task_id"]
        level = item["Level"]
        
        print(f"\n🔍 评测问题 {task_id} (Level {level}):")
        print(f"问题: {question[:100]}...")
        
        # 取推理步数
        reasoning_steps = 0
        try:
            steps_str = item.get("Annotator Metadata", {}).get("Number of steps", "0")
            reasoning_steps = int(steps_str)
        except Exception:
            pass
        # 取工具列表
        tool_list = []
        try:
            tools_str = item.get("Annotator Metadata", {}).get("Tools", "")
            for line in tools_str.splitlines():
                tool = line.strip()
                if tool:
                    # 去掉前面的编号和点
                    tool = tool.split('.', 1)[-1].strip()
                    # 去掉括号内容
                    import re
                    tool = re.sub(r"\\(.*?\\)", "", tool).strip()
                    if tool:
                        tool_list.append(tool)
        except Exception:
            pass
        # 取工具数量，优先Annotator Metadata，其次最外层，最后用工具列表长度兜底
        tool_count = 0
        try:
            tool_count_str = item.get("Annotator Metadata", {}).get("Number of tools")
            if tool_count_str is None:
                tool_count_str = item.get("Number of tools")
            if tool_count_str is not None:
                tool_count = int(tool_count_str)
            # 如果工具列表长度和数量不一致，以工具列表长度为准
            if tool_count == 0 and tool_list:
                tool_count = len(tool_list)
        except Exception:
            tool_count = len(tool_list)
        group = level
        print(f"  推理步数: {reasoning_steps}")
        print(f"  工具数量: {tool_count}")
        print(f"  工具列表: {tool_list}")
        print(f"  分组(Level): {group}")
        
        # 构造消息
        messages = [
            {"role": "system", "content": "你是一个知识渊博的AI助手。请严格按照如下要求回答：1. 只输出最终答案，不要输出推理过程。2. 答案必须用<answer>标签包裹，例如<answer>42</answer>。3. 如果无法回答，输出<answer>无法回答</answer>。"},
            {"role": "user", "content": question}
        ]
        
        # 调用agent
        response = await self.call_agent(messages)
        predicted_answer = self.extract_answer(response)
        
        # 评分
        is_correct = self.score_answer(predicted_answer, correct_answer)
        
        result = {
            "task_id": task_id,
            "level": level,
            "question": question,
            "correct_answer": correct_answer,
            "predicted_answer": predicted_answer,
            "full_response": response,
            "is_correct": is_correct
        }
        
        status = "✅" if is_correct else "❌"
        print(f"{status} 预测: {predicted_answer} | 正确答案: {correct_answer}")
        
        return result
    
    async def run_evaluation(self, max_questions: int = 10):
        """运行完整评测"""
        print("🚀 开始 GAIA 评测...")
        
        # 加载数据集
        dataset = self.load_dataset()
        if not dataset:
            return
        
        # 限制评测数量
        if max_questions > 0:
            dataset = dataset[:max_questions]
        
        print(f"📊 将评测 {len(dataset)} 个问题")
        
        # 逐个评测
        for i, item in enumerate(dataset, 1):
            try:
                result = await self.evaluate_single_question(item)
                self.results.append(result)
                
                # 显示进度
                correct_count = sum(1 for r in self.results if r["is_correct"])
                accuracy = correct_count / len(self.results) * 100
                print(f"📈 进度: {i}/{len(dataset)} | 准确率: {accuracy:.1f}% ({correct_count}/{len(self.results)})")
                
                # 避免请求过快
                await asyncio.sleep(1)
                
            except Exception as e:
                print(f"❌ 评测问题 {item.get('task_id', 'unknown')} 失败: {e}")
                continue
        
        # 生成报告
        self.generate_report()
    
    def generate_report(self):
        """生成评测报告"""
        if not self.results:
            print("❌ 没有评测结果")
            return
        
        # 统计结果
        total = len(self.results)
        correct = sum(1 for r in self.results if r["is_correct"])
        accuracy = correct / total * 100 if total > 0 else 0
        
        # 按难度统计
        level_stats = {}
        for result in self.results:
            level = result["level"]
            if level not in level_stats:
                level_stats[level] = {"total": 0, "correct": 0}
            level_stats[level]["total"] += 1
            if result["is_correct"]:
                level_stats[level]["correct"] += 1
        
        # ========== 新增多维度统计 ===========
        # 1. 平均推理步数
        reasoning_steps = []
        # 2. 平均工具使用数量
        tool_counts = []
        # 3. 工具使用频率统计
        tool_freq = {}
        # 4. 按题型分组准确率（以Level为例）
        group_accuracy = {}
        
        # 需要重新加载原始数据以提取元数据
        dataset_path = "examples/gaia/GAIA/2023/metadata.jsonl"
        dataset = []
        if os.path.exists(dataset_path):
            with open(dataset_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        item = json.loads(line)
                        dataset.append(item)
        # 构建 task_id 到元数据的映射
        meta_map = {item.get("task_id"): item for item in dataset}
        
        for result in self.results:
            task_id = result["task_id"]
            meta = meta_map.get(task_id, {})
            # 平均推理步数
            steps = None
            try:
                steps = meta.get("Annotator Metadata", {}).get("Number of steps")
                if steps is not None:
                    reasoning_steps.append(steps)
            except Exception:
                pass
            # 平均工具使用数量
            tool_num = None
            try:
                tool_num = meta.get("Number of tools")
                if tool_num is not None:
                    tool_counts.append(tool_num)
            except Exception:
                pass
            # 工具使用频率
            try:
                tools = meta.get("Tools", [])
                for tool in tools:
                    tool_freq[tool] = tool_freq.get(tool, 0) + 1
            except Exception:
                pass
            # 按题型分组准确率（以Level为例）
            group = meta.get("Level", "Unknown")
            group = str(group)  # 保证group为字符串，避免int+str错误
            if group not in group_accuracy:
                group_accuracy[group] = {"total": 0, "correct": 0}
            group_accuracy[group]["total"] += 1
            if result["is_correct"]:
                group_accuracy[group]["correct"] += 1
        
        avg_reasoning_steps = round(sum(reasoning_steps) / len(reasoning_steps), 2) if reasoning_steps else 0
        avg_tools_used = round(sum(tool_counts) / len(tool_counts), 2) if tool_counts else 0
        
        # 组准确率
        group_acc_json = {k: (v["correct"] / v["total"] if v["total"] else 0) for k, v in group_accuracy.items()}
        
        # 输出JSON统计
        stats_json = {
            "overall_accuracy": round(accuracy / 100, 4),
            "avg_reasoning_steps": avg_reasoning_steps,
            "avg_tools_used": avg_tools_used,
            "tool_usage_stats": tool_freq,
            "group_accuracy": group_acc_json
        }
        print("\n📊 评测多维度统计(JSON):\n" + json.dumps(stats_json, ensure_ascii=False, indent=2))
        
        # ========== 保留原有报告输出 ===========
        # 生成报告
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"gaia_evaluation_report_{timestamp}.md"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("# GAIA 评测报告\n\n")
            f.write(f"**评测时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**模型**: Qwen3-235B-A22B-FP8\n\n")
            f.write(f"**API**: {QWEN3_API_URL}\n\n")
            
            f.write("## 总体结果\n\n")
            f.write(f"- **总题数**: {total}\n")
            f.write(f"- **正确数**: {correct}\n")
            f.write(f"- **准确率**: {accuracy:.2f}%\n\n")
            
            f.write("## 按难度统计\n\n")
            for level in sorted(level_stats.keys()):
                stats = level_stats[level]
                level_accuracy = stats["correct"] / stats["total"] * 100
                f.write(f"### Level {level}\n")
                f.write(f"- 题数: {stats['total']}\n")
                f.write(f"- 正确: {stats['correct']}\n")
                f.write(f"- 准确率: {level_accuracy:.2f}%\n\n")
            
            f.write("## 详细结果\n\n")
            for result in self.results:
                status = "✅" if result["is_correct"] else "❌"
                f.write(f"### {status} {result['task_id']} (Level {result['level']})\n\n")
                f.write(f"**问题**: {result['question']}\n\n")
                f.write(f"**正确答案**: {result['correct_answer']}\n\n")
                f.write(f"**模型答案**: {result['predicted_answer']}\n\n")
                f.write(f"**完整回复**:\n```\n{result['full_response']}\n```\n\n")
                f.write("---\n\n")
        
        print(f"\n📋 评测报告已生成: {report_file}")
        print(f"📊 总体准确率: {accuracy:.2f}% ({correct}/{total})")

class GaiaLlmAgentEvaluator:
    def __init__(self, tool_names=None):
        self.results = []
        # 工具名列表，自动获取所有已注册工具
        if tool_names is None:
            tool_names = list(get_tool_desc().keys())
        # 构造最小可用AgentConfig
        conf = AgentConfig(
            name="llm_agent",
            llm_config=ModelConfig(
                llm_provider="qwen-openai",
                llm_model_name="qwen-turbo",
                llm_api_key="sk-xxx",  # 你可以改成自己的key
                llm_base_url="https://api.openai.com/v1"
            ),
            system_prompt="你是一个善于使用工具的AI助手。",
            agent_prompt="你是一个善于使用工具的AI助手。"
        )
        self.agent = LLM_Agent(conf=conf, name="llm_agent", tool_names=tool_names)

    async def call_agent(self, question: str) -> str:
        obs = StatefulObservation(content=question, context=[])
        # llm_agent支持async_run
        try:
            result = await self.agent.async_run(obs)
            # result.answer 可能是最终答案
            return getattr(result, 'answer', str(result))
        except Exception as e:
            return f"[llm_agent调用失败] {e}"

    async def evaluate_single_question(self, item: Dict[str, Any]) -> Dict[str, Any]:
        question = item["Question"]
        correct_answer = item["Final answer"]
        task_id = item["task_id"]
        level = item["Level"]
        print(f"\n🔍 [llm_agent] 评测问题 {task_id} (Level {level}):")
        print(f"问题: {question[:100]}...")
        response = await self.call_agent(question)
        predicted_answer = response.strip()
        is_correct = predicted_answer.lower() == correct_answer.lower()
        result = {
            "task_id": task_id,
            "level": level,
            "question": question,
            "correct_answer": correct_answer,
            "predicted_answer": predicted_answer,
            "full_response": response,
            "is_correct": is_correct
        }
        status = "✅" if is_correct else "❌"
        print(f"{status} 预测: {predicted_answer} | 正确答案: {correct_answer}")
        return result

    async def run_evaluation(self, max_questions: int = 10):
        print("🚀 [llm_agent] 开始 GAIA 工具链评测...")
        dataset_path = "examples/gaia/GAIA/2023/metadata.jsonl"
        dataset = []
        if not os.path.exists(dataset_path):
            print(f"❌ 数据集文件不存在: {dataset_path}")
            return
        with open(dataset_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    dataset.append(item)
        if max_questions > 0:
            dataset = dataset[:max_questions]
        print(f"📊 将评测 {len(dataset)} 个问题")
        accuracy = 0.0
        correct_count = 0
        for i, item in enumerate(dataset, 1):
            try:
                result = await self.evaluate_single_question(item)
                self.results.append(result)
                correct_count = sum(1 for r in self.results if r["is_correct"])
                accuracy = correct_count / len(self.results) * 100
                print(f"📈 进度: {i}/{len(dataset)} | 准确率: {accuracy:.1f}% ({correct_count}/{len(self.results)})")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"❌ 评测问题 {item.get('task_id', 'unknown')} 失败: {e}")
                continue
        print(f"\n📊 [llm_agent] 工具链评测准确率: {accuracy:.2f}% ({correct_count}/{len(self.results)})")

# 主函数支持两种评测模式
async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['qwen3', 'llm_agent'], default='qwen3', help='选择评测模式')
    parser.add_argument('--max_questions', type=int, default=10)
    args = parser.parse_args()
    if args.mode == 'llm_agent':
        evaluator = GaiaLlmAgentEvaluator()
        await evaluator.run_evaluation(max_questions=args.max_questions)
    else:
        evaluator = GaiaEvaluator()
        await evaluator.run_evaluation(max_questions=args.max_questions)

if __name__ == "__main__":
    asyncio.run(main()) 