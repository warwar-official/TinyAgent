from imports.models.embeddings.base_model import BaseEmbeddingModel
import requests
import time

class LMStudioEmbeddingModel(BaseEmbeddingModel):
    """
    Embedding model implementation for LM Studio (OpenAI-compatible API).
    """
    def __init__(self):
        self.API_ENDPOINT = "http://192.168.50.212:1234/v1/embeddings"
        self.API_KEY = "" # Empty as per requirements
        self.MODEL_ID = "text-embedding-nomic-embed-text-v1.5"

    def make_request(self, text: str) -> list[float]:
        """
        Generates an embedding vector for the given text using LM Studio.
        """
        headers = {
            "Content-Type": "application/json"
        }
        # Payload structure for OpenAI-compatible embeddings API
        payload = {
            "input": text,
            "model": self.MODEL_ID
        }

        try:
            response = requests.post(
                url=self.API_ENDPOINT,
                headers=headers,
                json=payload
            )
            
            # Simple retry logic for 503 or specific errors if needed, 
            # mirroring the Gemini implementation style slightly but keeping it simple for local.
             
            if response.status_code != 200:
                 raise Exception(f"Embedding API request failed: code {response.status_code}, body: {response.text}")

            result = response.json()
            
            # OpenAI format: {'data': [{'embedding': [...], ...}], ...}
            embedding = result['data'][0]['embedding']
            return embedding

        except Exception as e:
            print(f"Error generating embedding: {e}")
            raise e
