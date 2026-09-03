"""
T2P API Server (V6.0 — Structural Refactor)
- Uses AppCore singleton for shared dependencies
- Uses GradingService for business logic (extracted from HTTP layer)
- Async endpoints for non-blocking AI calls
- Slim controllers: validate → delegate → respond
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from typing import List, Optional, Literal
import uvicorn
import json
import time
import uuid
import logging
from pathlib import Path

from src.core import AppCore
from src.services.grading import GradingService
from src.user_session import UserSession
from src.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api_server")

app = FastAPI(
    title="T2P AI Mentor API",
    version="1.0.0",
    description="Adaptive calculus problem generation, grading, and learning analytics.",
)


# ---------- Middleware ----------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every request with method, path, and duration."""
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({duration:.3f}s)")
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared instances
core = AppCore.get()
grading_service = GradingService()


# ---------- Request/Response Models ----------
class GenerateRequest(BaseModel):
    topics: List[str] = Field(default_factory=list, max_length=20)
    num: int = Field(default=1, ge=1, le=10)
    mode: Literal["drill", "exam"] = "drill"
    difficulty: int = Field(default=3, ge=1, le=5)
    question_type: Literal["calculation", "mcq", "fill_in"] = "calculation"
    user_id: Optional[str] = Field(default=None, min_length=1, max_length=128)


class AuditRequest(BaseModel):
    problem_id: str = Field(min_length=1, max_length=128)
    student_work_image: str = Field(min_length=1, max_length=12_000_000)
    is_exam_mode: bool = False


class LoginRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)


class RecordRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    topic: str = Field(min_length=1, max_length=256)
    logic_alignment_score: float = Field(default=0, ge=0, le=100)
    is_correct: bool = False


# ---------- Health ----------
@app.get("/")
def read_root():
    return {
        "status": "T2P Backend is Running (V6.0)",
        "model": core.config.DEEPSEEK_MODEL,
        "total_problems": len(core.data_loader.problems)
    }


@app.get("/health")
async def health_check(check_provider: bool = False):
    """Return local readiness; optionally make a live provider request."""
    status = {
        "api": "healthy",
        "model": core.config.DEEPSEEK_MODEL,
        "deepseek": "configured" if core.ai_client.configured else "not_configured",
        "dataset": f"{len(core.data_loader.problems)} problems / {len(core.data_loader.topics_map)} topics"
    }
    if check_provider and core.ai_client.configured:
        try:
            test_response = await core.ai_client.generate_async(
                prompt="Reply with only the word 'OK'. No other text.",
                temperature=0.0,
            )
            status["deepseek"] = "reachable" if test_response and "OK" in test_response else "unexpected_response"
        except Exception as exc:
            logger.warning("Provider health check failed: %s", exc)
            status["deepseek"] = "unreachable"
    return status


@app.get("/topics")
async def get_all_topics():
    try:
        topics = core.data_loader.get_main_topics()
        return {"success": True, "topics": topics}
    except Exception as e:
        logger.error(f"Failed to fetch topics: {e}")
        fallback = [
            "Limits and Continuity", "Derivatives", "Applications of Derivatives",
            "Integrals", "Applications of Integration", "Differential Equations",
            "Sequences and Series", "Parametric and Polar Curves",
            "Vector Calculus", "Multivariable Calculus", "Multiple Integrals",
            "Techniques of Integration", "Indefinite Integrals"
        ]
        return {"success": True, "topics": fallback, "note": "fallback used"}


# ---------- User Management ----------
@app.post("/user/login")
def login_user(payload: LoginRequest):
    session = UserSession(payload.user_id)
    return {
        "success": True,
        "user_id": payload.user_id,
        "total_topics": len(session.roadmap),
        "progress": session.progress["topics_status"]
    }


@app.get("/user/progress/{user_id}")
def get_progress(user_id: str):
    try:
        session = UserSession(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "success": True,
        "user_id": user_id,
        "topics_status": session.progress["topics_status"],
        "total_minutes": session.progress["metadata"]["total_minutes"]
    }


@app.post("/user/record")
def record_result(payload: RecordRequest):
    session = UserSession(payload.user_id)
    try:
        session.record_result(payload.topic, payload.logic_alignment_score, payload.is_correct)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------- Problem Generation (with Adaptive Recommendation) ----------
@app.post("/generate")
async def generate_questions(req: GenerateRequest):
    try:
        if req.user_id:
            user_session = UserSession(req.user_id)
            recommended = user_session.get_current_task_params()
            if not req.topics:
                req.topics = [recommended["topic"]]
                req.difficulty = recommended["difficulty"]
                req.mode = recommended["mode"]
                logger.info(f"Adaptive: User {req.user_id} → {recommended['topic']}")

        if not req.topics:
            raise HTTPException(status_code=422, detail="topics are required when user_id is not provided")

        problems = await run_in_threadpool(
            core.generator.generate_batch,
            topics=req.topics,
            num=req.num,
            mode=req.mode,
            difficulty=req.difficulty,
            question_type=req.question_type
        )
        if not problems:
            raise HTTPException(status_code=500, detail="Generation failed, please try again later")

        output_dir = Path(core.config.OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        for prob in problems:
            existing_id = prob.get('id', '')
            if not existing_id or existing_id == 'T2P_GEN_1':
                new_id = str(uuid.uuid4())[:8]
                prob['id'] = new_id
            else:
                new_id = existing_id
            prob['problem_id'] = prob.get('problem_id') or new_id

            file_path = output_dir / f"{new_id}.json"
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(prob, f, ensure_ascii=False, indent=2)

        return {"success": True, "data": problems}

    except HTTPException:
        raise
    except RuntimeError as exc:
        logger.warning("Problem generation unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"Problem generation exception: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Problem generation failed") from exc


# ---------- Intelligent Audit (async — non-blocking) ----------
@app.post("/audit")
async def audit_submission(req: AuditRequest):
    """
    Grade a student submission using GradingService.
    Async: the DeepSeek API call is non-blocking.
    """
    try:
        result = await run_in_threadpool(
            grading_service.audit,
            problem_id=req.problem_id,
            student_input=req.student_work_image,
            is_exam_mode=req.is_exam_mode
        )

        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error", "Audit failed"))

        return result

    except HTTPException:
        raise
    except RuntimeError as exc:
        logger.warning("Audit unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"Audit exception: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Audit failed") from exc


# ---------- Admin: Config reload ----------
@app.post("/admin/reload-config")
def reload_config():
    """Hot-reload configuration from .env (admin use)."""
    global core, grading_service
    try:
        Config.reload()
        AppCore.reset()
        core = AppCore.get()
        grading_service = GradingService()
        return {"success": True, "model": core.config.DEEPSEEK_MODEL}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
