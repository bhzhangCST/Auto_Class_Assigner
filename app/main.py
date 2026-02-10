"""
Student Grade Auto Class Assignment System - FastAPI Main Entry
Two-step API: upload-preview → process with class size config.
"""

import os
import shutil
import uuid
import threading
from pathlib import Path
from typing import List, Dict, Optional
from pydantic import BaseModel
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .file_parser import parse_nested_folder, identify_subject_columns
from .class_assigner import assign_classes
from .report_generator import generate_result_excel, grade_number_to_chinese

app = FastAPI(
    title="ACA：智能分班系统",
    description="基于均衡蛇形算法",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

CLEANUP_DELAY = 300

# In-memory cache for parsed grade data between preview and process steps
session_cache: Dict[str, dict] = {}


def schedule_cleanup(session_id: str):
    """Schedule session file cleanup after CLEANUP_DELAY seconds."""
    def do_cleanup():
        for d in [OUTPUT_DIR / session_id, UPLOAD_DIR / session_id]:
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
        zip_path = OUTPUT_DIR / f"{session_id}.zip"
        if zip_path.exists():
            zip_path.unlink(missing_ok=True)
        session_cache.pop(session_id, None)

    timer = threading.Timer(CLEANUP_DELAY, do_cleanup)
    timer.daemon = True
    timer.start()


static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.get("/")
async def root():
    index_path = static_path / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "ACA智能分班系统"}


@app.post("/upload-preview")
async def upload_preview(files: List[UploadFile] = File(...)):
    """Step 1: Upload files, parse, and return grade info for configuration."""
    if not files:
        raise HTTPException(status_code=400, detail="未上传任何文件")

    session_id = str(uuid.uuid4())
    session_upload_dir = UPLOAD_DIR / session_id
    session_upload_dir.mkdir(parents=True, exist_ok=True)

    try:
        for file in files:
            if not file.filename:
                continue
            file_path = session_upload_dir / file.filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(await file.read())

        grade_data = parse_nested_folder(session_upload_dir)

        if not grade_data:
            shutil.rmtree(session_upload_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail="未找到有效的成绩文件")

        # Cache parsed data for the process step
        session_cache[session_id] = {
            "grade_data": grade_data,
            "upload_dir": session_upload_dir
        }

        grades = []
        for grade, df in grade_data.items():
            subject_cols = identify_subject_columns(df)
            grades.append({
                "grade": grade,
                "grade_name": grade_number_to_chinese(grade),
                "student_count": len(df),
                "original_classes": df['原班级'].nunique(),
                "subjects": subject_cols
            })

        return JSONResponse({
            "success": True,
            "session_id": session_id,
            "grades": grades
        })

    except HTTPException:
        raise
    except Exception as e:
        shutil.rmtree(session_upload_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")


class ClassConfig(BaseModel):
    big_count: int = 0
    small_count: int = 0
    small_size: int = 30


class ProcessRequest(BaseModel):
    session_id: str
    configs: Dict[str, ClassConfig]


@app.post("/process")
async def process(request: ProcessRequest):
    """Step 2: Run class assignment with user-configured class sizes."""
    session_id = request.session_id

    if session_id not in session_cache:
        raise HTTPException(status_code=404, detail="会话已过期，请重新上传")

    cached = session_cache[session_id]
    grade_data = cached["grade_data"]

    session_output_dir = OUTPUT_DIR / session_id
    session_output_dir.mkdir(parents=True, exist_ok=True)

    try:
        results = []

        for grade, df in grade_data.items():
            subject_cols = identify_subject_columns(df)
            if not subject_cols:
                continue

            config = request.configs.get(grade, ClassConfig())
            big_count = config.big_count
            small_count = config.small_count
            small_size = config.small_size

            total_classes = big_count + small_count
            if total_classes < 1:
                total_classes = df['原班级'].nunique()
                big_count = total_classes
                small_count = 0

            # Calculate class size targets
            if small_count > 0 and big_count > 0:
                remaining = len(df) - small_count * small_size
                # Filter out special students before calculating, but we need to
                # let assign_classes handle the filtering
                class_sizes = [max(1, round(remaining / big_count))] * big_count + [small_size] * small_count
            elif big_count > 0:
                base = len(df) // big_count
                extra = len(df) % big_count
                class_sizes = [base + (1 if i < extra else 0) for i in range(big_count)]
            else:
                class_sizes = [small_size] * small_count

            result_df, special_df = assign_classes(df, class_sizes, subject_cols)

            grade_name = grade_number_to_chinese(grade)
            result_file = generate_result_excel(
                result_df, special_df, subject_cols, session_output_dir, grade_name
            )

            results.append({
                "grade": grade_name,
                "student_count": len(result_df),
                "special_count": len(special_df) if special_df is not None else 0,
                "class_count": total_classes,
                "result_file": result_file.name
            })

        # Clean up upload dir
        upload_dir = cached.get("upload_dir")
        if upload_dir and upload_dir.exists():
            shutil.rmtree(upload_dir, ignore_errors=True)
        session_cache.pop(session_id, None)

        return JSONResponse({
            "success": True,
            "session_id": session_id,
            "results": results,
            "message": f"成功处理 {len(results)} 个年级的分班"
        })

    except Exception as e:
        shutil.rmtree(session_output_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


@app.get("/download/{session_id}/{filename}")
async def download_file(session_id: str, filename: str):
    file_path = OUTPUT_DIR / session_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    schedule_cleanup(session_id)
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.get("/download-all/{session_id}")
async def download_all(session_id: str):
    session_dir = OUTPUT_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="会话不存在")
    zip_path = OUTPUT_DIR / f"{session_id}.zip"
    shutil.make_archive(str(zip_path.with_suffix('')), 'zip', session_dir)
    schedule_cleanup(session_id)
    return FileResponse(path=zip_path, filename="分班结果.zip", media_type="application/zip")


@app.delete("/cleanup/{session_id}")
async def cleanup(session_id: str):
    for d in [OUTPUT_DIR / session_id, UPLOAD_DIR / session_id]:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
    zip_path = OUTPUT_DIR / f"{session_id}.zip"
    if zip_path.exists():
        zip_path.unlink(missing_ok=True)
    session_cache.pop(session_id, None)
    return {"success": True, "message": "清理完成"}
