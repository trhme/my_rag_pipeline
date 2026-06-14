from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_s3 as s3,
    aws_lambda as _lambda,
    aws_iam as iam,
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

        # 2. Shared Config Variables (Replace with secret references in production)
        pinecone_api_key = "YOUR_PINECONE_API_KEY"
        pinecone_index = "YOUR_PINECONE_INDEX_NAME"
        openai_api_key = "YOUR_OPENAI_API_KEY"

        # 3. Docker-based Ingestion Lambda (Handles dependencies > 250MB limit)
        ingest_lambda = _lambda.DockerImageFunction(
            self, "IngestionLambda",
            code=_lambda.DockerImageCode.from_image_asset("./lambda_src/ingestion"),
            timeout=Duration.minutes(5),
            memory_size=1024,
            environment={
                "PINECONE_API_KEY": pinecone_api_key,
                "PINECONE_INDEX_NAME": pinecone_index,
                "OPENAI_API_KEY": openai_api_key
            }
        )

        # Grant Ingestion Lambda explicit permissions to read from S3 (Least Privilege)
        source_bucket.grant_read(ingest_lambda)

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
                "PINECONE_API_KEY": pinecone_api_key,
                "PINECONE_INDEX_NAME": pinecone_index,
                "OPENAI_API_KEY": openai_api_key
            }
        )
