import logging

from sqlalchemy.orm import Session

from datachat.db.models import DatasetQueryRow, DatasetRow, DatasetUploadRow, UploadRow
from datachat.llm.client import get_llm_client
from datachat.pipeline.csv_reader import build_query_context, get_upload_path

logger = logging.getLogger(__name__)

MAX_SAMPLE_ROWS_PER_FILE = 5


def _build_dataset_context(uploads: list[UploadRow], upload_dir: str) -> str:
    """Build a multi-file context block: schema summary + small sample per file."""
    blocks = []
    for i, upload in enumerate(uploads, start=1):
        try:
            ctx = build_query_context(
                str(get_upload_path(upload_dir, upload.filename)),
                max_rows=MAX_SAMPLE_ROWS_PER_FILE,
            )
        except Exception as exc:
            logger.warning("Could not read upload %s: %s", upload.id, exc)
            ctx = f"(could not read file: {exc})"

        blocks.append(
            f"--- File {i}: {upload.original_filename} ---\n"
            f"Rows: {upload.row_count}\n"
            f"{ctx}"
        )
    return "\n\n".join(blocks)


def run_dataset_query(
    dataset_id: str,
    question: str,
    session: Session,
    upload_dir: str,
) -> DatasetQueryRow:
    dataset = session.get(DatasetRow, dataset_id)
    if dataset is None:
        raise ValueError(f"Dataset not found: {dataset_id}")

    join_rows = (
        session.query(DatasetUploadRow)
        .filter(DatasetUploadRow.dataset_id == dataset_id)
        .all()
    )
    if not join_rows:
        raise ValueError("Dataset has no uploaded files. Add at least one CSV first.")

    uploads = [session.get(UploadRow, jr.upload_id) for jr in join_rows]
    uploads = [u for u in uploads if u is not None]

    context = _build_dataset_context(uploads, upload_dir)
    provider, is_stub = get_llm_client()

    prompt = (
        f"<node:query>\n"
        f"You are a data analyst with access to {len(uploads)} CSV file(s) described below.\n"
        f"Answer the user's question by reasoning across all files. "
        f"If data from multiple files is relevant, synthesise it into a single coherent answer.\n\n"
        f"{context}\n\n"
        f"Question: {question}\n\n"
        f"Provide a clear, concise answer."
    )

    logger.info(
        "Running dataset query dataset_id=%s files=%d is_stub=%s",
        dataset_id, len(uploads), is_stub,
    )
    result = provider.generate(prompt)

    qrow = DatasetQueryRow(
        dataset_id=dataset_id,
        question=question,
        answer=result.text,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
    )
    session.add(qrow)
    session.flush()
    return qrow
