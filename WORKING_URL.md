# Where Yatra AI runs

## Live URL

**https://yatra-ai---a-multi-agent-travel-planner-with-langgraph.streamlit.app/**

This is the Streamlit app, deployed by hand on Streamlit Community Cloud with `streamlit_app.py` as
the main file. It was last checked on **4 October 2026**. The check was a page load only: no plan
was submitted. What the page showed:

- The app loaded and the sidebar listed the models in order: `deepseek:deepseek-flash`, then
  `openai:gpt-4.1-mini` as the fallback.
- The sidebar said "Keys: DeepSeek set, OpenAI set".
- Tools: flights ready, weather ready, hotels skipped (no `TAVILY_API_KEY` in the Cloud secrets).
- The page said that plans live in memory only.

What this check does **not** show: a real plan run end to end on the live URL, how the app behaves
with real provider responses, hotel search on Cloud, memory headroom, start-up time after the app
sleeps, uptime over time, or cost and latency. None of these has been measured. Streamlit
Community Cloud may put an idle app to sleep, so the first visit after a quiet period can be slow.

An earlier version of this file said the project was "fully operational" and "production-ready".
That was not supported by evidence, and it has been removed. The old text is not kept.

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

The Streamlit app is the only deployment that exists. It was set up by hand in the Streamlit
Community Cloud dashboard, not by a CI job. The steps, the secrets to paste and the limits are in
[DEPLOYMENT.md](DEPLOYMENT.md), section 13. An earlier attempt to run the API on Render (section 5
of the same file) did not come up and was never diagnosed, so the FastAPI + PostgreSQL stack is
built and tested in CI but is not deployed anywhere. Whenever the live URL is checked again, the
date and what was observed go in this file.

## Where to read more

- [README.md](README.md): what the project is and what it does not do.
- [specs/](specs/): one specification per part, each with its known gaps.
- [docs/history/](docs/history/): old build-night reports, not maintained.
