# TaskFlow AI

TaskFlow AI is a local, AI-powered task management application. It combines a task manager with a conversational assistant that uses **LangGraph** to interpret requests and interact with task-management tools.

The project is designed as a single-user application and as a practical implementation of LLM tool calling, workflow orchestration, state management, persistence, and human approval.

## Features

- **Task management:** Create, view, update, and manage tasks through the application.
- **Conversational assistant:** Interact with tasks using natural-language requests.
- **Tool calling:** The assistant uses application tools to perform supported task operations.
- **LangGraph workflow:** A graph-based workflow manages the assistant's execution and control flow.
- **Human approval:** Deletion actions use an approval step rather than being executed without confirmation.
- **Conversation persistence:** LangGraph checkpointing preserves conversation state across interactions.
- **Persistent storage:** SQLite stores application data.
- **Containerized deployment:** Docker Compose runs the frontend and backend as separate services.

## Technology Stack

| Area | Technology |
|---|---|
| Frontend | React, Vite, TypeScript |
| Styling and UI | Tailwind CSS, Lucide React |
| Backend API | Python, FastAPI, Pydantic |
| AI orchestration | LangGraph, LangChain |
| Local language model | Ollama with Gemma 4 E4B |
| Database | SQLite, SQLAlchemy (async), aiosqlite |
| Database migrations | Alembic |
| Python dependency management | uv |
| Frontend web server | Nginx |
| Containerization | Docker, Docker Compose |
| Testing and linting | pytest, Ruff, frontend test tooling |

## Architecture

The application is composed of two Docker services:

```text
Browser
   |
   | http://localhost:3000
   v
Frontend container
React build served by Nginx
   |
   | /api/* reverse proxy
   v
Backend container
FastAPI
   |
   +---- LangGraph workflow
   |        |
   |        +---- Ollama (Gemma 4 E4B)
   |        |
   |        +---- Task-management tools
   |        |
   |        +---- Approval handling
   |        |
   |        +---- SQLite checkpointer
   |
   +---- SQLite application database
```

Ollama runs on the host machine rather than inside Docker Compose. The backend container connects to it through `host.docker.internal`.

The application database is stored in the project's `data/` directory and mounted into the backend container so that its data persists when containers are recreated.

## Prerequisites

Install the following before starting the application:

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with Docker Compose.
- [Ollama](https://ollama.com/) installed and running on the host machine.
- The Gemma model used by the project available in Ollama.

Pull the model if it is not already installed:

```bash
ollama pull gemma4:e4b
```

Make sure Ollama is running and the model is available:

```bash
ollama list
```

## Run with Docker Compose

1. Clone the repository:

   ```bash
   git clone <YOUR_GITHUB_REPOSITORY_URL>
   cd TaskFlow-AI
   ```

2. Ensure Docker Desktop and Ollama are running.

3. (Optional) Create a `.env` file in the project root to override the default Ollama model:

   ```env
   OLLAMA_MODEL=gemma4:e4b
   ```

4. Build and start the application:

   ```bash
   docker compose up --build -d
   ```

5. Open the application:

   **http://localhost:3000**

Docker Compose builds the frontend and backend images. The backend runs the database migrations during startup, and the frontend starts after the backend passes its health check.

Useful Docker commands:

```bash
# View running services
docker compose ps

# Follow logs
docker compose logs -f

# Follow logs for one service
docker compose logs -f backend
docker compose logs -f frontend

# Stop the application
docker compose down
```

The SQLite data directory is bind-mounted from `./data`. Do not delete that directory if you need to preserve application data.

## Project Structure

```text
TaskFlow-AI/
├── backend/
│   ├── app/
│   │   ├── api/          # API routes and endpoints
│   │   ├── core/         # Application configuration and core setup
│   │   ├── database/     # Database setup and session handling
│   │   ├── models/       # Database models
│   │   ├── schemas/      # API schemas
│   │   ├── services/     # Application business logic
│   │   └── tools/        # Tools exposed to the AI workflow
│   ├── migrations/       # Alembic database migrations
│   ├── tests/            # Backend tests
│   └── Dockerfile
├── frontend/
│   ├── src/              # React application source
│   ├── Dockerfile
│   └── nginx.conf
├── data/                 # Persistent local application data
├── docs/                 # Project and implementation documentation
├── compose.yaml
├── pyproject.toml
├── uv.lock
└── README.md
```

## Development

The project uses `uv` and the committed `uv.lock` file to manage and reproduce Python dependencies. A `requirements.txt` file is not used.

### Backend

From the repository root:

```bash
uv sync
cd backend
uv run uvicorn app.main:app --reload
```

The API health endpoint is:

```text
http://localhost:8000/api/v1/health
```

Run backend tests and lint checks from the `backend/` directory:

```bash
uv run pytest
uv run ruff check app tests
```

### Frontend

In a separate terminal:

```bash
cd frontend
npm ci
npm run dev
```

Available frontend scripts are defined in `frontend/package.json`. The Vite development server proxies API requests to the local backend.

## Configuration

The backend reads its configuration from environment variables and the root `.env` file. The Docker Compose configuration supplies the container-specific database URL and Ollama connection.

| Variable | Purpose | Docker default |
|---|---|---|
| `OLLAMA_BASE_URL` | Ollama server address | `http://host.docker.internal:11434` |
| `OLLAMA_MODEL` | Model used by the assistant | `gemma4:e4b` |
| `OLLAMA_TEMPERATURE` | Model temperature | `0.0` |
| `DATABASE_URL` | SQLAlchemy database connection | `sqlite+aiosqlite:////app/data/taskflow.db` |
| `API_V1_PREFIX` | API route prefix | `/api/v1` |

Do not commit real `.env` files, credentials, or local database files to source control.

## Design Scope

- TaskFlow AI is currently designed for **single-user local use**.
- Authentication and multi-user account management are not included.
- The language model is expected to be served locally by Ollama.
- The Docker Compose setup is intended for local development and demonstration, not an internet-facing production deployment.

Do not expose this application publicly without first adding appropriate authentication, authorization, and deployment security controls.

## License

No license has been specified yet. Unless a license is added to this repository, the project should be treated as **all rights reserved**.
