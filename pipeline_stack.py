from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_s3 as s3,
    aws_lambda as _lambda,
    aws_secretsmanager as secretsmanager,
    aws_s3_notifications as s3n
)
from constructs import Construct

class ServerlessRagPipelineStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. Define Secure S3 Source Bucket (Text & PDFs Only)
        source_bucket = s3.Bucket(
            self, "RagSourceBucket",
            bucket_name="my-secure-rag-source-bucket-2026", # Change to unique name
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY, # Change to RETAIN for production
            auto_delete_objects=True
        )

        # 2. Shared Config Variables
        pinecone_index = "YOUR_PINECONE_INDEX_NAME"

        # Secrets should already exist in AWS Secrets Manager.
        # Expected secret value can be either a plain string key or JSON, for example:
        # {"api_key": "..."}
        pinecone_api_secret = secretsmanager.Secret.from_secret_name_v2(
            self,
            "PineconeApiSecret",
            "my/rag/pinecone-api-key",
        )
        openai_api_secret = secretsmanager.Secret.from_secret_name_v2(
            self,
            "OpenAiApiSecret",
            "my/rag/openai-api-key",
        )

        # 3. Ingestion Lambda as a normal zip-based function (simpler than Docker)
        ingest_lambda = _lambda.Function(
            self, "IngestionLambda",
            runtime=_lambda.Runtime.PYTHON_3_14,
            handler="ingest_lambda.lambda_handler",
            code=_lambda.Code.from_asset("./lambda_src/ingestion"),
            timeout=Duration.minutes(5),
            memory_size=1024,
            environment={
                "PINECONE_API_SECRET_NAME": pinecone_api_secret.secret_name,
                "PINECONE_INDEX_NAME": pinecone_index,
                "OPENAI_API_SECRET_NAME": openai_api_secret.secret_name,
            }
        )

        # Grant Ingestion Lambda explicit permissions to read from S3 (Least Privilege)
        source_bucket.grant_read(ingest_lambda)
        pinecone_api_secret.grant_read(ingest_lambda)
        openai_api_secret.grant_read(ingest_lambda)

        # 4. Attach S3 Event Trigger to Ingestion Lambda
        source_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(ingest_lambda)
        )

        # 5. Zip-based Query/Chat Lambda (No heavy dependencies, pure SDK client calls)
        query_lambda = _lambda.Function(
            self, "QueryLambda",
            runtime=_lambda.Runtime.PYTHON_3_14,
            handler="query_lambda.lambda_handler",
            code=_lambda.Code.from_asset("./lambda_src/query"),
            timeout=Duration.seconds(30),
            memory_size=512,
            environment={
                "PINECONE_API_SECRET_NAME": pinecone_api_secret.secret_name,
                "PINECONE_INDEX_NAME": pinecone_index,
                "OPENAI_API_SECRET_NAME": openai_api_secret.secret_name,
            }
        )

        pinecone_api_secret.grant_read(query_lambda)
        openai_api_secret.grant_read(query_lambda)
