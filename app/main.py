"""
Student Grade Auto Class Assignment System - FastAPI Main Entry
"""

import os
import shutil
import uuid
import threading
from pathlib import Path
from typing import List
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

CLEANUP_DELAY = 300  # 5 minutes


def schedule_cleanup(session_id: str):
    """Schedule session file cleanup after CLEANUP_DELAY seconds."""
    def do_cleanup():
        session_dir = OUTPUT_DIR / session_id
        zip_path = OUTPUT_DIR / f"{session_id}.zip"
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
        if zip_path.exists():
            zip_path.unlink(missing_ok=True)
    
    timer = threading.Timer(CLEANUP_DELAY, do_cleanup)
    timer.daemon = True
    timer.start()

static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.get("/")
async def root():
    """Serve main page."""
    index_path = static_path / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "学生成绩自动分班系统 API"}


@app.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    """Upload and process grade files, return class assignment results."""
    if not files:
        raise HTTPException(status_code=400, detail="未上传任何文件")
    
    session_id = str(uuid.uuid4())
    session_upload_dir = UPLOAD_DIR / session_id
    session_output_dir = OUTPUT_DIR / session_id
    
    session_upload_dir.mkdir(parents=True, exist_ok=True)
    session_output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        for file in files:
            if not file.filename:
                continue
            
            file_path = session_upload_dir / file.filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)
        
        grade_data = parse_nested_folder(session_upload_dir)
        
        if not grade_data:
            raise HTTPException(status_code=400, detail="未找到有效的成绩文件")
        
        results = []
        
        for grade, df in grade_data.items():
            subject_cols = identify_subject_columns(df)
            
            if not subject_cols:
                continue
            
            n_classes = df['原班级'].nunique()
            if n_classes < 1:
                n_classes = 1
            
            result_df = assign_classes(df, n_classes, subject_cols)
            
            grade_name = grade_number_to_chinese(grade)
            result_file = generate_result_excel(
                result_df, subject_cols, session_output_dir, grade_name
            )
            
            results.append({
                "grade": grade_name,
                "student_count": len(result_df),
                "class_count": n_classes,
                "result_file": result_file.name
            })
        
        shutil.rmtree(session_upload_dir, ignore_errors=True)
        
        return JSONResponse({
            "success": True,
            "session_id": session_id,
            "results": results,
            "message": f"成功处理 {len(results)} 个年级的分班"
        })
        
    except Exception as e:
        shutil.rmtree(session_upload_dir, ignore_errors=True)
        shutil.rmtree(session_output_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


@app.get("/download/{session_id}/{filename}")
async def download_file(session_id: str, filename: str):
    """Download result file and schedule cleanup."""
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
    """Download all result files as ZIP and schedule cleanup."""
    session_dir = OUTPUT_DIR / session_id
    
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="会话不存在")
    
    zip_path = OUTPUT_DIR / f"{session_id}.zip"
    shutil.make_archive(str(zip_path.with_suffix('')), 'zip', session_dir)
    
    schedule_cleanup(session_id)
    
    return FileResponse(
        path=zip_path,
        filename="分班结果.zip",
        media_type="application/zip"
    )


@app.delete("/cleanup/{session_id}")
async def cleanup(session_id: str):
    """Clean up session files."""
    session_output_dir = OUTPUT_DIR / session_id
    zip_path = OUTPUT_DIR / f"{session_id}.zip"
    
    if session_output_dir.exists():
        shutil.rmtree(session_output_dir, ignore_errors=True)
    
    if zip_path.exists():
        zip_path.unlink()
    
    return {"success": True, "message": "清理完成"}
