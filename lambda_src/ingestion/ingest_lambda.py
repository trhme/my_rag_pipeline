import json
import os
import boto3


def _read_api_key_from_secret(secret_name: str) -> str:
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_name)
    secret_value = response.get("SecretString", "")

    if not secret_value:
        raise ValueError(f"Secret {secret_name} is empty or missing SecretString")

    # Support either plain string secrets or JSON payloads.
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


def lambda_handler(event, context):
    """S3-triggered ingestion entrypoint for the container Lambda."""
    # Resolve API keys from Secrets Manager at runtime.
    openai_api_key = _read_api_key_from_secret(os.environ["OPENAI_API_SECRET_NAME"])
    pinecone_api_key = _read_api_key_from_secret(os.environ["PINECONE_API_SECRET_NAME"])

    records = event.get("Records", []) if isinstance(event, dict) else []

    file_keys = []
    for record in records:
        s3_info = record.get("s3", {})
        object_info = s3_info.get("object", {})
        key = object_info.get("key")
        if key:
            file_keys.append(key)

    # Placeholder response while ingestion pipeline logic is implemented.
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "Ingestion Lambda invoked.",
                "files": file_keys,
                "pinecone_index": os.getenv("PINECONE_INDEX_NAME", ""),
                "secrets_loaded": bool(openai_api_key and pinecone_api_key),
            }
        ),
    }
