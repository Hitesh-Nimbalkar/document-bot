# UI-related Lambda route handler for fetching models configuration
import os
import time
import json
import boto3
import yaml
from utils.logger import CustomLogger
from Lambda.llm_lambda_test.lambda_handler import make_response
logger = CustomLogger(__name__)
s3 = boto3.client("s3")
_MODELS_CACHE = {"ts": 0, "data": None, "etag": None}
CACHE_TTL_SECONDS = int(os.getenv("MODELS_CONFIG_CACHE_TTL", "300"))  # 5 min default
MODELS_CONFIG_BUCKET = os.getenv("MODELS_CONFIG_BUCKET") or os.getenv("CONFIG_BUCKET")
MODELS_CONFIG_KEY = os.getenv("MODELS_CONFIG_KEY", "config/models.yaml")

def _load_models_config(force: bool = False):
    """Internal helper to load and cache the models config from S3.
    Returns raw dict loaded from YAML.
    """
    now = time.time()
    if not force and _MODELS_CACHE["data"] and (now - _MODELS_CACHE["ts"]) < CACHE_TTL_SECONDS:
        return _MODELS_CACHE["data"], False
    if not MODELS_CONFIG_BUCKET:
        raise RuntimeError("MODELS_CONFIG_BUCKET env var not set")
    extra = {}
    if _MODELS_CACHE["etag"]:
        extra["IfNoneMatch"] = _MODELS_CACHE["etag"]
    try:
        # Try conditional get using ETag for minimal data transfer
        response = s3.get_object(Bucket=MODELS_CONFIG_BUCKET, Key=MODELS_CONFIG_KEY, **({} if force else extra))
        body = response["Body"].read().decode("utf-8")
        data = yaml.safe_load(body) or {}
        _MODELS_CACHE.update(ts=now, data=data, etag=response.get("ETag"))
        return data, True
    except s3.exceptions.ClientError as e:  # type: ignore[attr-defined]
        code = e.response["Error"].get("Code")
        if code == "304":  # Not Modified
            _MODELS_CACHE["ts"] = now
            return _MODELS_CACHE["data"], False
        raise

def handle_get_models_config(event, payload):
    """Handles /get_models_config route:
    - Fetches and returns the models registry (embeddings, rerankers, llms)
    Query params / payload options:
      force_reload: bool or "1" to bypass cache
    """
    force_flag = False
    if isinstance(payload, dict):
        force_flag = str(payload.get("force_reload", "")).lower() in ("1", "true", "yes")
    try:
        data, refreshed = _load_models_config(force=force_flag)
        meta = {
            "refreshed": refreshed,
            "cache_ttl": CACHE_TTL_SECONDS,
            "timestamp": int(time.time())
        }
        # Flatten top-level version and group sections only
        filtered = {
            k: v for k, v in data.items() if k in ("version", "embeddings", "rerankers", "llms")
        }
        return make_response(200, {"models": filtered, "meta": meta})
    except Exception as e:
        logger.error(f"\U0001F4A5 Error fetching models config: {e}", exc_info=True)
        return make_response(500, f"Error fetching models config: {str(e)}")

