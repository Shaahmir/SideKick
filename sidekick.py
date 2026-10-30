import os
import uuid 
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from langchain_core import messages
from langchain_core.messages.tool import tool_call
from langgraph.checkpoint import memory
from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    PIIMiddleware,
    TodoListMiddleware
)
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from tools import get_tools, human_assist, notify

load_dotenv(override = True)
MODEL = os.getenv("MODEL")

SANDBOX_DIR = Path(__file__).parent / "mnt"
SANDBOX_DIR.mkdir(parents = True, exist_ok = True)
MAX_ATTEMPTS = 3

def text_of(message):

    content = message.content

    if isinstance(content, str):
        return content

    return "".join(
        text.get("text", "") for text in content if isinstance(text, dict) and text.get("type") in ("text", "output_text")
    )

class EvaluateOuput(BaseModel):    
    feedback: str = Field(description = "Feedback on the assistant's response")
    succeeded: bool = Field(description = "Whether the success criteria have been met")
    need_assist: bool = Field(description = "True if the assistant has a question, needs clarification, or is stuck and needs the user")

SIDEKICK_PROMPT = """
You are Sidekick, a capable personal assistant who completes tasks for the user.
You have a real web browser, a sandbox filesystem, web search, Wikipedia, and the ability to send push notifications.
When you use the browser, navigate to a page and read it with a snapshot rather than clicking around unnecessarily.
Dismiss cookie banners and popups yourself by clicking in the browser. If you reach something only a human can do,
like logging in, a captcha, or two-factor authentication, use the request_human_help tool to tell the user exactly
what to do in your browser window, then carry on once they have done it.
For flight searches, use Google Flights in your browser: go straight to https://www.google.com/travel/flights?q=...
with a natural language query like "flights from New York to London leaving 14 July returning 21 July".
Keep working on the task until the success criteria are met, or until you genuinely need to ask the user a question.
If you have a question, ask it plainly. When you are finished, give your final answer clearly,
saying what you did, what you produced, and what you found.
"""

class TolerateToolError(AgentMiddleware):
    """Hand tool failures back to the model as a message so it can recover, rather than
    crashing the run. Tools that touch the outside world, like a browser, fail now and then."""

    async def awrap_tool_call(self, request, handler):
        try:
            return await handler(request)
        except Exception as e:
            return ToolMessage(
                content = f"That tool call failed: {e}, Try another approach",
                tool_call_id = request.tool_call["id"]
            )

class SideKick:

    def __init__(self):
        self.sidekick_id = str(uuid.uuid4())
        self.memory = InMemorySaver()
        self.tools = None
        self.session = None
        self.worker = None
        self.evaluator = None
        self.task = ""
        self.success_criteria = ""
        self.attempts = 0
        self.paused = False
        self.pending_actions = 0
        self.todos = []

    async def setup(self):
        self.tools, self.session = await get_tools(SANDBOX_DIR)

        self.worker = create_agent(
            model = MODEL,
            tools = self.tools,
            system_prompt = f"{SIDEKICK_PROMPT}\nToday is {datetime.now():%A %d %B %Y}.",
            middleware = [
                TolerateToolError(),
                TodoListMiddleware(),
                PIIMiddleware("email"),
                PIIMiddleware("credit_card", apply_to_tool_results = True),
                ModelCallLimitMiddleware(run_limit = 30),
                HumanInTheLoopMiddleware(interrupt_on = {"notify": True, "human_assist": True})
            ],
            checkpointer = self.memory
        )

        self.evaluator = ChatOpenAI(
            model = MODEL
        ).with_structured_output(EvaluateOuput)

    async def evaluate(self, message: str, success_criteria: str, last_message: str, tools_used: list[str]) -> EvaluateOuput:
            
        EVALUATOR_PROMPT = f"""
        You decide whether an assistant has met the success criteria for a task.

        The user's request was:
        {message}

        The success criteria are:
        {success_criteria}

        The tools the assistant called while working, in order:
        {", ".join(tools_used) or "none"}

        The assistant's most recent reply was:
        {last_message}

        Decide whether the success criteria are met, using the tool calls as evidence of what was actually done.
        Also decide whether the assistant needs more input from the user, either because it asked a question,
        needs clarification, or seems stuck. Give brief, concrete feedback.
        """

        return await self.evaluator.ainvoke(EVALUATOR_PROMPT)

    async def run_turn(self, message: str, success_criteria: str, history: list) -> list:
        """One turn of conversation: the worker attempts the task and the evaluator checks it,
        retrying with feedback up to MAX_ATTEMPTS. If the worker pauses for approval, this
        returns straight away with paused set, and resume() continues the same turn."""

        self.task = message 
        self.success_criteria = success_criteria or "The answer should be clear, complete and correct."
        self.attempts = 0
        self.todos = []
        payload = {
            "messages": [
                {"role": "user", "content": f"{message}\n\nThe success criteria for this task are: {self.success_criteria}"}
            ]
        }

        return await self._advance(
            payload,
            history = [{"role": "user", "content": message}]
        )

    async def resume(self, history: list) -> list:
        """Approve the actions the worker paused on, and continue the turn."""

        payload = Command(
            resume = {
                "decisions": [{"type": "approve"}] * self.pending_actions
            }
        )

        return await self._advance(
            payload,
            history
        )

    async def _advance(self, payload, history: list) -> list:

        config = {
            "configurable": {
                "thread_id": self.sidekick_id
            }
        }

        while True:

            result = None

            async for result in self.worker.astream(
                payload,
                config = config,
                stream_mode = "values"
            ):

                if "__interrupt__" in result:
                    actions = result["__interrupt__"][0].value["action_requests"]
                    self.paused = True
                    self.pending_actions = len(actions)
                    described = "\n".join(action["description"] for action in actions)
                    return history + [{"role": "assistant", "content": f"Waiting for your approval:\n{described}"}]

            self.paused = False
            self.todos = result.get("todos", [])
            reply = text_of(result["messages"][-1])
            tools_used = [call["name"] for message in result["messages"] for call in (getattr(message, "tool_calls", None) or [])]
            self.attempts += 1

            verdict = await self.evaluate(self.task, self.success_criteria, reply, tools_used)

            if verdict.succeeded or verdict.need_assist or self.attempts >= MAX_ATTEMPTS:
                return history + [
                    {"role": "assistant", "content": reply},
                    {"role": "assistant", "content": f"Evaluator: {verdict.feedback}"}
                ]

            payload = {
                "messages": [
                    {"role": "user", "content": f"Your last response did not meet the success criteria. Here is the feedback: {verdict.feedback}. Please keep working and address it."}
                ]
            }

    async def cleanup(self):
        """Shut down the MCP servers; the browser window closes."""
        if self.session:
            self.session.stop()
