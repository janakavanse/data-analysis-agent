from pydantic import BaseModel


class ColumnSchema(BaseModel):
    name: str
    dtype: str
    null_count: int
    min: float | str | None = None
    max: float | str | None = None
    distinct_sample: list[str] | None = None


class DatasetSchema(BaseModel):
    columns: list[ColumnSchema]
    row_count: int


class DatasetResponse(BaseModel):
    dataset_id: str
    original_filename: str
    file_type: str
    row_count: int
    column_count: int
    schema: list[ColumnSchema]
