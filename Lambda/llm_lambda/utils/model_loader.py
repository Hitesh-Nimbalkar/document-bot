
import os
import importlib
from .config_loader import get_config
# Import secret fetcher
from .secret import get_secret

class ModelLoader:
    """
    Generic model loader for any model type/provider defined in config.yaml.
    """
    def __init__(self):
        self.config = get_config()
    def _get_api_key(self, provider):
        """
        Fetch API key for a provider using the secret name from environment variable.
        E.g., for provider 'google', looks for 'GOOGLE_API_KEY_SECRET'.
        """
        env_var = f"{provider.upper()}_API_KEY_SECRET"
        return get_secret(env_var)
    def load_model(self, model_type: str, provider: str = None, **kwargs):
        """
        Generic loader for any model type/provider defined in config.yaml.
        model_type: e.g. 'llms', 'embedding_models', etc.
        provider: provider key in config (optional, else use default or first)
        kwargs: override config values
        """
        # Import all possible model classes up front
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
        except ImportError:
            ChatGoogleGenerativeAI = None
            GoogleGenerativeAIEmbeddings = None
        try:
            from langchain_groq import ChatGroq
        except ImportError:
            ChatGroq = None
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            ChatOpenAI = None
        try:
            from langchain_aws import ChatBedrock
        except ImportError:
            ChatBedrock = None
        block = self.config.get(model_type)
        if not block:
            raise ValueError(f"Model type '{model_type}' not found in config")
        if provider is None:
            provider = os.getenv(f"{model_type.upper()}_PROVIDER") or next(iter(block))
        if provider not in block:
            raise ValueError(f"Provider '{provider}' not found for model type '{model_type}' in config")
        model_conf = block[provider]
        # Optionally allow import path in config, else use if-else logic
        import_path = model_conf.get("import_path")
        model_class = None
        if import_path:
            module_name, class_name = import_path.rsplit('.', 1)
            module = importlib.import_module(module_name)
            model_class = getattr(module, class_name)
        else:
            # Use explicit if-else for known providers
            if model_type == "llms" and provider == "google" and ChatGoogleGenerativeAI:
                model_class = ChatGoogleGenerativeAI
            elif model_type == "llms" and provider == "groq" and ChatGroq:
                model_class = ChatGroq
            elif model_type == "llms" and provider == "openai" and ChatOpenAI:
                model_class = ChatOpenAI
            elif model_type == "llms" and provider == "bedrock" and ChatBedrock:
                model_class = ChatBedrock
            elif model_type == "embedding_models" and provider == "google" and GoogleGenerativeAIEmbeddings:
                model_class = GoogleGenerativeAIEmbeddings
            else:
                raise ValueError(f"No model class found for model type '{model_type}' and provider '{provider}'")
        # Merge config and kwargs
        params = dict(model_conf)
        params.update(kwargs)
        # Inject API key if needed
        for key in ["api_key", "api_token"]:
            if key in params and not params[key]:
                params[key] = self._get_api_key(provider)
        # Remove import_path from params
        params.pop("import_path", None)
        return model_class(**params)

if __name__ == "__main__":
    # Set up environment variables for secret names (for local testing/demo)
    os.environ["GOOGLE_API_KEY_SECRET"] = "google-api-key-secret-name"
    os.environ["GROQ_API_KEY_SECRET"] = "groq-api-key-secret-name"
    os.environ["OPENAI_API_KEY_SECRET"] = "openai-api-key-secret-name"
    os.environ["BEDROCK_API_KEY_SECRET"] = "bedrock-api-key-secret-name"
    loader = ModelLoader()
    # Example: Load a Google embedding model (API key will be fetched from secret)
    embedding_model = loader.load_model("embedding_models", provider="google")
    print("Embedding model loaded:", embedding_model)
    # Example: Load a Groq LLM model with custom parameters (API key from secret)
    llm_model = loader.load_model("llms", provider="groq", temperature=0.5, max_output_tokens=1024)
    print("LLM model loaded:", llm_model)
#   # Example: Load a Google embedding model
#   embedding_model = loader.load_model("embedding_models", provider="google")
#   print("Embedding model loaded:", embedding_model)
#   # Example: Load a Groq LLM model with custom parameters
#   llm_model = loader.load_model("llms", provider="groq", temperature=0.5, max_output_tokens=1024)
#   print("LLM model loaded:", llm_model)
