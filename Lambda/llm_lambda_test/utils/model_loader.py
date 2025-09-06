import os
import boto3
import yaml
from langchain_aws import ChatBedrock

class ModelLoader:
    """
    Loader for AWS Bedrock models with optional S3-based config.
    Supports a generic config structure with faiss_db, embedding_models, retriever, and llms.
    """
    def __init__(self):
        # Load config from S3 if env vars are set, else fallback to local get_config()
        config_bucket = os.environ.get("CONFIG_BUCKET")
        config_key = os.environ.get("CONFIG_KEY")
        if config_bucket and config_key:
            self.config = self._load_config_from_s3(config_bucket, config_key)
        else:
            print("CONFIG_BUCKET or CONFIG_KEY missing, using local get_config()")
            from .config_loader import get_config
            self.config = get_config()

    def _load_config_from_s3(self, bucket: str, key: str) -> dict:
        """
        Load YAML configuration file from S3.
        """
        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket=bucket, Key=key)
        yaml_content = obj["Body"].read().decode("utf-8")
        return yaml.safe_load(yaml_content)

    def get_faiss_config(self) -> dict:
        """
        Return FAISS DB configuration.
        """
        return self.config.get("faiss_db", {})

    def get_retriever_config(self) -> dict:
        """
        Return retriever configuration.
        """
        return self.config.get("retriever", {})

    def load_llm(self, **kwargs):
        """
        Load a Bedrock LLM using the 'llms.bedrock' config.
        """
        llms_config = self.config.get("llms", {})
        if "bedrock" not in llms_config:
            raise ValueError("Bedrock LLM configuration not found in config")

        model_conf = dict(llms_config["bedrock"])
        model_conf.update(kwargs)

        # Remove import_path if exists
        model_conf.pop("import_path", None)

        return ChatBedrock(**model_conf)


# if __name__ == "__main__":
#     loader = ModelLoader()
    
#     # Example: load Bedrock LLM
#     llm_model = loader.load_llm(temperature=0.5, max_output_tokens=1024)
#     print("Bedrock LLM model loaded:", llm_model)
    
#     # Example: access FAISS DB and retriever config
#     print("FAISS config:", loader.get_faiss_config())
#     print("Retriever config:", loader.get_retriever_config())
