# Where Yatra AI runs

**There is no public URL yet.** The application has not been deployed. An earlier version of this
file said the project was "fully operational" and "production-ready". That was not supported by
evidence, and it has been removed. The old text is not kept.

## Run it locally

The quickest way is the Streamlit app. It needs no database and no Docker:

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then paste your keys into it
streamlit run streamlit_app.py                                # http://localhost:8501
```

The Next.js front end and the API run with Docker:

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

The current target is Streamlit Community Cloud, with `streamlit_app.py` as the main file. The
steps, the secrets to paste and the limits are in [DEPLOYMENT.md](DEPLOYMENT.md), section 13. An
earlier attempt to run the API on Render (section 5 of the same file) did not come up and was not
resolved. When a deployment exists, its URL goes in this file, with the date it was last checked.

## Where to read more

- [README.md](README.md): what the project is and what it does not do.
- [specs/](specs/): one specification per part, each with its known gaps.
- [docs/history/](docs/history/): old build-night reports, not maintained.
