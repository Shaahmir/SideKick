import os
import asyncio
import requests
import wikipedia
import warnings

from bs4 import GuessedAtParserWarning
from dotenv import load_dotenv
from contextlib import AsyncExitStack

from langchain_tavily import TavilySearch
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

load_dotenv(override = True)
wikipedia.set_user_agent("SideKickAPP (context@example.com)")
warnings.filterwarnings("ignore", category = GuessedAtParserWarning)

pushover_user = os.getenv("PUSHOVER_USER")
pushover_token = os.getenv("PUSHOVER_TOKEN")
pushover_url = "https://api.pushover.net/1/messages.json"

web_search = TavilySearch(max_results = 5)

@tool
def wikipedia_search(query: str, top_k: int = 1, max_chars: int = 1500) -> str:
    """Search Wikipedia and return summaries of the top results"""
    try:
        results = wikipedia.search(query, results = top_k)

        if not results:
            return f"No results found for {query}"
        
        summaries = []
        for title in results:
            try:
                page  = wikipedia.page(title, auto_suggest = False)
                content = page.summary[:max_chars]
                summaries.append(f"**{page.title}**\n{content}")
            except Exception as e:
                continue

        return "\n\n".join(summaries) if summaries else "No usable pages found!"

    except Exception as e:
        return f"Wikipedia Error: {str(e)}"

@tool
def notify(message: str) -> str:
    """ Send a message to the user as a notification"""

    print(f"Sending: {message}")
    
    payload = {
        "user": pushover_user,
        "token": pushover_token,
        "message": message
    }

    result = requests.post(
        pushover_url,
        data = payload
    )

    print(f"Notification sent via API, Status Code: {result}")

@tool
def human_assist(instructions: str) -> str:
    """Ask the user to do something in the browser window that you cannot do yourself,
    such as logging in to a site, passing a captcha, or approving two-factor authentication.
    Explain exactly what you need them to do. The run pauses until they have done it."""
    
    print(f"\n ACTION NEEDED: {instructions}")

    res = input("Press Enter on done or type 'Failed'...")

    if res.lower() == 'failed':
        return "The user couldn't complete, Do not retry report this."

    return "The user says it is done, Continue with the task."

class MCPSession:

    def __init__(self, SANDBOX_DIR):
        self.tools = []
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._task = None
        self.sandbox_dir = SANDBOX_DIR

    async def _run(self):

        connection = {
            "playwright": {
                "transport": "stdio",
                "command": "npx",
                "args": ["@playwright/mcp@latest", "--isolated"]
            },
            
            "filesystem": {
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", str(self.sandbox_dir)]
            }
        }

        client = MultiServerMCPClient(connection)

        async with AsyncExitStack() as stack:

            for name in connection:
                session = await stack.enter_async_context(client.session(name))
                self.tools += await load_mcp_tools(session, server_name = name)
        
            self._ready.set()
            await self._stop.wait()

    async def start(self) -> list:

        self._task = asyncio.create_task(self._run())
        ready = asyncio.create_task(self._ready.wait())
        await asyncio.wait([ready, self._task], return_when = asyncio.FIRST_COMPLETED)
        ready.cancel()

        if self._task.done():
            self._task.result()

        return self.tools

    async def stop(self) -> None:

        self._stop.set()

        if self._task:
            await self._task

async def get_tools(SANDBOX_DIR: str):

    sessions = MCPSession(SANDBOX_DIR)
    tools = [web_search, notify, wikipedia_search, human_assist]
    mcp_tools = await sessions.start()

    return tools + mcp_tools, sessions
