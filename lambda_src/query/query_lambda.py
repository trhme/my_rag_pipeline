import os
import json
import openai
import boto3
from pinecone import Pinecone


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


openai_api_key = _read_api_key_from_secret(os.environ["OPENAI_API_SECRET_NAME"])
pinecone_api_key = _read_api_key_from_secret(os.environ["PINECONE_API_SECRET_NAME"])

# Initialize clients globally for execution container reuse
openai_client = openai.OpenAI(api_key=openai_api_key)
pc = Pinecone(api_key=pinecone_api_key)
pinecone_index = pc.Index(os.environ["PINECONE_INDEX_NAME"])

def lambda_handler(event, context):
    try:
        # Parse input payload
        body = json.loads(event.get("body", "{}")) if "body" in event else event
        user_query = body.get("query")
        
        if not user_query:
            return {"statusCode": 400, "body": json.dumps({"error": "Missing 'query' field."})}
        
        # 1. Generate Query Embedding
        embed_response = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=user_query
        )
        query_vector = embed_response.data[0].embedding
        
        # 2. Query Pinecone Vector Database
        search_results = pinecone_index.query(
            vector=query_vector,
            top_k=5,
            include_metadata=True
        )
        
        # 3. Aggregate Retrieved Context Chunks
        context_chunks = []
        for match in search_results.get("matches", []):
            if "text" in match.get("metadata", {}):
                context_chunks.append(match["metadata"]["text"])
                
        context_text = "\n---\n".join(context_chunks)
        
        # 4. Strict Fact Retrieval Generation
        system_prompt = (
            "You are a factual retrieval assistant. Answer the user's question using ONLY "
            "the provided context below. If the answer cannot be found in the context, say "
            "'Information not found.' Do not make up facts."
        )
        
        completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context:\n{context_text}\n\nQuestion: {user_query}"}
            ]
        )
        
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "answer": completion.choices[0].message.content,
                "sources_used": len(context_chunks)
            })
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }