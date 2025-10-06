"""
Common utilities for data loaders to handle numpy/pandas types safely
"""
import numpy as np
import pandas as pd
from decimal import Decimal


def safe_int(value, default=None):
    """
    Convert value to Python int, handling numpy types and overflow
    Returns default if conversion fails or value is out of PostgreSQL integer range
    PostgreSQL INTEGER range: -2147483648 to 2147483647
    """
    if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
        return default

    try:
        # Convert to Python int (handles numpy.int64, numpy.int32, etc.)
        result = int(value)

        # Check PostgreSQL INTEGER range
        if result < -2147483648 or result > 2147483647:
            # Use BIGINT range instead or return default
            if result < -9223372036854775808 or result > 9223372036854775807:
                return default
            return result  # Within BIGINT range

        return result
    except (ValueError, TypeError, OverflowError):
        return default


def safe_float(value, default=None):
    """
    Convert value to Python float, handling numpy types
    Returns default if conversion fails or value is NaN/Inf
    """
    if value is None or (isinstance(value, (float, np.floating)) and (np.isnan(value) or np.isinf(value))):
        return default

    try:
        return float(value)
    except (ValueError, TypeError, OverflowError):
        return default


def safe_str(value, default=None):
    """
    Convert value to Python str, handling numpy/pandas types
    Returns default if value is None or NaN
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default

    try:
        return str(value)
    except (ValueError, TypeError):
        return default


def safe_bool(value, default=False):
    """
    Convert value to Python bool, handling numpy types
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default

    try:
        return bool(value)
    except (ValueError, TypeError):
        return default


def convert_row_types(row_dict):
    """
    Convert all numpy/pandas types in a dictionary to Python native types
    Useful for converting DataFrame rows before database insertion

    Args:
        row_dict: Dictionary with potentially numpy/pandas typed values

    Returns:
        Dictionary with Python native types
    """
    result = {}
    for key, value in row_dict.items():
        if isinstance(value, (np.integer, pd.Int64Dtype)):
            result[key] = safe_int(value)
        elif isinstance(value, (np.floating, pd.Float64Dtype)):
            result[key] = safe_float(value)
        elif isinstance(value, (np.bool_, pd.BooleanDtype)):
            result[key] = safe_bool(value)
        elif isinstance(value, np.ndarray):
            result[key] = value.tolist()
        elif isinstance(value, (pd.Timestamp, np.datetime64)):
            result[key] = pd.to_datetime(value).to_pydatetime() if not pd.isna(value) else None
        else:
            result[key] = value

    return result


def prepare_dataframe_for_insert(df):
    """
    Prepare a pandas DataFrame for PostgreSQL insertion by converting all numpy types

    Args:
        df: pandas DataFrame

    Returns:
        DataFrame with Python native types
    """
    df_copy = df.copy()

    # Convert integer columns
    for col in df_copy.select_dtypes(include=[np.integer]).columns:
        df_copy[col] = df_copy[col].apply(safe_int)

    # Convert float columns
    for col in df_copy.select_dtypes(include=[np.floating]).columns:
        df_copy[col] = df_copy[col].apply(safe_float)

    # Convert boolean columns
    for col in df_copy.select_dtypes(include=[np.bool_]).columns:
        df_copy[col] = df_copy[col].apply(safe_bool)

    # Convert datetime columns
    for col in df_copy.select_dtypes(include=['datetime64']).columns:
        df_copy[col] = pd.to_datetime(df_copy[col])

    return df_copy
