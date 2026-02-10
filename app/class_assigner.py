"""
Balanced Snake Class Assignment Algorithm Module
Supports variable class sizes (big/small classes) and special student exclusion.
"""

import pandas as pd
import numpy as np
from typing import List, Tuple, Optional
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


def separate_special_students(df: pd.DataFrame, subject_cols: List[str]) -> Tuple[pd.DataFrame, Optional[pd.DataFrame]]:
    """
    Separate students with ALL subject scores non-numeric (absent, long-term leave, etc.).
    Returns (normal_df, special_df). special_df is None if no special students.
    """
    def is_all_non_numeric(row):
        for col in subject_cols:
            val = row[col]
            if pd.notna(val):
                try:
                    float(val)
                    return False
                except (ValueError, TypeError):
                    continue
        return True

    mask = df.apply(is_all_non_numeric, axis=1)
    special_df = df[mask].copy() if mask.any() else None
    normal_df = df[~mask].copy()

    return normal_df, special_df


def snake_assign_variable(n_students: int, class_sizes: List[int]) -> List[int]:
    """
    Snake distribution with variable class sizes.
    class_sizes[i] = target number of students for class i.
    """
    n_classes = len(class_sizes)
    remaining = list(class_sizes)
    assignments = []

    direction = 1
    current = 0

    for _ in range(n_students):
        # Find next class with remaining capacity
        attempts = 0
        while remaining[current] <= 0 and attempts < n_classes * 2:
            next_c = current + direction
            if next_c >= n_classes:
                direction = -1
                next_c = current + direction
            elif next_c < 0:
                direction = 1
                next_c = current + direction
            current = next_c
            attempts += 1

        if remaining[current] <= 0:
            # All classes at target, find any with space
            for i in range(n_classes):
                if remaining[i] > 0:
                    current = i
                    break

        assignments.append(current)
        remaining[current] -= 1

        # Move to next class
        next_c = current + direction
        if next_c >= n_classes:
            direction = -1
        elif next_c < 0:
            direction = 1
        else:
            current = next_c

    return assignments


def calculate_balance_score(df: pd.DataFrame, subject_cols: List[str]) -> float:
    """Calculate balance score (lower is better) based on class variance."""
    if '新班级' not in df.columns:
        return float('inf')
    total_variance = df.groupby('新班级')['总分'].mean().var()
    for col in subject_cols:
        total_variance += df.groupby('新班级')[col].mean().var()
    return total_variance


def optimize_balance_middle_tier(df: pd.DataFrame, subject_cols: List[str],
                                  locked_indices: set, n_iterations: int = 400) -> pd.DataFrame:
    """Greedy optimization by swapping ONLY non-locked students within same-size classes."""
    df = df.copy()
    n_classes = df['新班级'].nunique()
    if n_classes < 2:
        return df

    # Group classes by size for same-size swaps
    class_size_map = df['新班级'].value_counts().to_dict()
    size_to_classes = {}
    for cls, size in class_size_map.items():
        size_to_classes.setdefault(size, []).append(cls)

    swappable = {cls: [idx for idx in df[df['新班级'] == cls].index.tolist() if idx not in locked_indices]
                 for cls in df['新班级'].unique()}

    current_score = calculate_balance_score(df, subject_cols)
    no_improvement = 0

    for _ in range(n_iterations):
        # Pick a size group with at least 2 classes
        eligible_groups = [classes for classes in size_to_classes.values()
                          if len(classes) >= 2 and any(len(swappable.get(c, [])) > 0 for c in classes)]
        if not eligible_groups:
            # Try cross-size swaps as fallback
            all_classes = [c for c, idxs in swappable.items() if len(idxs) > 0]
            if len(all_classes) < 2:
                break
            class_a, class_b = random.sample(all_classes, 2)
        else:
            group = random.choice(eligible_groups)
            classes_with_swaps = [c for c in group if len(swappable.get(c, [])) > 0]
            if len(classes_with_swaps) < 2:
                no_improvement += 1
                if no_improvement >= 80:
                    break
                continue
            class_a, class_b = random.sample(classes_with_swaps, 2)

        if not swappable[class_a] or not swappable[class_b]:
            continue

        idx_a = random.choice(swappable[class_a])
        idx_b = random.choice(swappable[class_b])

        df.loc[idx_a, '新班级'] = class_b
        df.loc[idx_b, '新班级'] = class_a

        new_score = calculate_balance_score(df, subject_cols)

        if new_score < current_score:
            current_score = new_score
            swappable[class_a].remove(idx_a)
            swappable[class_a].append(idx_b)
            swappable[class_b].remove(idx_b)
            swappable[class_b].append(idx_a)
            no_improvement = 0
        else:
            df.loc[idx_a, '新班级'] = class_a
            df.loc[idx_b, '新班级'] = class_b
            no_improvement += 1

        if no_improvement >= 80:
            break

    return df


def assign_classes(df: pd.DataFrame, class_sizes: List[int],
                   subject_cols: List[str],
                   top_tier_ratio: float = 0.15,
                   bottom_tier_ratio: float = 0.15) -> Tuple[pd.DataFrame, Optional[pd.DataFrame]]:
    """
    Tiered class assignment with variable class sizes:
    1. Separate special students (all scores non-numeric)
    2. Convert and calculate scores
    3. Snake distribution respecting class size targets
    4. Lock top & bottom tier, optimize middle
    
    Returns (result_df, special_df)
    """
    df = df.copy()

    # Step 1: Separate special students
    df, special_df = separate_special_students(df, subject_cols)

    if len(df) == 0:
        return df, special_df

    # Step 2: Convert to numeric
    for col in subject_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    df['综合分'] = calculate_composite_score(df, subject_cols)
    df['总分'] = calculate_total_score(df, subject_cols)

    # Step 3: Sort
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

    # Adjust class sizes to match actual student count (after removing special students)
    actual_total = len(df)
    target_total = sum(class_sizes)

    if target_total != actual_total:
        # Proportionally scale class sizes
        ratio = actual_total / target_total if target_total > 0 else 1
        adjusted = [max(1, round(s * ratio)) for s in class_sizes]
        # Fix rounding difference
        diff = actual_total - sum(adjusted)
        for i in range(abs(diff)):
            idx = i % len(adjusted)
            adjusted[idx] += 1 if diff > 0 else -1
        class_sizes = adjusted

    # Step 4: Snake assign
    n_classes = len(class_sizes)
    assignments = snake_assign_variable(len(df), class_sizes)
    df['新班级'] = [f"{i+1}班" for i in assignments]

    # Step 5: Lock top and bottom tiers, optimize middle
    n_students = len(df)
    top_count = int(n_students * top_tier_ratio)
    bottom_count = int(n_students * bottom_tier_ratio)
    locked_indices = set(range(top_count)) | set(range(n_students - bottom_count, n_students))

    df = optimize_balance_middle_tier(df, subject_cols, locked_indices, n_iterations=400)

    return df, special_df
