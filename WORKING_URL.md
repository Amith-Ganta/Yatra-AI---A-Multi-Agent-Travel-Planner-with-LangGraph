# Where Yatra AI runs

**There is no public URL yet.** The application has not been deployed. An earlier version of this
file said the project was "fully operational" and "production-ready". That was not supported by
evidence, and it has been removed. The old text is not kept.

## Run it locally

```bash
cp .env.example .env        # then set DEEPSEEK_API_KEY and, optionally, TAVILY_API_KEY
docker compose up --build
```

| What | URL |
|---|---|
| Frontend | http://localhost:3000 (run `npm run dev` in `frontend/`, see `specs/10-frontend.spec.md`) |
| API | http://localhost:8000 |
| Liveness | http://localhost:8000/health |
| Readiness (database check, MCP status) | http://localhost:8000/ready |

The compose file starts the API and PostgreSQL. It does not start the frontend. The Docker image
has not been built on the author's machine, so a first build may need a fix.

## Deploy it

The target is Render. The steps, the environment variables and the known limits of the free tier
are in [DEPLOYMENT.md](DEPLOYMENT.md). When a deployment exists, its URL goes in this file, with
the date it was last checked.

## Where to read more

- [README.md](README.md): what the project is and what it does not do.
- [specs/](specs/): one specification per part, each with its known gaps.
- [docs/history/](docs/history/): old build-night reports, not maintained.
