# coding: utf-8
# Copyright (c) 2025 inclusionAI.
import abc
import asyncio
import json
import os
import traceback
from typing import Optional

from aworld.config import ConfigDict
from aworld.core.memory import MemoryBase, MemoryItem, MemoryStore, MemoryConfig
from aworld.logs.util import logger
from aworld.memory.longterm import DefaultMemoryOrchestrator, LongTermConfig
from aworld.memory.models import UserProfileExtractParams, AgentExperienceExtractParams
from aworld.models.llm import get_llm_model, acall_llm_model


class InMemoryMemoryStore(MemoryStore):
    def __init__(self):
        self.memory_items = []

    def add(self, memory_item: MemoryItem):
        self.memory_items.append(memory_item)

    def get(self, memory_id) -> Optional[MemoryItem]:
        return next((item for item in self.memory_items if item.id == memory_id), None)

    def get_first(self, filters: dict = None) -> Optional[MemoryItem]:
        """Get the first memory item."""
        filtered_items = self.get_all(filters)
        if len(filtered_items) == 0:
            return None
        return filtered_items[0]

    def total_rounds(self, filters: dict = None) -> int:
        """Get the total number of rounds."""
        return len(self.get_all(filters))

    def get_all(self, filters: dict = None) -> list[MemoryItem]:
        """Filter memory items based on filters."""
        filtered_items = [item for item in self.memory_items if self._filter_memory_item(item, filters)]
        return filtered_items

    def _filter_memory_item(self, memory_item: MemoryItem, filters: dict = None) -> bool:
        if memory_item.deleted:
            return False
        if filters is None:
            return True
        if filters.get('application_id') is not None:
            if memory_item.application_id is None:
                return False
            if memory_item.application_id != filters['application_id']:
                return False
        if filters.get('user_id') is not None:
            if memory_item.user_id is None:
                return False
            if memory_item.user_id != filters['user_id']:
                return False
        if filters.get('agent_id') is not None:
            if memory_item.agent_id is None:
                return False
            if memory_item.agent_id != filters['agent_id']:
                return False
        if filters.get('task_id') is not None:
            if memory_item.task_id is None:
                return False
            if memory_item.task_id != filters['task_id']:
                return False
        if filters.get('session_id') is not None:
            if memory_item.session_id is None:
                return False
            if memory_item.session_id != filters['session_id']:
                return False
        if filters.get('memory_type') is not None:
            if memory_item.memory_type is None:
                return False
            if memory_item.memory_type != filters['memory_type']:
                return False
        return True

    def get_last_n(self, last_rounds, filters: dict = None) -> list[MemoryItem]:
        return self.get_all(filters=filters)[-last_rounds:]

    def update(self, memory_item: MemoryItem):
        for index, item in enumerate(self.memory_items):
            if item.id == memory_item.id:
                self.memory_items[index] = memory_item
                break

    def delete(self, memory_id):
        exists = self.get(memory_id)
        if exists:
            exists.deleted = True

    def history(self, memory_id) -> list[MemoryItem] | None:
        exists = self.get(memory_id)
        if exists:
            return exists.histories
        return None


class MemoryFactory:

    @classmethod
    def from_config(cls, config: MemoryConfig) -> "MemoryBase":
        """
        Initialize a Memory instance from a configuration dictionary.

        Args:
            config (dict): Configuration dictionary.

        Returns:
            MemoryBase: Memory instance.
        """
        if config.provider == "inmemory":
            logger.info("🧠 [MEMORY]setup memory store: inmemory")
            return InMemoryStorageMemory(
                memory_store=InMemoryMemoryStore(),
                config=config,
                enable_summary=config.enable_summary,
                summary_rounds=config.summary_rounds
            )
        elif config.provider == "mem0":
            from aworld.memory.mem0.mem0_memory import Mem0Memory
            logger.info("🧠 [MEMORY]setup memory store: mem0")
            return Mem0Memory(
                memory_store=InMemoryMemoryStore(),
                config=config
            )
        else:
            raise ValueError(f"Invalid memory store type: {config.get('memory_store')}")


class Memory(MemoryBase):
    __metaclass__ = abc.ABCMeta

    def __init__(self, memory_store: MemoryStore, config: MemoryConfig, **kwargs):
        self.memory_store = memory_store
        self.config = config
        self._llm_instance = None
        self._embedder_model = None

        # Initialize long-term memory components
        if self.config.enable_long_term:
            self.longterm_config = config.long_term_config or LongTermConfig.create_simple_config()
            self.memory_orchestrator = DefaultMemoryOrchestrator(
                self.default_llm_instance,
                self.longterm_config,
                embedding_model=self._embedder_model,
                long_term_memory_store=self.memory_store
            )
            logger.info(f"🧠 [MEMORY:long-term] Initialized with config: "
                        f"threshold={self.longterm_config.trigger.message_count_threshold}, "
                        f"user_profiles={self.longterm_config.extraction.enable_user_profile_extraction}, "
                        f"agent_experiences={self.longterm_config.extraction.enable_agent_experience_extraction}")



    @property
    def default_llm_instance(self):
        def get_env(key: str, default_key: str, default_val: object=None):
            return os.getenv(key) if os.getenv(key) else os.getenv(default_key, default_val)

        if not self._llm_instance:
            self._llm_instance = get_llm_model(conf=ConfigDict({
                "llm_model_name": get_env("MEM_LLM_MODEL_NAME", "LLM_MODEL_NAME"),
                "llm_api_key": get_env("MEM_LLM_API_KEY", "LLM_API_KEY") ,
                "llm_base_url": get_env("MEM_LLM_BASE_URL", 'LLM_BASE_URL'),
                "temperature": get_env("MEM_LLM_TEMPERATURE", "MEM_LLM_TEMPERATURE", 1.0),
                "streaming": 'False'
            }))
        return self._llm_instance


    def _build_history_context(self, messages) -> str:
        """Build the history context string from a list of messages.

        Args:
            messages: List of message objects with 'role', 'content', and optional 'tool_calls'.
        Returns:
            Concatenated context string.
        """
        history_context = ""
        for item in messages:
            history_context += (f"\n\n{item['role']}: {item['content']}, "
                                f"{'tool_calls:' + json.dumps(item['tool_calls']) if 'tool_calls' in item and item['tool_calls'] else ''}")
        return history_context

    async def _call_llm_summary(self, summary_messages: list) -> str:
        """Call LLM to generate summary and log the process.

        Args:
            summary_messages: List of messages to send to LLM.
        Returns:
            Summary content string.
        """
        logger.info(f"🧠 [MEMORY:short-term] [Summary] Creating summary memory, history messages: {summary_messages}")
        llm_response = await acall_llm_model(
            self.default_llm_instance,
            messages=summary_messages,
            stream=False
        )
        logger.info(f'🧠 [MEMORY:short-term] [Summary] summary_content: result is {llm_response.content[:400] + "...truncated"} ')
        return llm_response.content

    def _get_parsed_history_messages(self, history_items: list[MemoryItem]) -> list[dict]:
        """Get and format history messages for summary.

        Args:
            history_items: list[MemoryItem]
        Returns:
            List of parsed message dicts
        """
        parsed_messages = [
            {
                'role': message.metadata['role'],
                'content': message.content,
                'tool_calls': message.metadata.get('tool_calls') if message.metadata.get('tool_calls') else None
            }
            for message in history_items]
        return parsed_messages

    async def async_gen_multi_rounds_summary(self, to_be_summary: list[MemoryItem]) -> str:
        logger.info(
            f"🧠 [MEMORY:short-term] [Summary] Creating summary memory, history messages")
        if len(to_be_summary) == 0:
            return ""
        parsed_messages = self._get_parsed_history_messages(to_be_summary)
        history_context = self._build_history_context(parsed_messages)

        summary_messages = [
            {"role": "user", "content": self.config.summary_prompt.format(context=history_context)}
        ]

        return await self._call_llm_summary(summary_messages)

    async def async_gen_summary(self, filters: dict, last_rounds: int) -> str:
        """A tool for summarizing the conversation history."""

        logger.info(f"🧠 [MEMORY:short-term] [Summary] Creating summary memory, history messages [filters -> {filters}, "
                    f"last_rounds -> {last_rounds}]")
        history_items = self.memory_store.get_last_n(last_rounds, filters=filters)
        if len(history_items) == 0:
            return ""
        parsed_messages = self._get_parsed_history_messages(history_items)
        history_context = self._build_history_context(parsed_messages)

        summary_messages = [
            {"role": "user", "content": self.config.summary_prompt.format(context=history_context)}
        ]

        return await self._call_llm_summary(summary_messages)

    async def async_gen_cur_round_summary(self, to_be_summary: MemoryItem, filters: dict, last_rounds: int) -> str:
        if self.config.enable_summary and len(to_be_summary.content) < self.config.summary_single_context_length:
            return to_be_summary.content

        logger.info(f"🧠 [MEMORY:short-term] [Summary] Creating summary memory, history messages [filters -> {filters}, "
                    f"last_rounds -> {last_rounds}]: to be summary content is {to_be_summary.content}")
        history_items = self.memory_store.get_last_n(last_rounds, filters=filters)
        if len(history_items) == 0:
            return ""
        parsed_messages = self._get_parsed_history_messages(history_items)

        # Append the to_be_summary
        parsed_messages.append({
            "role": to_be_summary.metadata['role'],
            "content": f"{to_be_summary.content}",
            'tool_call_id': to_be_summary.metadata['tool_call_id'],
        })
        history_context = self._build_history_context(parsed_messages)

        summary_messages = [
            {"role": "user", "content": self.config.summary_prompt.format(context=history_context)}
        ]

        return await self._call_llm_summary(summary_messages)

    def search(self, query, limit=100, filters=None) -> Optional[list[MemoryItem]]:
        pass

    def add(self, memory_item: MemoryItem, filters: dict = None):
        self._add(memory_item, filters)
        self.post_add(memory_item, filters)

    @abc.abstractmethod
    def _add(self, memory_item: MemoryItem, filters: dict = None):
        pass

    def post_add(self, memory_item: MemoryItem, filters: dict = None):
        try:
            # TODO: add a background task to process long-term memory
            self.post_process_long_terms(memory_item, filters)
        except Exception as err:
            logger.warning(f"🧠 [MEMORY:long-term] Error during long-term memory processing: {err}, traceback is {traceback.format_exception(err)}")

    def post_process_long_terms(self, memory_item: MemoryItem, filters: dict = None):
        """Post process long-term memory."""

        # check if long-term memory is enabled
        if not self.config.enable_long_term:
            return

        # check if long-term memory config is valid
        long_term_config = self.config.long_term_config
        if not long_term_config:
            return

        # check if memory_item is "message"
        if memory_item.memory_type != 'message':
            return

        # get all memories of current task
        task_memory_items = self.memory_store.get_all({
            'memory_type': 'message',
            'application_id': memory_item.application_id,
            'session_id': memory_item.session_id,
            'task_id': memory_item.task_id
        })

        task_params = []

        # Check if user profile extraction is enabled
        if long_term_config.extraction.enable_user_profile_extraction:
            if memory_item.user_id:
                user_profile_task_params = UserProfileExtractParams(
                    user_id=memory_item.user_id,
                    session_id=memory_item.session_id,
                    task_id=memory_item.task_id,
                    application_id=memory_item.application_id,
                    memories=task_memory_items
                )
                task_params.append(user_profile_task_params)
            else:
                logger.warning(f"🧠 [MEMORY:long-term] memory_item.user_id is None, skip user profile extraction")

        # Check if agent experience extraction is enabled
        if long_term_config.extraction.enable_agent_experience_extraction:
            if memory_item.agent_id:
                agent_experience_task_params = AgentExperienceExtractParams(
                    agent_id=memory_item.agent_id,
                    session_id=memory_item.session_id,
                    task_id=memory_item.task_id,
                    application_id=memory_item.application_id,
                    memories=task_memory_items
                )
                task_params.append(agent_experience_task_params)
            else:
                logger.warning(
                    f"🧠 [MEMORY:long-term] memory_item.agent_id is None, skip agent experience extraction")

        self.memory_orchestrator.create_longterm_processing_tasks(task_params)

    def delete(self, memory_id):
        pass

    def update(self, memory_item: MemoryItem):
        pass


class InMemoryStorageMemory(Memory):
    def __init__(self, memory_store: MemoryStore, config: MemoryConfig, enable_summary: bool = True, **kwargs):
        super().__init__(memory_store=memory_store, config=config, longterm_config=config.long_term_config)
        self.summary = {}
        self.summary_rounds = self.config.summary_rounds
        self.enable_summary = self.config.enable_summary

    def _add(self, memory_item: MemoryItem, filters: dict = None):
        self.memory_store.add(memory_item)

        # Check if we need to create or update summary
        if self.enable_summary:
            total_rounds = len(self.memory_store.get_all())
            if total_rounds > self.summary_rounds:
                self._create_or_update_summary(total_rounds)


    def _create_or_update_summary(self, total_rounds: int):
        """Create or update summary based on current total rounds.

        Args:
            total_rounds (int): Total number of rounds.
        """
        summary_index = int(total_rounds / self.summary_rounds)
        start = (summary_index - 1) * self.summary_rounds
        end = total_rounds - self.summary_rounds

        # Ensure we have valid start and end indices
        start = max(0, start)
        end = max(start, end)

        # Get the memory items to summarize
        items_to_summarize = self.memory_store.get_all()[start:end + 1]
        print(f"{total_rounds}start: {start}, end: {end},")

        # Create summary content
        summary_content = self._summarize_items(items_to_summarize, summary_index)

        # Create the range key
        range_key = f"{start}_{end}"

        # Check if summary for this range already exists
        if range_key in self.summary:
            # Update existing summary
            self.summary[range_key].content = summary_content
            self.summary[range_key].updated_at = None  # This will update the timestamp
        else:
            # Create new summary
            summary_item = MemoryItem(
                content=summary_content,
                metadata={
                    "summary_index": summary_index,
                    "start_round": start,
                    "end_round": end,
                    "role": "system"
                },
                tags=["summary"]
            )
            self.summary[range_key] = summary_item

    def _summarize_items(self, items: list[MemoryItem], summary_index: int) -> str:
        """Summarize a list of memory items.

        Args:
            items (list[MemoryItem]): List of memory items to summarize.
            summary_index (int): Summary index.

        Returns:
            str: Summary content.
        """
        # This is a placeholder. In a real implementation, you might use an LLM or other method
        # to create a meaningful summary of the content
        return asyncio.run(self.async_gen_multi_rounds_summary(items))

    def update(self, memory_item: MemoryItem):
        self.memory_store.update(memory_item)

    def delete(self, memory_id):
        self.memory_store.delete(memory_id)

    def get(self, memory_id) -> Optional[MemoryItem]:
        return self.memory_store.get(memory_id)

    def get_all(self, filters: dict = None) -> list[MemoryItem]:
        return self.memory_store.get_all()

    def get_last_n(self, last_rounds, add_first_message=True, filters: dict = None) -> list[MemoryItem]:
        """Get last n memories.

        Args:
            last_rounds (int): Number of memories to retrieve.
            add_first_message (bool):

        Returns:
            list[MemoryItem]: List of latest memories.
        """
        memory_items = self.memory_store.get_last_n(last_rounds, filters=filters)
        while len(memory_items) > 0 and memory_items[0].metadata and "tool_call_id" in memory_items[0].metadata and \
                memory_items[0].metadata["tool_call_id"]:
            last_rounds = last_rounds + 1
            memory_items = self.memory_store.get_last_n(last_rounds, filters=filters)

        # If summary is disabled or no summaries exist, return just the last_n_items
        if not self.enable_summary or not self.summary:
            return memory_items

        # Calculate the range for relevant summaries
        all_items = self.memory_store.get_all(filters=filters)
        total_items = len(all_items)
        end_index = total_items - last_rounds

        # Get complete summaries
        result = []
        complete_summary_count = end_index // self.summary_rounds

        # Get complete summaries
        for i in range(complete_summary_count):
            range_key = f"{i * self.summary_rounds}_{(i + 1) * self.summary_rounds - 1}"
            if range_key in self.summary:
                result.append(self.summary[range_key])

        # Get the last incomplete summary if exists
        remaining_items = end_index % self.summary_rounds
        if remaining_items > 0:
            start = complete_summary_count * self.summary_rounds
            range_key = f"{start}_{end_index - 1}"
            if range_key in self.summary:
                result.append(self.summary[range_key])

        # Add the last n items
        result.extend(memory_items)

        # Add first user input
        if add_first_message and last_rounds < self.memory_store.total_rounds():
            memory_items.insert(0, self.memory_store.get_first(filters=filters))

        if filters["memory_type"] == "message" and "agent_id" in filters:
            agent_memory_items = self.memory_store.get_all(filters={
                "memory_type": "init",
                "agent_id": filters["agent_id"],
                "application_id": filters["application_id"] if "application_id" in filters else "default",
            })
            if len(agent_memory_items) > 0:
                memory_items.insert(0, agent_memory_items[0])

        return result
