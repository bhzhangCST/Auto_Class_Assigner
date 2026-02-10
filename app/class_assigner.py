"""
Balanced Snake Class Assignment Algorithm Module
Uses Z-score normalization with tiered distribution for balanced classes.
Top students strictly snake-assigned, middle/bottom students optimized for balance.
"""

import pandas as pd
import numpy as np
from typing import List
import random


def calculate_composite_score(df: pd.DataFrame, subject_cols: List[str]) -> pd.Series:
    """Calculate Z-score normalized composite score for balanced subject weighting."""
    z_scores = pd.DataFrame()
    
    for col in subject_cols:
        scores = pd.to_numeric(df[col], errors='coerce').fillna(0)
        mean = scores.mean()
        std = scores.std()
        z_scores[col] = (scores - mean) / std if std > 0 else 0
    
    return z_scores.mean(axis=1)


def calculate_total_score(df: pd.DataFrame, subject_cols: List[str]) -> pd.Series:
    """Calculate raw total score by summing all subjects."""
    total = pd.Series(0.0, index=df.index)
    for col in subject_cols:
        total += pd.to_numeric(df[col], errors='coerce').fillna(0)
    return total


def snake_assign(n_students: int, n_classes: int) -> List[int]:
    """Generate snake pattern assignment sequence (1,2,3,3,2,1,1,2,3...)."""
    assignments = []
    direction = 1
    current_class = 0
    
    for i in range(n_students):
        assignments.append(current_class)
        next_class = current_class + direction
        
        if next_class >= n_classes:
            direction = -1
        elif next_class < 0:
            direction = 1
        else:
            current_class = next_class
    
    return assignments


def calculate_balance_score(df: pd.DataFrame, subject_cols: List[str]) -> float:
    """Calculate balance score (lower is better) based on class variance."""
    if '新班级' not in df.columns:
        return float('inf')
    
    total_variance = df.groupby('新班级')['总分'].mean().var()
    
    for col in subject_cols:
        class_means = df.groupby('新班级')[col].apply(
            lambda x: pd.to_numeric(x, errors='coerce').fillna(0).mean()
        )
        total_variance += class_means.var()
    
    return total_variance


def optimize_balance_middle_tier(df: pd.DataFrame, subject_cols: List[str], 
                                  locked_indices: set, n_iterations: int = 300) -> pd.DataFrame:
    """
    Greedy optimization by swapping ONLY non-locked students.
    Top and bottom tier students are locked in their snake positions.
    """
    df = df.copy()
    n_classes = df['新班级'].nunique()
    
    if n_classes < 2:
        return df
    
    # Build class indices, excluding locked students from swap candidates
    swappable_indices = {cls: [idx for idx in df[df['新班级'] == cls].index.tolist() 
                               if idx not in locked_indices]
                         for cls in df['新班级'].unique()}
    
    # Check if we have enough swappable students
    total_swappable = sum(len(v) for v in swappable_indices.values())
    if total_swappable < 4:
        return df
    
    current_score = calculate_balance_score(df, subject_cols)
    no_improvement_count = 0
    max_no_improvement = 80
    
    for iteration in range(n_iterations):
        # Get classes with swappable students
        classes_with_swaps = [cls for cls, indices in swappable_indices.items() if len(indices) > 0]
        if len(classes_with_swaps) < 2:
            break
            
        class_a, class_b = random.sample(classes_with_swaps, 2)
        
        if not swappable_indices[class_a] or not swappable_indices[class_b]:
            continue
        
        idx_a = random.choice(swappable_indices[class_a])
        idx_b = random.choice(swappable_indices[class_b])
        
        # Perform swap
        df.loc[idx_a, '新班级'] = class_b
        df.loc[idx_b, '新班级'] = class_a
        
        new_score = calculate_balance_score(df, subject_cols)
        
        if new_score < current_score:
            current_score = new_score
            swappable_indices[class_a].remove(idx_a)
            swappable_indices[class_a].append(idx_b)
            swappable_indices[class_b].remove(idx_b)
            swappable_indices[class_b].append(idx_a)
            no_improvement_count = 0
        else:
            # Revert swap
            df.loc[idx_a, '新班级'] = class_a
            df.loc[idx_b, '新班级'] = class_b
            no_improvement_count += 1
        
        if no_improvement_count >= max_no_improvement:
            break
    
    return df


def assign_classes(df: pd.DataFrame, n_classes: int, 
                   subject_cols: List[str],
                   top_tier_ratio: float = 0.15,
                   bottom_tier_ratio: float = 0.15) -> pd.DataFrame:
    """
    Tiered class assignment pipeline:
    1. Convert scores to numeric
    2. Calculate composite and total scores
    3. Sort by composite score
    4. Snake distribution for ALL students
    5. Lock top & bottom tier students in place
    6. Optimize balance by swapping ONLY middle tier students
    
    This ensures top students are evenly distributed while maintaining balance.
    """
    df = df.copy()
    
    for col in subject_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    df['综合分'] = calculate_composite_score(df, subject_cols)
    df['总分'] = calculate_total_score(df, subject_cols)
    
    # Sort by composite score, then total, then language, then ID
    sort_cols = ['综合分', '总分']
    ascending = [False, False]
    
    if '语文' in df.columns:
        sort_cols.append('语文')
        ascending.append(False)
    
    if '考号' in df.columns:
        sort_cols.append('考号')
        ascending.append(True)
    
    df = df.sort_values(sort_cols, ascending=ascending).reset_index(drop=True)
    df['年级排名'] = range(1, len(df) + 1)
    
    # Snake assign all students
    assignments = snake_assign(len(df), n_classes)
    df['新班级'] = [f"{i+1}班" for i in assignments]
    
    # Determine locked indices (top and bottom tier)
    n_students = len(df)
    top_count = int(n_students * top_tier_ratio)
    bottom_count = int(n_students * bottom_tier_ratio)
    
    # Top tier: first top_count students (indices 0 to top_count-1)
    # Bottom tier: last bottom_count students
    locked_indices = set(range(top_count)) | set(range(n_students - bottom_count, n_students))
    
    # Optimize only middle tier
    df = optimize_balance_middle_tier(df, subject_cols, locked_indices, n_iterations=400)
    
    return df
