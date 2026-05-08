import logging

from src.config.s3_config import S3_BUCKET_NAME, get_s3_client

logger = logging.getLogger(__name__)


def build_s3_key(owner: str, repo_name: str, file_path: str) -> str:
    return f"repos/{owner}/{repo_name}/{file_path}"


def upload_file(content: str, s3_key: str) -> str:
    """Upload UTF-8 text content to S3 and return the key."""
    client = get_s3_client()
    client.put_object(
        Bucket=S3_BUCKET_NAME,
        Key=s3_key,
        Body=content.encode("utf-8"),
        ContentType="text/plain; charset=utf-8",
    )
    return s3_key


def download_file(s3_key: str) -> str:
    """Download text content from S3."""
    client = get_s3_client()
    response = client.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
    return response["Body"].read().decode("utf-8")
