"""Comprehensive local smoke test for the My-Agent stack.

This script avoids external services and verifies:
- SQLite database operations
- Tool registration and execution
- Agent loop behavior for a one-tool task

Run it with:
    python smoke_test.py
"""

import asyncio
import gc
import tempfile
import unittest
from pathlib import Path

from agent_core import AgentCore, AgentStatus
from database import Database
from tools import TOOL_REGISTRY, Tool, tool


SMOKE_STATE = {"tool_calls": 0}


@tool(name="smoke_echo", category="test")
async def smoke_echo(text: str) -> str:
    """Echo back text for smoke testing."""
    SMOKE_STATE["tool_calls"] += 1
    await asyncio.sleep(0)
    return f"echo:{text}"


class FakeLLM:
    """Minimal LLM stub that returns one tool call, then a final summary."""

    def __init__(self):
        self.system_prompt = ""
        self.chat_calls = []
        self.provider = "fake"  # needed by agent_core for VLM injection check

    def set_system_prompt(self, prompt: str):
        self.system_prompt = prompt

    def clear_history(self):
        self.chat_calls.clear()

    async def chat(self, message: str, tools=None, images=None):
        self.chat_calls.append({"message": message, "tools": tools})

        if len(self.chat_calls) == 1:
            return {
                "content": "Tool: smoke_echo(text=\"hello\")",
                "tool_calls": [
                    {
                        "function": {
                            "name": "smoke_echo",
                            "arguments": {"text": "hello"},
                        }
                    }
                ],
                "raw": {"message": {"content": "Tool: smoke_echo(text=\"hello\")"}},
            }

        return {
            "content": "已完成：我调用了 smoke_echo，并收到了 echo:hello。",
            "tool_calls": [],
            "raw": {"message": {"content": "已完成"}},
        }


class SmokeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        SMOKE_STATE["tool_calls"] = 0
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "smoke_agent.db"
        self.db = Database(str(self.db_path))

    def tearDown(self):
        del self.db
        gc.collect()
        self.temp_dir.cleanup()

    def test_database_round_trip(self):
        task_id = self.db.create_task(
            name="Smoke Task",
            description="A task created by the smoke test",
            workflow=[{"tool": "smoke_echo", "params": {"text": "hi"}}],
            cron="0 8 * * *",
            is_trusted=True,
        )

        task = self.db.get_task(task_id)
        self.assertIsNotNone(task)
        self.assertEqual(task["name"], "Smoke Task")
        self.assertTrue(task["is_trusted"])

        log_id = self.db.add_log("INFO", "Smoke log entry", task_id=task_id, details="ok")
        self.assertGreater(log_id, 0)

        execution_id = self.db.record_tool_execution(
            tool_name="smoke_echo",
            parameters={"text": "hi"},
            result="echo:hi",
            status="success",
            task_id=task_id,
            confirmed_by_user=True,
        )
        self.assertGreater(execution_id, 0)

        logs = self.db.get_logs(limit=10, task_id=task_id)
        self.assertGreaterEqual(len(logs), 1)

        executions = self.db.get_tool_executions(limit=10)
        self.assertGreaterEqual(len(executions), 1)

    def test_tool_registration_and_execution(self):
        self.assertIn("smoke_echo", TOOL_REGISTRY)
        schema = Tool.get_tool_schema("smoke_echo")
        self.assertIsNotNone(schema)

        result = Tool.execute_tool("smoke_echo", text="world")
        self.assertEqual(result, "echo:world")
        self.assertEqual(SMOKE_STATE["tool_calls"], 1)

    async def test_agent_single_tool_turn(self):
        fake_llm = FakeLLM()
        agent = AgentCore(
            llm=fake_llm,
            db=self.db,
            security_mode="safe",
            max_iterations=3,
        )

        async def approve_confirmation(tool_name: str, parameters: dict) -> bool:
            return True

        agent.on_confirmation_request = approve_confirmation

        response = await agent.process_message("open google", task_id=1)

        self.assertEqual(agent.status, AgentStatus.IDLE)
        self.assertEqual(len(fake_llm.chat_calls), 2)
        self.assertEqual(SMOKE_STATE["tool_calls"], 1)
        self.assertIn("已完成", response)

        tool_executions = self.db.get_tool_executions(limit=10)
        self.assertEqual(len(tool_executions), 1)
        self.assertEqual(tool_executions[0]["tool_name"], "smoke_echo")


if __name__ == "__main__":
    unittest.main(verbosity=2)