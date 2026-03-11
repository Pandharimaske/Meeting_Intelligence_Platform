# Backend package — do NOT import routes here.
# Importing routes.py at package level causes the full FastAPI app (including
# _load_jobs_from_disk, ThreadPoolExecutor, etc.) to initialise on every
# `from backend.core.settings import settings` call, which is wasteful and
# causes ordering problems during uvicorn --reload.
#
# The app is referenced by the string "backend.routes:app" in run_server.py,
# which is the correct way to let uvicorn import it on demand.
