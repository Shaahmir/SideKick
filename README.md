# SideKick

An autonomous personal AI agent built with LangChain and LangGraph. SideKick takes natural-language instructions, plans and executes tasks using real-world tools, interacts with a web browser, manages files, and verifies whether the requested task has actually been completed. SideKick is designed to **get things done**. It works toward explicitly defined success criteria, evaluates its own results, and retries when the task has not been completed successfully.

## Core Architecture

### SideKick Worker

The worker is the main agent responsible for completing tasks.

It uses LangChain's `create_agent` with the following capabilities:

- Understands natural-language requirements.
- Creates and manages task lists.
- Searches the web for current information.
- Navigates websites using a real browser.
- Reads, creates, and modifies files.
- Installs and uses available tools through its execution environment.
- Requests human assistance when an action requires user intervention.

The worker continues executing the task until it meets the success criteria or genuinely needs additional input.

### Task Evaluator

SideKick uses a separate LLM-based evaluator to verify task completion.

The evaluator receives:

- Original user requirements.
- Defined success criteria.
- The worker's latest response.
- The tools used during execution.

It returns a structured result containing:

- `feedback`: Explanation of the current result.
- `succeeded`: Whether the success criteria have been met.
- `need_assist`: Whether the worker needs clarification or human assistance.

If the task is incomplete, the evaluator provides feedback to the worker, allowing it to correct its approach.
SideKick allows up to **3 evaluation attempts** before returning the final result.

### Tool Integration

SideKick combines custom LangChain tools with external Model Context Protocol (MCP) servers.

**Custom Tools**

| Tool | Responsibility |
|---|---|
| Tavily Search | Search the web for current information |
| Wikipedia Search | Retrieve Wikipedia summaries |
| Pushover Notifications | Send push notifications |
| Human Assistance | Request user intervention |

**MCP Tools**

SideKick dynamically connects to two MCP servers:

**1. Playwright MCP**

Provides browser automation capabilities.

- Navigate websites.
- Read webpage content.
- Interact with browser elements.
- Handle cookie banners and popups.
- Perform browser-based research.

The browser server runs in isolated mode.

**2. Filesystem MCP**

Provides filesystem access restricted to the project's `mnt/` workspace.

- Create files and directories.
- Read existing files.
- Modify generated files.
- Organize task outputs.

The worker can use these tools together to complete tasks involving both web research and file generation.

## Human-in-the-Loop

Not every action should happen without user approval.

SideKick implements human-in-the-loop execution using LangGraph's `HumanInTheLoopMiddleware`.

Actions such as sending notifications and requesting human assistance can interrupt execution and wait for approval.

For example, if a website requires authentication, a CAPTCHA, or two-factor authentication, SideKick can pause and ask the user to complete that step.

Once approved, execution resumes from where it stopped rather than restarting the entire task.

## Execution Safety & Middleware

SideKick uses several middleware components to improve execution reliability:

| Middleware | Purpose |
|---|---|
| `TodoListMiddleware` | Tracks task progress |
| `HumanInTheLoopMiddleware` | Pauses sensitive actions for approval |
| `PIIMiddleware` | Detects and handles sensitive information |
| `ModelCallLimitMiddleware` | Limits worker model calls to 30 per run |
| `TolerateToolError` | Returns tool failures to the agent so it can recover |

LangGraph's `InMemorySaver` maintains execution state and supports resuming interrupted tasks.

Each SideKick instance receives its own unique session identifier.

## Workspace

All task-related files are stored inside the `mnt/` directory.

For example, a flight research task might generate:

```text
mnt/
└── flights.md
```

The generated files depend entirely on the user's requirements. SideKick does not enforce a predefined output structure.
A task can involve research, document generation, data collection, or other file-based operations.

## Project Structure

```text
SideKick/
├── mnt/
│   └── Generated task files
│
├── main.py
├── sidekick.py
├── tools.py
│
├── .env.example
├── .gitignore
├── LICENSE
├── README.md
│
├── pyproject.toml
└── uv.lock
```

## Installation

SideKick uses `uv` for dependency management.

**Prerequisites**

- Python 3.14 or later.
- [uv](https://docs.astral.sh/uv/).
- Node.js and npm (required to run the MCP servers).
- An LLM API key.
- A Tavily API key.
- Pushover credentials if push notifications are required.

Clone the repository:

```bash
git clone https://github.com/Shaahmir/SideKick.git
cd SideKick
```

Install dependencies:

```bash
uv sync
```

Create your environment file:

```bash
cp .env.example .env
```

Configure your environment variables:

```env
MODEL=
OPENAI_API_KEY=
PUSHOVER_USER=
PUSHOVER_TOKEN=
TAVILY_API_KEY=
```

`MODEL` specifies the model used by the worker and evaluator. The current implementation uses LangChain's `ChatOpenAI` interface.

## Running SideKick

Run the application:

```bash
uv run python main.py
```

The application initializes the worker, connects to the available tools, and starts executing the task defined in `main.py`.
Generated files and task artifacts are written to `mnt/`.

## Technologies

- **LangChain** – Agent creation and tool integration.
- **LangGraph** – Workflow orchestration, state management, and execution resumption.
- **Playwright** – Browser automation.
- **Tavily** – Web search.
- **Wikipedia API** – Knowledge retrieval.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
