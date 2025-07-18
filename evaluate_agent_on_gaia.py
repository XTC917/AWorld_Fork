import asyncio
import json
import os
from datetime import datetime
from typing import List, Dict, Any
from aworld.config.conf import AgentConfig, ClientType, ModelConfig
from aworld.agents.llm_agent import Agent
from aworld.core.common import Observation
from aworld.core.context.base import Context

QWEN3_API_URL = "https://modelfactory.lenovo.com/app-workspace-172-1748942586592-vscode/v1"
QWEN3_MODEL = "/dfs/data/aisz/panhui9/cache_dir/mogao/Qwen3-235B-A22B-FP8"
GAIA_PATH = "Gaia_Database/metadata.jsonl"

class GaiaLlmAgentEvaluator:
    def __init__(self):
        self.results = []
        agent_config = AgentConfig(
            llm_config=ModelConfig(
                llm_provider="openai",
                llm_model_name=QWEN3_MODEL,
                llm_base_url=QWEN3_API_URL,
                llm_client_type=ClientType.HTTP,
                llm_temperature=0.6,
                max_tokens=1000,
                llm_api_key="",
                async_enabled=True,  # 必须在 ModelConfig 里
            ),
            system_prompt="你是一个有用的AI助手。",
            agent_prompt="请用中文简明扼要地回答用户问题。",
        )
        self.agent = Agent(
            conf=agent_config,
            name="qwen3_agent",
            system_prompt="你是一个有用的AI助手。",
            agent_prompt="请用中文简明扼要地回答用户问题。",
        )
        if getattr(self.agent, "agent_context", None) is None:
            self.agent.agent_context = Context()
        self.agent._init_context(self.agent.agent_context)

    def load_dataset(self) -> List[Dict[str, Any]]:
        dataset = []
        if not os.path.exists(GAIA_PATH):
            print(f"❌ 数据集文件不存在: {GAIA_PATH}")
            return dataset
        with open(GAIA_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    dataset.append(json.loads(line))
        print(f"✅ 成功加载 {len(dataset)} 条 GAIA 数据")
        return dataset

    async def call_agent(self, question: str) -> str:
        obs = Observation(content=question)
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self.agent.policy, obs)
            if result and hasattr(result[0], 'policy_info'):
                return str(result[0].policy_info).strip()
            else:
                return str(result)
        except Exception as e:
            return f"[Agent调用失败] {e}"

    def extract_answer(self, response: str) -> str:
        import re
        # 优先提取 <answer>标签
        match = re.search(r'<answer>(.*?)</answer>', response, re.IGNORECASE | re.DOTALL)
        if match:
            ans = match.group(1).strip()
        else:
            # 提取 \boxed{数字}
            match = re.search(r'\\boxed\{(\d+)\}', response)
            if match:
                ans = match.group(1)
            else:
                # 提取 $$数字$$
                match = re.search(r'\$\$?\s*(\d+)\s*\$\$?', response)
                if match:
                    ans = match.group(1)
                else:
                    # 提取第一个纯数字
                    match = re.search(r'\b(\d+)\b', response)
                    if match:
                        ans = match.group(1)
                    else:
                        # 没有数字就取最后一段
                        lines = response.strip().split('\n')
                        for line in reversed(lines):
                            if line.strip() and not line.startswith('#'):
                                ans = line.strip()
                                break
                        else:
                            ans = response.strip()
        return ans

    def score_answer(self, predicted: str, correct: str) -> bool:
        import re
        predicted = predicted.lower().strip()
        correct = correct.lower().strip()
        if predicted == correct:
            return True
        if correct in predicted or predicted in correct:
            return True
        pred_clean = re.sub(r'[^\w]', '', predicted)
        corr_clean = re.sub(r'[^\w]', '', correct)
        if pred_clean == corr_clean:
            return True
        return False

    def detect_function_calling(self, response: str) -> bool:
        # 检测回复中是否有 function/tool call 相关内容
        import re
        # 典型 function call 关键词/格式
        patterns = [
            r'"tool_calls"', r'"function"', r'调用工具', r'function_call', r'arguments', r'\{.*?\}', r'\[.*?\]'
        ]
        for pat in patterns:
            if re.search(pat, response, re.IGNORECASE):
                return True
        return False

    async def evaluate_single_question(self, item: Dict[str, Any]) -> Dict[str, Any]:
        question = item["Question"]
        correct_answer = item["Final answer"]
        task_id = item.get("task_id", "")
        level = item.get("Level", "")
        print(f"\n🔍 评测问题 {task_id} (Level {level}): {question[:80]}...")
        response = await self.call_agent(question)
        predicted_answer = self.extract_answer(response)
        is_correct = self.score_answer(predicted_answer, correct_answer)
        function_called = self.detect_function_calling(response)
        result = {
            "task_id": task_id,
            "level": level,
            "question": question,
            "correct_answer": correct_answer,
            "predicted_answer": predicted_answer,
            "full_response": response,
            "is_correct": is_correct,
            "function_called": function_called
        }
        status = "✅" if is_correct else "❌"
        print(f"{status} 预测: {predicted_answer} | 正确答案: {correct_answer} | FunctionCall: {function_called}")
        return result

    async def run_evaluation(self, max_questions: int = 166):
        print("🚀 开始 GAIA 评测...")
        dataset = self.load_dataset()
        if not dataset:
            return
        if max_questions > 0:
            dataset = dataset[:max_questions]
        print(f"📊 将评测 {len(dataset)} 个问题")
        for i, item in enumerate(dataset, 1):
            try:
                result = await self.evaluate_single_question(item)
                self.results.append(result)
                correct_count = sum(1 for r in self.results if r["is_correct"])
                func_count = sum(1 for r in self.results if r["function_called"])
                accuracy = correct_count / len(self.results) * 100
                print(f"📈 进度: {i}/{len(dataset)} | 准确率: {accuracy:.1f}% ({correct_count}/{len(self.results)}) | FunctionCall: {func_count}")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"❌ 评测问题 {item.get('task_id', 'unknown')} 失败: {e}")
                continue
        self.generate_report()

    def generate_report(self):
        if not self.results:
            print("❌ 没有评测结果")
            return
        total = len(self.results)
        correct = sum(1 for r in self.results if r["is_correct"])
        func_count = sum(1 for r in self.results if r["function_called"])
        accuracy = correct / total * 100 if total > 0 else 0
        func_rate = func_count / total * 100 if total > 0 else 0
        # 按难度统计
        level_stats = {}
        for result in self.results:
            level = result["level"]
            if level not in level_stats:
                level_stats[level] = {"total": 0, "correct": 0, "func": 0}
            level_stats[level]["total"] += 1
            if result["is_correct"]:
                level_stats[level]["correct"] += 1
            if result["function_called"]:
                level_stats[level]["func"] += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"gaia_llm_agent_report_{timestamp}.md"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("# GAIA LLM Agent 评测报告\n\n")
            f.write(f"**评测时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**模型**: Qwen3-235B-A22B-FP8\n\n")
            f.write(f"**API**: {QWEN3_API_URL}\n\n")
            f.write("## 总体结果\n\n")
            f.write(f"- **总题数**: {total}\n")
            f.write(f"- **正确数**: {correct}\n")
            f.write(f"- **准确率**: {accuracy:.2f}%\n")
            f.write(f"- **Function Calling 触发数**: {func_count}\n")
            f.write(f"- **Function Calling 触发率**: {func_rate:.2f}%\n\n")
            f.write("## 按难度统计\n\n")
            for level in sorted(level_stats.keys()):
                stats = level_stats[level]
                level_accuracy = stats["correct"] / stats["total"] * 100 if stats["total"] else 0
                func_acc = stats["func"] / stats["total"] * 100 if stats["total"] else 0
                f.write(f"### Level {level}\n")
                f.write(f"- 题数: {stats['total']}\n")
                f.write(f"- 正确: {stats['correct']}\n")
                f.write(f"- 准确率: {level_accuracy:.2f}%\n")
                f.write(f"- Function Calling 触发率: {func_acc:.2f}%\n\n")
            f.write("## 详细结果\n\n")
            for result in self.results:
                status = "✅" if result["is_correct"] else "❌"
                f.write(f"### {status} {result['task_id']} (Level {result['level']})\n\n")
                f.write(f"**问题**: {result['question']}\n\n")
                f.write(f"**正确答案**: {result['correct_answer']}\n\n")
                f.write(f"**模型答案**: {result['predicted_answer']}\n\n")
                f.write("**完整回复**:\n```\n")
                f.write(f"{result['full_response']}\n")
                f.write("```\n")
                f.write(f"**Function Calling**: {result['function_called']}\n\n")
                f.write("---\n\n")
        print(f"\n📋 评测报告已生成: {report_file}")
        print(f"📊 总体准确率: {accuracy:.2f}% ({correct}/{total}) | Function Calling 触发率: {func_rate:.2f}% ({func_count}/{total})")

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--max_questions', type=int, default=166)
    args = parser.parse_args()
    evaluator = GaiaLlmAgentEvaluator()
    await evaluator.run_evaluation(max_questions=args.max_questions)

if __name__ == "__main__":
    asyncio.run(main()) 