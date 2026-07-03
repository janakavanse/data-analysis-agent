"""Local dataframe profiling — produces a DatasetSchema of column-level
aggregate metadata only. This is the hard privacy boundary: never return or
log actual row values beyond min/max/null-count/low-cardinality samples.
"""
import pandas as pd

from domain.dataset import ColumnSchema, DatasetSchema

_MAX_DISTINCT_SAMPLE = 20
_NUMERIC_KINDS = "iuf"  # int, uint, float
_DATETIME_KIND = "M"


def profile_dataframe(df: pd.DataFrame) -> DatasetSchema:
    if df.shape[1] == 0:
        raise ValueError("Dataset has no columns — file is empty or unparseable.")

    columns: list[ColumnSchema] = []
    for col in df.columns:
        series = df[col]
        dtype = str(series.dtype)
        null_count = int(series.isna().sum())

        min_val: float | str | None = None
        max_val: float | str | None = None
        kind = series.dtype.kind
        if kind in _NUMERIC_KINDS or kind == _DATETIME_KIND:
            non_null = series.dropna()
            if len(non_null) > 0:
                raw_min = non_null.min()
                raw_max = non_null.max()
                if kind == _DATETIME_KIND:
                    min_val = str(raw_min)
                    max_val = str(raw_max)
                else:
                    min_val = raw_min.item() if hasattr(raw_min, "item") else raw_min
                    max_val = raw_max.item() if hasattr(raw_max, "item") else raw_max

        distinct_sample: list[str] | None = None
        n_distinct = series.nunique(dropna=True)
        if n_distinct <= _MAX_DISTINCT_SAMPLE:
            values = sorted(str(v) for v in series.dropna().unique().tolist())
            distinct_sample = values[:_MAX_DISTINCT_SAMPLE]

        columns.append(
            ColumnSchema(
                name=str(col),
                dtype=dtype,
                null_count=null_count,
                min=min_val,
                max=max_val,
                distinct_sample=distinct_sample,
            )
        )

    return DatasetSchema(columns=columns, row_count=int(df.shape[0]))
