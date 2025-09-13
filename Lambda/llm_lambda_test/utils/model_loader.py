import os
import boto3
import yaml
import importlib
import json

class ModelLoader:
    """
    Generic Model Loader with AWS Secrets Manager integration.
    Config (fetched from S3) contains model details + hardcoded secret_name.
    """

    def __init__(self):
        self.secrets_client = boto3.client("secretsmanager")

        # Load config from S3 if env vars are set, else fallback to local
        config_bucket = os.environ.get("CONFIG_BUCKET")
        config_key = os.environ.get("CONFIG_KEY")
        if config_bucket and config_key:
            self.config = self._load_config_from_s3(config_bucket, config_key)
        else:
            print("CONFIG_BUCKET or CONFIG_KEY missing, using local get_config()")
            from .config_loader import get_config
            self.config = get_config()

    def _load_config_from_s3(self, bucket: str, key: str) -> dict:
        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket=bucket, Key=key)
        yaml_content = obj["Body"].read().decode("utf-8")
        return yaml.safe_load(yaml_content)

    def _dynamic_import(self, import_path: str):
        module_name, class_name = import_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, class_name)

    def _get_secret(self, secret_name: str) -> str:
        """
        Fetch a secret value from AWS Secrets Manager.
        """
        response = self.secrets_client.get_secret_value(SecretId=secret_name)
        if "SecretString" in response:
            return response["SecretString"]
        else:
            return response["SecretBinary"].decode("utf-8")

    def _prepare_model_conf(self, model_conf: dict) -> dict:
        """
        Inject secrets into model config if secret_name is provided.
        """
        if "secret_name" in model_conf:
            secret_value = self._get_secret(model_conf["secret_name"])

            # If secret is JSON (e.g. {"api_key": "..."}), parse it
            try:
                secret_dict = json.loads(secret_value)
                model_conf.update(secret_dict)
            except json.JSONDecodeError:
                model_conf["api_key"] = secret_value

            model_conf.pop("secret_name", None)

        return model_conf

    # def load_embedding_model(self, name: str = None, **kwargs):
    #     embeddings_config = self.config.get("embedding_models", {})
    #     if not embeddings_config:
    #         raise ValueError("No embedding models found in config")

    #     model_key = name or next(iter(embeddings_config))
    #     model_conf = dict(embeddings_config[model_key])
    #     model_conf.update(kwargs)

    #     import_path = model_conf.pop("import_path")
    #     cls = self._dynamic_import(import_path)

    #     model_conf = self._prepare_model_conf(model_conf)
    #     return cls(**model_conf)

    def load_embedding_model(self, name: str = None, **kwargs):
        """
        For now: always return a Bedrock embedding model client.
        Keeps structure the same so rest of pipeline works unchanged.
        """
        try:
            import boto3
            bedrock = boto3.client(service_name="bedrock-runtime")
            
            class BedrockEmbeddingWrapper:
                def __init__(self, client, model_id="amazon.titan-embed-text-v1", **kwargs):
                    self.client = client
                    self.model_id = model_id

                def embed(self, text: str) -> list[float]:
                    response = self.client.invoke_model(
                        modelId=self.model_id,
                        body=json.dumps({"inputText": text})
                    )
                    result = json.loads(response["body"].read())
                    return result["embedding"]  # adjust if Bedrock response differs

            # ✅ Always return Bedrock wrapper (ignoring config.yaml for embeddings)
            return BedrockEmbeddingWrapper(bedrock, **kwargs)

        except Exception as e:
            raise RuntimeError(f"Failed to load Bedrock embedding model: {e}")


    def load_llm(self, name: str = None, **kwargs):
        llms_config = self.config.get("llms", {})
        if not llms_config:
            raise ValueError("No LLMs found in config")

        model_key = name or next(iter(llms_config))
        model_conf = dict(llms_config[model_key])
        model_conf.update(kwargs)

        import_path = model_conf.pop("import_path")
        cls = self._dynamic_import(import_path)

        model_conf = self._prepare_model_conf(model_conf)
        return cls(**model_conf)
