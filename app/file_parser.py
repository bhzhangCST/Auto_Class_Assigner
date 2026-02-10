"""
Excel File Parser Module
Supports .xlsx and .xls formats with automatic header detection.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional


def auto_detect_headers(df: pd.DataFrame) -> Dict[str, str]:
    """Auto-detect and standardize column headers."""
    column_mapping = {}
    
    id_patterns = ['考号', '学号', '编号', 'id', '序号']
    name_patterns = ['姓名', '名字', '学生姓名', 'name']
    subject_patterns = ['语文', '数学', '英语', '科学', '道法', '品德', '体育', '音乐', '美术']
    
    for idx, col in enumerate(df.columns):
        col_str = str(col).strip().lower()
        
        if any(p in col_str for p in id_patterns):
            column_mapping[col] = '考号'
        elif any(p in col_str for p in name_patterns):
            column_mapping[col] = '姓名'
        elif any(p in col_str for p in subject_patterns):
            for p in subject_patterns:
                if p in col_str:
                    column_mapping[col] = p
                    break
        elif 'unnamed' in col_str:
            sample_data = df[col].dropna().head(10)
            if len(sample_data) == 0:
                continue
                
            if idx == 0:
                if sample_data.apply(lambda x: isinstance(x, (int, float)) or str(x).isdigit()).all():
                    column_mapping[col] = '考号'
            elif idx == 1:
                if sample_data.apply(lambda x: isinstance(x, str) and any('\u4e00' <= c <= '\u9fff' for c in str(x))).any():
                    column_mapping[col] = '姓名'
            else:
                if pd.api.types.is_numeric_dtype(sample_data):
                    column_mapping[col] = f'科目{idx-1}'
    
    return column_mapping


def parse_excel_file(file_path: Path) -> Optional[pd.DataFrame]:
    """Parse a single Excel file (.xlsx or .xls)."""
    try:
        suffix = file_path.suffix.lower()
        
        if suffix == '.xlsx':
            df = pd.read_excel(file_path, engine='openpyxl')
        elif suffix == '.xls':
            df = pd.read_excel(file_path, engine='xlrd')
        else:
            return None
        
        column_mapping = auto_detect_headers(df)
        df = df.rename(columns=column_mapping)
        
        if '考号' not in df.columns or '姓名' not in df.columns:
            return None
        
        filename = file_path.stem
        parts = filename.split('.')
        if len(parts) >= 2:
            grade = parts[0]
            class_num = parts[1]
            df['原班级'] = f"{grade}年级{class_num}班"
            df['年级'] = grade
        else:
            df['原班级'] = filename
            df['年级'] = 'unknown'
        
        return df
        
    except Exception as e:
        print(f"Failed to parse {file_path}: {e}")
        return None


def identify_subject_columns(df: pd.DataFrame) -> List[str]:
    """Identify subject score columns by name matching or numeric type detection."""
    exclude_cols = ['考号', '姓名', '原班级', '年级', '新班级', '总分', '综合分', '年级排名']
    known_subjects = ['语文', '数学', '英语', '科学', '道法', '品德', '体育', '音乐', '美术', 
                      '物理', '化学', '生物', '历史', '地理', '政治']
    subject_cols = []
    
    for col in df.columns:
        if col in exclude_cols:
            continue
        
        if col in known_subjects:
            subject_cols.append(col)
            continue
        
        if any(subj in str(col) for subj in known_subjects):
            subject_cols.append(col)
            continue
            
        if pd.api.types.is_numeric_dtype(df[col]):
            subject_cols.append(col)
        else:
            try:
                numeric_col = pd.to_numeric(df[col], errors='coerce')
                if numeric_col.notna().sum() > len(df) * 0.5:
                    if not any(p in str(col).lower() for p in ['id', '号', '班', '级', '名']):
                        subject_cols.append(col)
            except:
                pass
    
    return subject_cols


def parse_folder(folder_path: Path) -> Dict[str, pd.DataFrame]:
    """Parse all Excel files in a folder, grouped by grade."""
    grade_data: Dict[str, List[pd.DataFrame]] = {}
    
    for file_path in folder_path.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in ['.xlsx', '.xls']:
            df = parse_excel_file(file_path)
            if df is not None:
                grade = df['年级'].iloc[0]
                if grade not in grade_data:
                    grade_data[grade] = []
                grade_data[grade].append(df)
    
    result = {}
    for grade, dfs in grade_data.items():
        if dfs:
            result[grade] = pd.concat(dfs, ignore_index=True)
    
    return result


def parse_nested_folder(folder_path: Path) -> Dict[str, pd.DataFrame]:
    """Parse nested folder structure (grade folders containing class files)."""
    grade_data: Dict[str, List[pd.DataFrame]] = {}
    
    grade_name_map = {
        '一': '1', '二': '2', '三': '3', '四': '4', '五': '5', '六': '6',
        '1': '1', '2': '2', '3': '3', '4': '4', '5': '5', '6': '6'
    }
    
    def process_file(file_path: Path, grade_hint: Optional[str] = None):
        if file_path.suffix.lower() not in ['.xlsx', '.xls']:
            return
            
        df = parse_excel_file(file_path)
        if df is None:
            return
            
        if grade_hint and df['年级'].iloc[0] == 'unknown':
            for key, val in grade_name_map.items():
                if key in grade_hint:
                    df['年级'] = val
                    break
        
        grade = df['年级'].iloc[0]
        if grade not in grade_data:
            grade_data[grade] = []
        grade_data[grade].append(df)
    
    for item in folder_path.iterdir():
        if item.is_file():
            process_file(item)
        elif item.is_dir():
            grade_hint = item.name
            for file_path in item.iterdir():
                if file_path.is_file():
                    process_file(file_path, grade_hint)
    
    result = {}
    for grade, dfs in grade_data.items():
        if dfs:
            result[grade] = pd.concat(dfs, ignore_index=True)
    
    return result
