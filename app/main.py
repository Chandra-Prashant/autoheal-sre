from fastapi import FastAPI

app = FastAPI(title="autoheal-sre")


@app.get("/health")
def health():
    return {"status": "ok"}
