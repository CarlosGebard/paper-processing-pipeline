import datetime as dt
import hashlib
import hmac
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _signing_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    key = ("AWS4" + secret_key).encode("utf-8")
    date_key = hmac.new(key, date_stamp.encode("utf-8"), hashlib.sha256).digest()
    region_key = hmac.new(date_key, region.encode("utf-8"), hashlib.sha256).digest()
    service_key = hmac.new(region_key, service.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()


def _canonical_key(key: str) -> str:
    return "/".join(urllib.parse.quote(part, safe="") for part in key.split("/"))


class ObjectStorage:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, region: str):
        self.endpoint = endpoint.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region

    def head_object(self, bucket: str, key: str) -> dict[str, str] | None:
        try:
            with self._request("HEAD", bucket, key) as response:
                return {name.lower(): value for name, value in response.headers.items()}
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def put_file(self, bucket: str, key: str, path: Path, metadata: dict[str, str] | None = None) -> bool:
        if not path.is_file():
            raise SystemExit(f"Not a file: {path}")
        headers = {"content-type": mimetypes.guess_type(path.name)[0] or "application/octet-stream"}
        for name, value in (metadata or {}).items():
            headers[f"x-amz-meta-{name.lower()}"] = value
        existing = self.head_object(bucket, key)
        sha256_hex = (metadata or {}).get("sha256")
        if existing and sha256_hex and existing.get("x-amz-meta-sha256") == sha256_hex:
            return False
        with self._request("PUT", bucket, key, body=path.read_bytes(), headers=headers):
            return True

    def _request(
        self,
        method: str,
        bucket: str,
        key: str | None = None,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
    ):
        parsed = urllib.parse.urlparse(self.endpoint)
        if not parsed.scheme or not parsed.netloc:
            raise SystemExit(f"Invalid S3 endpoint: {self.endpoint}")

        payload_hash = hashlib.sha256(body).hexdigest() if body else EMPTY_SHA256
        path = f"/{urllib.parse.quote(bucket, safe='')}"
        if key:
            path = f"{path}/{_canonical_key(key)}"

        now = dt.datetime.now(dt.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        service = "s3"
        scope = f"{date_stamp}/{self.region}/{service}/aws4_request"

        request_headers = {
            "host": parsed.netloc,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        for name, value in (headers or {}).items():
            request_headers[name.lower()] = value

        signed_header_names = sorted(request_headers)
        canonical_headers = "".join(f"{name}:{request_headers[name]}\n" for name in signed_header_names)
        signed_headers = ";".join(signed_header_names)
        canonical_request = "\n".join([method, path, "", canonical_headers, signed_headers, payload_hash])
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signature = hmac.new(
            _signing_key(self.secret_key, date_stamp, self.region, service),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        authorization = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self.access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )

        url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))
        request = urllib.request.Request(url, data=body if body else None, method=method)
        for name, value in request_headers.items():
            request.add_header(name, value)
        request.add_header("authorization", authorization)
        return urllib.request.urlopen(request, timeout=30)
