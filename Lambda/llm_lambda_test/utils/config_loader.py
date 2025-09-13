
import os
import yaml
_CONFIG_CACHE = None
def get_config():
    """
    Loads and returns the config dict, from S3 if CONFIG_BUCKET and CONFIG_KEY env vars are set, else from local config.yaml.
    Caches the config for reuse.
    """
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    bucket = os.environ.get('CONFIG_BUCKET')
    key = os.environ.get('CONFIG_KEY')
    if bucket and key:
        try:
            import boto3
            session = boto3.session.Session()
            s3 = session.client('s3')
            response = s3.get_object(Bucket=bucket, Key=key)
            content = response['Body'].read().decode('utf-8')
            _CONFIG_CACHE = yaml.safe_load(content)
        except Exception as e:
            print(f"Error loading config from S3: {e}")
            raise
    return _CONFIG_CACHE
