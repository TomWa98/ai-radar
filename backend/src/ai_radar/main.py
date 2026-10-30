"""FastAPI application entry point."""

from fastapi import FastAPI

app = FastAPI(title="AI Radar")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check: confirms the API process is running."""
    return {"status": "ok"}
