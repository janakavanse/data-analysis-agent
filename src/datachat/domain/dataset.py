from datetime import datetime
from pydantic import BaseModel


class DatasetCreate(BaseModel):
    name: str


class Dataset(BaseModel):
    id: str
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetQuery(BaseModel):
    id: str
    dataset_id: str
    question: str
    answer: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetQueryCreate(BaseModel):
    question: str
