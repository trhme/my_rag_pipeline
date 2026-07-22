import json
import os
import logging
import boto3
from pypdf import PdfReader
import openai
from pinecone import Pinecone

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _read_api_key_from_secret(secret_name: str) -> str:
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_name)
    secret_value = response.get("SecretString", "")

    if not secret_value:
        raise ValueError(f"Secret {secret_name} is empty or missing SecretString")

    try:
        secret_json = json.loads(secret_value)
    except json.JSONDecodeError:
        return secret_value

    return (
        secret_json.get("api_key")
        or secret_json.get("OPENAI_API_KEY")
        or secret_json.get("PINECONE_API_KEY")
        or ""
    )


def _download_s3_object(bucket: str, key: str) -> str:
    s3 = boto3.client("s3")
    safe_name = key.replace("/", "_")
    local_path = os.path.join("/tmp", safe_name)
    logger.info("Downloading s3://%s/%s to %s", bucket, key, local_path)
    s3.download_file(bucket, key, local_path)
    return local_path


def _extract_text_from_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        reader = PdfReader(path)
        text = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            text.append(page_text)
        return "\n\n".join(text).strip()

    with open(path, "rb") as f:
        raw = f.read()

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end].strip())
        start += chunk_size - overlap
    return [chunk for chunk in chunks if chunk]


def lambda_handler(event, context):
    logger.info("Ingestion Lambda invoked")
    logger.info("Event: %s", json.dumps(event))

    openai_api_key = _read_api_key_from_secret(os.environ["OPENAI_API_SECRET_NAME"])
    pinecone_api_key = _read_api_key_from_secret(os.environ["PINECONE_API_SECRET_NAME"])
    pinecone_index_name = os.environ.get("PINECONE_INDEX_NAME")

    if not pinecone_index_name:
        raise ValueError("PINECONE_INDEX_NAME environment variable is required")

    openai_client = openai.OpenAI(api_key=openai_api_key)
    pinecone_client = Pinecone(api_key=pinecone_api_key)
    pinecone_index = pinecone_client.Index(pinecone_index_name)

    records = event.get("Records", []) if isinstance(event, dict) else []
    processed = []
    upserted_vectors = 0

    for record in records:
        s3_info = record.get("s3", {})
        bucket = s3_info.get("bucket", {}).get("name")
        object_info = s3_info.get("object", {})
        key = object_info.get("key")

        if not bucket or not key:
            continue

        local_path = _download_s3_object(bucket, key)
        text = _extract_text_from_file(local_path)

        if not text:
            logger.warning("No text extracted from %s", key)
            continue

        chunks = _chunk_text(text)
        logger.info("Split %s into %d chunks", key, len(chunks))

        embed_resp = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=chunks,
        )

        vectors = []
        for idx, chunk_response in enumerate(embed_resp.data):
            embedding = chunk_response.embedding
            vectors.append(
                {
                    "id": f"{os.path.basename(key)}-{idx}",
                    "values": embedding,
                    "metadata": {
                        "source": key,
                        "chunk_index": idx,
                        "text": chunks[idx],
                    },
                }
            )

        if vectors:
            pinecone_index.upsert(vectors=vectors)
            upserted_vectors += len(vectors)
            processed.append(key)

    logger.info("Ingestion complete. Processed files: %s, vectors upserted: %d", processed, upserted_vectors)

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "Ingestion completed.",
                "processed_files": processed,
                "upserted_vectors": upserted_vectors,
            }
        ),
    }
