# fastapi_server.py: A simple FastAPI server for health checks and future webhooks. Currently just has a root endpoint that returns {"status": "ok"}.
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok"}