"""
Balanced Class Assignment Algorithm Module
Supports variable class sizes (big/small classes) and special student exclusion.
Uses multi-round snake initialization + intensive greedy swap optimization to achieve
per-subject and total average score differences within 0.4 points.
"""

import pandas as pd
import numpy as np
from typing import List, Tuple, Optional, Dict
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
    Separate students who should not participate in class assignment:
    - All subject scores are non-numeric (absent, long-term leave, etc.)
    - All subject scores are 0
    Returns (normal_df, special_df). special_df is None if no special students.
    """
    def is_special(row):
        for col in subject_cols:
            val = row[col]
            if pd.notna(val):
                try:
                    v = float(val)
                    if v != 0:
                        return False
                except (ValueError, TypeError):
                    continue
        return True  # all non-numeric OR all zero/missing

    mask = df.apply(is_special, axis=1)
    special_df = df[mask].copy() if mask.any() else None
    normal_df = df[~mask].copy()

    return normal_df, special_df


def compute_class_sizes(n_students: int, big_count: int, small_count: int, small_size: int) -> List[int]:
    """
    Compute class size list from big/small config and actual student count.
    Called AFTER special students are removed, so n_students is accurate.
    """
    total_classes = big_count + small_count
    if total_classes < 1:
        return [n_students]

    if small_count > 0 and big_count > 0:
        actual_small_size = min(small_size, n_students // small_count) if small_count > 0 else small_size
        remaining = n_students - small_count * actual_small_size
        if remaining <= 0:
            base = n_students // total_classes
            extra = n_students % total_classes
            return [base + (1 if i < extra else 0) for i in range(total_classes)]
        big_base = remaining // big_count
        big_extra = remaining % big_count
        class_sizes = [big_base + (1 if i < big_extra else 0) for i in range(big_count)]
        class_sizes += [actual_small_size] * small_count
    elif big_count > 0:
        base = n_students // big_count
        extra = n_students % big_count
        class_sizes = [base + (1 if i < extra else 0) for i in range(big_count)]
    else:
        base = n_students // small_count
        extra = n_students % small_count
        class_sizes = [base + (1 if i < extra else 0) for i in range(small_count)]

    diff = n_students - sum(class_sizes)
    for i in range(abs(diff)):
        idx = i % len(class_sizes)
        class_sizes[idx] += 1 if diff > 0 else -1

    return class_sizes


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
            for i in range(n_classes):
                if remaining[i] > 0:
                    current = i
                    break

        assignments.append(current)
        remaining[current] -= 1

        next_c = current + direction
        if next_c >= n_classes:
            direction = -1
        elif next_c < 0:
            direction = 1
        else:
            current = next_c

    return assignments


def calculate_balance_metric(df: pd.DataFrame, subject_cols: List[str]) -> Dict[str, float]:
    """
    Calculate per-metric max-min range of class averages.
    Returns dict with '总分' and each subject's range, plus 'weighted_total'.
    """
    result = {}
    class_means_total = df.groupby('新班级')['总分'].mean()
    result['总分'] = class_means_total.max() - class_means_total.min()

    for col in subject_cols:
        class_means = df.groupby('新班级')[col].mean()
        result[col] = class_means.max() - class_means.min()

    # Weighted: total + subjects (subjects weighted more because they're individual)
    result['weighted_total'] = result['总分'] + sum(result[col] for col in subject_cols) * 2.0
    return result


class FastBalanceTracker:
    """
    Incrementally tracks class sums and counts to efficiently compute
    balance metrics during swap optimization without full groupby each time.
    """
    def __init__(self, df: pd.DataFrame, subject_cols: List[str]):
        self.subject_cols = subject_cols
        self.metrics = ['总分'] + list(subject_cols)
        self.classes = sorted(df['新班级'].unique())
        self.class_to_idx = {c: i for i, c in enumerate(self.classes)}
        n_cls = len(self.classes)
        n_metrics = len(self.metrics)

        # class_sums[metric_idx][class_idx] = sum of scores
        self.class_sums = np.zeros((n_metrics, n_cls))
        # class_counts[class_idx] = number of students
        self.class_counts = np.zeros(n_cls, dtype=int)

        # Pre-extract student score vectors: student_scores[idx] = array of metric values
        self.student_scores = {}
        for idx in df.index:
            scores = np.array([df.loc[idx, m] for m in self.metrics], dtype=float)
            self.student_scores[idx] = scores

            cls = df.loc[idx, '新班级']
            ci = self.class_to_idx[cls]
            self.class_sums[:, ci] += scores
            self.class_counts[ci] += 1

    def get_score(self) -> float:
        """Compute the weighted balance score from current state."""
        # means[metric_idx][class_idx]
        means = self.class_sums / np.maximum(self.class_counts, 1)
        ranges = means.max(axis=1) - means.min(axis=1)
        # ranges[0] is 总分, rest are subjects
        return ranges[0] + np.sum(ranges[1:]) * 2.0

    def get_metrics(self) -> Dict[str, float]:
        """Return per-metric ranges."""
        means = self.class_sums / np.maximum(self.class_counts, 1)
        ranges = means.max(axis=1) - means.min(axis=1)
        result = {}
        for i, m in enumerate(self.metrics):
            result[m] = float(ranges[i])
        result['weighted_total'] = float(ranges[0] + np.sum(ranges[1:]) * 2.0)
        return result

    def swap(self, idx_a: int, class_a_idx: int, idx_b: int, class_b_idx: int):
        """Perform a swap: move idx_a from class_a to class_b, idx_b from class_b to class_a."""
        scores_a = self.student_scores[idx_a]
        scores_b = self.student_scores[idx_b]

        self.class_sums[:, class_a_idx] -= scores_a
        self.class_sums[:, class_a_idx] += scores_b
        self.class_sums[:, class_b_idx] -= scores_b
        self.class_sums[:, class_b_idx] += scores_a

    def find_worst_metric_classes(self) -> Tuple[int, int, int]:
        """Find the metric with largest range and the classes at max/min."""
        means = self.class_sums / np.maximum(self.class_counts, 1)
        ranges = means.max(axis=1) - means.min(axis=1)
        # Weight subjects more
        weighted_ranges = ranges.copy()
        weighted_ranges[1:] *= 2.0
        worst_metric = int(np.argmax(weighted_ranges))
        metric_means = means[worst_metric]
        best_class = int(np.argmax(metric_means))
        worst_class = int(np.argmin(metric_means))
        return worst_metric, best_class, worst_class


def optimize_balance(df: pd.DataFrame, subject_cols: List[str],
                     locked_indices: set, n_iterations: int = 5000) -> pd.DataFrame:
    """
    Greedy optimization by swapping non-locked students.
    Uses FastBalanceTracker for O(1) score evaluation per swap.
    Targeted strategy: preferentially swaps students between the highest and
    lowest average classes for the worst-balanced metric.
    """
    df = df.copy()
    classes = sorted(df['新班级'].unique())
    n_classes = len(classes)
    if n_classes < 2:
        return df

    tracker = FastBalanceTracker(df, subject_cols)
    class_to_idx = tracker.class_to_idx

    # Build swappable indices per class (by class index)
    swappable_by_cls = {}
    student_class_idx = {}  # idx -> class_idx
    for cls in classes:
        ci = class_to_idx[cls]
        swappable_by_cls[ci] = [idx for idx in df[df['新班级'] == cls].index.tolist()
                                if idx not in locked_indices]
        for idx in df[df['新班级'] == cls].index.tolist():
            student_class_idx[idx] = ci

    current_score = tracker.get_score()
    no_improvement = 0
    max_no_improvement = 500

    for iteration in range(n_iterations):
        if random.random() < 0.75:
            # Targeted: find worst metric and swap between its best/worst classes
            _, best_ci, worst_ci = tracker.find_worst_metric_classes()
            if (not swappable_by_cls.get(best_ci) or not swappable_by_cls.get(worst_ci)
                    or best_ci == worst_ci):
                eligible = [ci for ci in range(n_classes)
                            if len(swappable_by_cls.get(ci, [])) > 0]
                if len(eligible) < 2:
                    break
                best_ci, worst_ci = random.sample(eligible, 2)
            class_a_idx, class_b_idx = best_ci, worst_ci
        else:
            eligible = [ci for ci in range(n_classes)
                        if len(swappable_by_cls.get(ci, [])) > 0]
            if len(eligible) < 2:
                break
            class_a_idx, class_b_idx = random.sample(eligible, 2)

        if not swappable_by_cls[class_a_idx] or not swappable_by_cls[class_b_idx]:
            continue

        idx_a = random.choice(swappable_by_cls[class_a_idx])
        idx_b = random.choice(swappable_by_cls[class_b_idx])

        # Perform swap in tracker
        tracker.swap(idx_a, class_a_idx, idx_b, class_b_idx)
        new_score = tracker.get_score()

        if new_score < current_score:
            current_score = new_score
            # Update bookkeeping
            swappable_by_cls[class_a_idx].remove(idx_a)
            swappable_by_cls[class_a_idx].append(idx_b)
            swappable_by_cls[class_b_idx].remove(idx_b)
            swappable_by_cls[class_b_idx].append(idx_a)
            student_class_idx[idx_a] = class_b_idx
            student_class_idx[idx_b] = class_a_idx
            # Also update the dataframe
            df.loc[idx_a, '新班级'] = classes[class_b_idx]
            df.loc[idx_b, '新班级'] = classes[class_a_idx]
            no_improvement = 0
        else:
            # Revert swap in tracker
            tracker.swap(idx_a, class_b_idx, idx_b, class_a_idx)
            no_improvement += 1

        if no_improvement >= max_no_improvement:
            break

    return df


def assign_classes(df: pd.DataFrame,
                   class_sizes: List[int],
                   subject_cols: List[str],
                   big_count: int = 0,
                   small_count: int = 0,
                   small_size: int = 30,
                   top_tier_ratio: float = 0.15,
                   n_rounds: int = 8) -> Tuple[pd.DataFrame, Optional[pd.DataFrame]]:
    """
    Multi-round class assignment with variable class sizes:
    1. Separate special students (all scores non-numeric)
    2. Convert and calculate scores
    3. Recompute class_sizes based on actual normal student count (fixes big/small bug)
    4. Run multiple rounds of snake + optimization, keep best result
    5. Lock top tier only, optimize all other students

    Returns (result_df, special_df)
    """
    df = df.copy()

    # Add unique internal ID for reliable mapping (考号 can be duplicated across classes)
    df['_uid'] = range(len(df))

    # Step 1: Separate special students
    df, special_df = separate_special_students(df, subject_cols)

    if len(df) == 0:
        df.drop(columns=['_uid'], inplace=True, errors='ignore')
        if special_df is not None:
            special_df.drop(columns=['_uid'], inplace=True, errors='ignore')
        return df, special_df

    # Step 2: Convert to numeric
    for col in subject_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    df['综合分'] = calculate_composite_score(df, subject_cols)
    df['总分'] = calculate_total_score(df, subject_cols)

    # Step 3: Sort by composite score
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

    # Step 4: Recompute class sizes based on actual normal student count
    actual_total = len(df)
    total_classes = big_count + small_count

    if total_classes > 0:
        class_sizes = compute_class_sizes(actual_total, big_count, small_count, small_size)
    else:
        # Fallback: adjust provided class_sizes to match actual count
        target_total = sum(class_sizes)
        if target_total != actual_total:
            ratio = actual_total / target_total if target_total > 0 else 1
            adjusted = [max(1, round(s * ratio)) for s in class_sizes]
            diff = actual_total - sum(adjusted)
            for i in range(abs(diff)):
                idx = i % len(adjusted)
                adjusted[idx] += 1 if diff > 0 else -1
            class_sizes = adjusted

    # Step 5: Multi-round snake + optimization
    n_classes = len(class_sizes)
    n_students = len(df)
    top_count = int(n_students * top_tier_ratio)
    locked_indices = set(range(top_count))

    best_df = None
    best_score = float('inf')

    for round_idx in range(n_rounds):
        round_df = df.copy()

        if round_idx == 0:
            # First round: standard snake assignment
            assignments = snake_assign_variable(n_students, class_sizes)
        else:
            # Subsequent rounds: shuffle within score tiers before snake
            # Create small random perturbations in student order
            indices = list(range(n_students))
            block_size = max(n_classes * 2, 6)

            for start in range(0, n_students, block_size):
                end = min(start + block_size, n_students)
                block = indices[start:end]
                # Only shuffle non-locked positions
                unlocked = [i for i in block if i not in locked_indices]
                if len(unlocked) > 1:
                    shuffled_vals = unlocked.copy()
                    random.shuffle(shuffled_vals)
                    for orig, new_val in zip(unlocked, shuffled_vals):
                        indices[orig] = new_val

            # Reorder round_df by shuffled indices
            round_df = round_df.iloc[indices].reset_index(drop=True)
            assignments = snake_assign_variable(n_students, class_sizes)

        round_df['新班级'] = [f"{i+1}班" for i in assignments]

        # Optimize with increased iterations
        round_df = optimize_balance(round_df, subject_cols, locked_indices, n_iterations=5000)

        score = calculate_balance_score(round_df, subject_cols)
        if score < best_score:
            best_score = score
            best_df = round_df.copy()

    # Map class assignments back using unique _uid (safe even with duplicate 考号)
    assignment_map = dict(zip(best_df['_uid'], best_df['新班级']))
    df['新班级'] = df['_uid'].map(assignment_map)

    # Clean up internal columns
    df.drop(columns=['_uid'], inplace=True)
    if special_df is not None:
        special_df.drop(columns=['_uid'], inplace=True, errors='ignore')

    # Final safety: recalculate total score
    df['总分'] = calculate_total_score(df, subject_cols)

    return df, special_df


def calculate_balance_score(df: pd.DataFrame, subject_cols: List[str]) -> float:
    """Calculate balance score (lower is better) based on max-min range."""
    metrics = calculate_balance_metric(df, subject_cols)
    return metrics['weighted_total']
