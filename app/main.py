"""Reqnova - FastAPI backend.

Endpoints
  GET  /                      single-page frontend
  GET  /api/health            config sanity check (no secrets returned)
  GET  /api/samples           example inputs for the UI
  POST /api/extract           upload a file -> plain text (vision model for images/scans)
  POST /api/analyze           run the pipeline; streams progress as Server-Sent Events
  POST /api/export/markdown   result JSON -> Markdown document
  GET  /api/history           list previous analyses (newest first)
  GET  /api/history/{id}      one saved analysis (input + full result)
  DELETE /api/history/{id}    delete one;  DELETE /api/history  clears all
"""
from __future__ import annotations

import json
import logging
import queue
import threading
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, history, parser, pipeline, report

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

app = FastAPI(title="Reqnova · AI for Requirements")
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
if (ROOT / "examples").is_dir():  # optional local demo files (not part of the public repo)
    app.mount("/examples", StaticFiles(directory=ROOT / "examples"), name="examples")


class AnalyzeRequest(BaseModel):
    text: str
    mode: str = config.DEFAULT_MODEL_MODE  # "fast" | "quality"


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(FRONTEND / "assets" / "favicon.ico")


@app.get("/api/health")
def health():
    return {"llm_key_set": bool(config.FAST_MODEL and config.FAST_MODEL_API_KEY),
            "parse_key_set": bool(config.VISION_MODEL and config.VISION_API_KEY),
            "default_mode": config.DEFAULT_MODEL_MODE}


@app.get("/api/samples")
def samples():
    return json.loads((ROOT / "app" / "samples.json").read_text(encoding="utf-8"))


@app.post("/api/extract")
async def extract(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 15 MB).")
    try:
        return parser.extract_text(file.filename or "upload", data)
    except parser.ParseError as e:
        raise HTTPException(422, str(e))


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    """Run the pipeline in a worker thread and stream step events (SSE)."""
    q: queue.Queue = queue.Queue()

    def emit(step, status, data):
        q.put({"type": "step", "step": step, "status": status, "data": data})

    def work():
        try:
            result = pipeline.run(req.text, req.mode, emit)
            try:
                result["history_id"] = history.save(req.text, req.mode, result)
            except Exception:  # noqa: BLE001 - history must never break an analysis
                logging.exception("could not save history")
            q.put({"type": "result", "data": result})
        except ValueError as e:              # bad input -> user-facing message
            q.put({"type": "error", "message": str(e)})
        except Exception as e:  # noqa: BLE001
            logging.exception("pipeline failed")
            q.put({"type": "error", "message": f"Pipeline failed: {e}"})
        finally:
            q.put(None)

    threading.Thread(target=work, daemon=True).start()

    def stream():
        while True:
            try:
                item = q.get(timeout=15)
            except queue.Empty:
                yield ": keep-alive\n\n"     # keeps proxies from closing slow deep-model runs
                continue
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/export/markdown", response_class=PlainTextResponse)
def export_markdown(result: dict):
    return report.to_markdown(result)


@app.get("/api/history")
def history_list(limit: int = 100):
    return history.list_items(limit)


@app.get("/api/history/{hid}")
def history_get(hid: str):
    item = history.get(hid)
    if not item:
        raise HTTPException(404, "Not found")
    return item


@app.delete("/api/history/{hid}")
def history_delete(hid: str):
    if not history.delete(hid):
        raise HTTPException(404, "Not found")
    return {"deleted": hid}


@app.delete("/api/history")
def history_clear():
    return {"deleted": history.clear()}
