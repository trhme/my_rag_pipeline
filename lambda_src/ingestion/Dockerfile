FROM public.ecr.aws/lambda/python:3.14

COPY ingest_lambda.py ${LAMBDA_TASK_ROOT}/

RUN python -m pip install --no-cache-dir \
    pypdf \
    tiktoken \
    openai \
    pinecone

# Allow override via --entrypoint while keeping Lambda handler as default
ENTRYPOINT []
CMD ["python", "-m", "awslambdaric", "ingest_lambda.lambda_handler"]
