# Serverless RAG Pipeline :rocket:

This repository implements a small serverless retrieval-augmented generation (RAG) pipeline using AWS Lambda, Pinecone, and OpenAI. The system ingests documents from S3, creates embeddings with OpenAI, stores vectors in Pinecone, and answers queries by retrieving relevant chunks and asking OpenAI to compose a factual response.

Quick links:
- `pipeline_stack.py` — CDK stack that provisions the S3 bucket, two Lambdas, and S3 notifications.
- `lambda_src/ingestion/ingest_lambda.py` — Ingestion Lambda that turns S3 objects into vectors and upserts them into Pinecone. :package:
- `lambda_src/query/query_lambda.py` — Query Lambda that searches Pinecone and uses OpenAI to generate answers. :mag_right:
- `.github/workflows/install-deps.yml` — CI workflow that builds Lambda dependencies and synthesizes (and can deploy) the CDK app. :gear:

---

## Architecture Overview :blue_book:

- Users upload documents (text, PDF) to the S3 source bucket (created by `pipeline_stack.py`).
- S3 object-created notifications trigger the **Ingest Lambda** which:
  - downloads the object
  - extracts text (PDF/text handling)
  - chunks the text
  - calls OpenAI to create embeddings
  - upserts vectors into a Pinecone index with metadata (source, chunk_index, text)
- The **Query Lambda** accepts a user query, embeds the query with OpenAI, queries Pinecone for nearest vectors, then passes the retrieved chunked context to OpenAI to produce a concise, factual answer.

This separation keeps ingestion (batch/stream) and query (retrieval + LLM) concerns isolated. :handshake:

---

## Ingest Lambda (what it does) :inbox_tray:

Location: `lambda_src/ingestion/ingest_lambda.py`

- Trigger: S3 Object Created event.
- Steps:
  1. Read OpenAI and Pinecone API keys from AWS Secrets Manager (secret names configured in CDK env).
  2. Download the S3 object to `/tmp` and extract text (PDF pages are handled via `pypdf`).
  3. Chunk text (default ~800 chars with 100 overlap).
  4. Call OpenAI embeddings API (`text-embedding-3-small`) for the chunks.
  5. Upsert vectors into Pinecone with metadata including `source` and `chunk_index`.

Notes:
- The ingestion Lambda is optimized for single-file events, but you can run a separate backfill to index existing S3 content (see Backfill below). :floppy_disk:

---

## Query Lambda (what it does) :mag:

Location: `lambda_src/query/query_lambda.py`

- Accepts requests containing a `query` string (HTTP API or direct invocation).
- Steps:
  1. Embed the user query using OpenAI (`text-embedding-3-small`).
  2. Query Pinecone for the top-k matches (the code uses `top_k=5`).
  3. Aggregate the matched chunk texts into a single context payload.
  4. Call OpenAI chat/completion (configured in the code as `gpt-4o-mini`) with a strict system prompt that instructs the model to answer only from the provided context.
  5. Return the answer and number of sources used.

This flow enables multi-document answers because Pinecone returns the most relevant chunks across all ingested files. :sparkles:

---

## Why Pinecone + OpenAI? :bulb:

- OpenAI produces high-quality vector embeddings that capture semantic meaning.
- Pinecone provides a fast, scalable vector database for kNN search.
- Combining them lets you store embeddings once and perform low-latency retrievals for downstream LLM prompts.

Design notes:
- Your code currently embeds with `text-embedding-3-small` (dimension 1536). When creating a Pinecone index, set `dimension=1536` and `metric=cosine` for best results.
- The system uses OpenAI for both embeddings and final answer generation (retrieval-augmented generation). :robot_face:

---

## Backfill / Bulk Ingest (index existing S3 documents) :warning:

If you have thousands of existing documents in S3, the S3-triggered Lambda only processes new uploads. To index historical content you should run a backfill job. Options:

- Local/CLI script: a Python script that lists `s3.list_objects_v2`, downloads each file, and calls the same chunk/embed/upsert logic (quick to run but rate-limited by your machine and API quotas).
- AWS-native: use Step Functions + Lambdas or an ECS/Fargate job to paginate S3 and process objects in parallel with retries and batching.

Practical tips:
- Batch your embedding calls (multiple chunks per request) up to the model and token limits.
- Add exponential backoff + retries for OpenAI 429s.
- Monitor and throttle to stay within OpenAI quota/billing limits. :money_with_wings:

---

## Secrets & Configuration :lock:

- `OpenAI` API key and `Pinecone` API key are read from Secrets Manager. The CDK stack expects two secrets by name (see `pipeline_stack.py`):
  - `my/rag/openai-api-key` (or whatever name you set in CDK)
  - `my/rag/pinecone-api-key`
- The Pinecone index name is supplied via the `PINECONE_INDEX_NAME` environment variable in `pipeline_stack.py` (replace the placeholder `YOUR_PINECONE_INDEX_NAME`).

CI / GitHub Actions:
- The workflow at `.github/workflows/install-deps.yml` installs Lambda dependencies on the runner and can run `cdk synth`.
- The deploy job requires `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` stored as repository secrets if you want CI-driven deploys. :gear:

---

## Troubleshooting :wrench:

- `ModuleNotFoundError` for binary extensions (e.g., `pydantic_core._pydantic_core`) can occur if you build packages on macOS and then zip them for Linux Lambda runtime. The CI workflow installs packages on the GitHub runner (Linux) and avoids committing `site-packages` into git.
- `RateLimitError` / `insufficient_quota` from OpenAI indicates billing/quota limits — check your OpenAI billing dashboard or add retries and reduce batch sizes.
- If Pinecone queries return wrong-sized vectors, verify the index `dimension` matches the embedding model (1536 for `text-embedding-3-small`).

---

## Next steps & improvements :rocket:

- Add a backfill job (Step Functions or CLI script) to index historical S3 objects.
- Add logging/metrics around embedding usage and Pinecone upserts for observability.
- Consider adding a rate-limited async worker (ECS/Fargate) for heavy backfills.

If you want, I can:
- add a backfill script and a CDK task to run it,
- update `pipeline_stack.py` to accept the Pinecone index name from a CDK context/SSM param, or
- add more robust retry/backoff logic to `ingest_lambda.py`.

---

Happy to update this README with any extra detail you want (deploy commands, example queries, or a sample backfill script). :sparkles: