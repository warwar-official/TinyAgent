from imports.models.base_model import BaseAPIModel
import requests

class GeminiModel(BaseAPIModel):
    def __init__(self, model_id: str, api_key: str) -> None:
        self.API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/"
        self.API_KEY = api_key
        self.MODEL_ID = model_id
    
    def make_request(self, payload: dict) -> str:
        headers = {
            'Content-Type':'application/json',
            'Accept':'application/json',
            'x-goog-api-key':self.API_KEY
        }
        response = requests.post(
            url=f"{self.API_ENDPOINT}{self.MODEL_ID}:generateContent",
            headers=headers,
            json=payload
        )
        answer = response.json()
        asnswer_message = answer.get("candidates")[0].get("content").get("parts")[0].get("text")
        return asnswer_message