import os

import boto3

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "fire-dolphin")
DO_SPACES_ENDPOINT = os.getenv(
    "DO_SPACES_ENDPOINT", f"https://{AWS_REGION}.digitaloceanspaces.com"
)


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=DO_SPACES_ENDPOINT,
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )
