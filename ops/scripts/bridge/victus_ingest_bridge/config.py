import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class BridgeConfig:
    pg_dsn: str
    redis_url: str
    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str = "victus-corpus"
    aws_region: str = "us-east-1"


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required env: {name}")
    return value


def load_config() -> BridgeConfig:
    config = BridgeConfig(
        pg_dsn=_required_env("VICTUS_PG_DSN"),
        redis_url=os.environ.get("VICTUS_REDIS_URL", "redis://redis:6379/0"),
        s3_endpoint=os.environ.get("VICTUS_S3_ENDPOINT", "http://seaweedfs:8333"),
        s3_access_key=_required_env("VICTUS_S3_ACCESS_KEY"),
        s3_secret_key=_required_env("VICTUS_S3_SECRET_KEY"),
        s3_bucket=os.environ.get("VICTUS_S3_BUCKET", "victus-corpus"),
        aws_region=os.environ.get("VICTUS_AWS_REGION", "us-east-1"),
    )
    parsed = urlparse(config.redis_url)
    if parsed.scheme != "redis":
        raise SystemExit("VICTUS_REDIS_URL must use redis://")
    return config
