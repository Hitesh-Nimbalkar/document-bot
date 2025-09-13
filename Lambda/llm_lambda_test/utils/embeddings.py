def split_into_chunks(text: str, chunk_size: int = 500) -> list[str]:
    """
    Split text into chunks of ~chunk_size words.
    """
    words = text.split()
    return [" ".join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]


from utils.model_loader import ModelLoader

# Initialize loader once
_loader = ModelLoader()
_embedding_model = None

def get_embedding_model():
    """
    Always load the Bedrock embedding model.
    Keeps same function signature, so rest of code is unchanged.
    """
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = _loader.load_embedding_model()
    return _embedding_model

def get_embeddings(text: str, model_name: str = None) -> list[float]:
    """
    Generate embeddings using Bedrock (ignores model_name for now).
    Pipeline can still pass model_name, but it's ignored.
    """
    model = get_embedding_model()
    return model.embed(text)
