FROM public.ecr.aws/lambda/python:3.14

# Copy application files
COPY ingest_lambda.py ${LAMBDA_TASK_ROOT}

# Install pipeline dependencies directly into the AWS task space
RUN pip install --no-cache-dir \
    pypdf \
    tiktoken \
    openai \
    pinecone-client

# Set the handler entry point
CMD [ "ingest_lambda.lambda_handler" ]
