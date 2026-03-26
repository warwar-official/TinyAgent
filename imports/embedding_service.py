from fastembed import TextEmbedding
from fastembed.common.model_description import PoolingType, ModelSource
import os
import numpy as np

class EmbeddingService:
    _instance = None

    def __init__(self, emb_model_name: str, models_cache_path: str):
        if EmbeddingService._instance is not None:
            raise Exception("EmbeddingService is a singleton! Use get_instance().")
            
        os.makedirs(models_cache_path, exist_ok=True)
        
        custom_model_name = f"{emb_model_name}-custom"
        try:
            # Find the model in fastembed's list to preserve the correct sources, dim, and additional_files
            supported = next((m for m in TextEmbedding.list_supported_models() if m["model"] == emb_model_name), None)
            if supported:
                TextEmbedding.add_custom_model(
                    model=custom_model_name,
                    pooling=PoolingType.MEAN,
                    normalization=True,
                    sources=ModelSource(**supported["sources"]),
                    dim=supported["dim"],
                    model_file="model.onnx",
                    additional_files=supported.get("additional_files")
                )
            else:
                # Fallback
                TextEmbedding.add_custom_model(
                    model=custom_model_name,
                    pooling=PoolingType.MEAN,
                    normalization=True,
                    sources=ModelSource(hf=emb_model_name),
                    dim=1024,
                    model_file="model.onnx"
                )
        except ValueError:
            pass # Already registered

        self.embedding_model = TextEmbedding(
            model_name=custom_model_name,
            cache_dir=models_cache_path
        )
        
        # Determine vector size
        sample_vec = list(self.embedding_model.embed(["test"]))[0]
        self.vector_size = len(sample_vec)
        EmbeddingService._instance = self

    @classmethod
    def get_instance(cls, emb_model_name: str = None, models_cache_path: str = None) -> 'EmbeddingService':
        if cls._instance is None:
            if not emb_model_name or not models_cache_path:
                raise ValueError("EmbeddingService must be initialized with arguments first.")
            cls(emb_model_name, models_cache_path)
        return cls._instance

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        """Returns a list of dense numpy arrays for the given texts."""
        return list(self.embedding_model.embed(texts))
    
    def embed_single(self, text: str) -> list[float]:
        """Returns a single embedding vector as a standard Python list of floats."""
        return self.embed([text])[0].tolist()

    def get_vector_size(self) -> int:
        return self.vector_size
