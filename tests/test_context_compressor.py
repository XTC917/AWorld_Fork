import unittest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tests.base_test import BaseTest

from aworld.config.conf import AgentConfig, ModelConfig, ContextRuleConfig, OptimizationConfig, LlmCompressionConfig
from aworld.core.context.processor import CompressionResult, CompressionType
from aworld.core.context.processor.llm_compressor import LLMCompressor
from aworld.core.context.processor.prompt_processor import PromptProcessor
from aworld.core.context.base import AgentContext, ContextUsage


class TestPromptCompressor(BaseTest):
    """Test cases for PromptCompressor.compress_batch function"""

    def __init__(self):
        """Set up test fixtures"""
        self.mock_model_name = "qwen/qwen3-1.7b"
        self.mock_base_url = "http://localhost:1234/v1"
        self.mock_api_key = "lm-studio"
        self.mock_llm_config = ModelConfig(
            llm_model_name=self.mock_model_name,
            llm_base_url=self.mock_base_url,
            llm_api_key=self.mock_api_key
        )
        os.environ["LLM_API_KEY"] = self.mock_api_key
        os.environ["LLM_BASE_URL"] = self.mock_base_url
        os.environ["LLM_MODEL_NAME"] = self.mock_model_name

    def test_compress_batch_basic(self):
        
        compressor = LLMCompressor(
            llm_config=self.mock_llm_config
        )
        
        # Test data
        contents = [
            "[SYSTEM]You are a helpful assistant.\n[USER]This is the first long text content that needs compression. This is the first long text content that needs compression.",
        ]
        
        # Execute compress_batch
        results = compressor.compress_batch(contents)
        
        # Assertions
        for result in results:
            self.assertIsInstance(result, CompressionResult)
            self.assertEqual(result.compression_type, CompressionType.LLM_BASED)
            self.assertTrue('This is the first long text content that needs compression. This is the first long text content that needs compression.' not in result.compressed_content)

    def test_compress_messages(self):
        """Test compress_messages function from PromptProcessor"""
        
        # Create context rule with compression enabled
        context_rule = ContextRuleConfig(
            optimization_config=OptimizationConfig(
                enabled=True,
                max_token_budget_ratio=0.8
            ),
            llm_compression_config=LlmCompressionConfig(
                enabled=True,
                trigger_compress_token_length=10,  # Low threshold to trigger compression
                compress_model=self.mock_llm_config
            )
        )
        
        # Create agent context
        agent_context = AgentContext(
            agent_id="test_agent",
            agent_name="test_agent",
            agent_desc="Test agent for compression",
            system_prompt="You are a helpful assistant.",
            agent_prompt="You are a helpful assistant.",
            model_config=self.mock_llm_config,
            context_rule=context_rule,
            context_usage=ContextUsage(total_context_length=4096)
        )
        
        # Create prompt processor
        processor = PromptProcessor(agent_context)
        
        # Test messages with repeated content that needs compression
        messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant."
            },
            {
                "role": "user", 
                "content": "This is the first long text content that needs compression. This is the first long text content that needs compression."
            },
            {
                "role": "assistant",
                "content": "I understand you want me to help with compression."
            }
        ]
        
        # Execute compress_messages
        compressed_messages = processor.compress_messages(messages)

        # Assertions
        self.assertIsInstance(compressed_messages, list)
        self.assertEqual(len(compressed_messages), len(messages))
        
        # Find the user message and verify it was processed
        user_message = None
        for msg in compressed_messages:
            if msg.get("role") == "user":
                user_message = msg
                break
        
        self.assertIsNotNone(user_message)
        # The original repeated text should be compressed
        original_content = "This is the first long text content that needs compression. This is the first long text content that needs compression."
        self.assertNotEqual(user_message["content"], original_content)
        # The compressed content should be shorter than original
        self.assertLess(len(user_message["content"]), len(original_content))

if __name__ == '__main__':
    testPromptCompressor = TestPromptCompressor()
    testPromptCompressor.test_compress_batch_basic()
    testPromptCompressor = TestPromptCompressor()
    testPromptCompressor.test_compress_messages()




