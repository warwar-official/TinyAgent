class BaseEmbeddingModel:
    """
    Base class for embedding models.
    """
    API_ENDPOINT: str
    API_KEY: str
    MODEL_ID: str

    def make_request(self, text: str) -> list[float]:
        """
        Generates an embedding vector for the given text.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding vector.
        """
        raise NotImplementedError
