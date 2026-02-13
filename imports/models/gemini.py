from imports.models.base_model import BaseAPIModel
import requests
import time

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
        tries = 0
        while response.status_code != 200:
            if response.status_code == 503:
                time.sleep(1)
            elif response.status_code == 429:
                time.sleep(60)
            else:
                raise Exception(f"API request failed: code {response.status_code}")
            tries += 1
            if tries > 3:
                raise Exception("API request failed")
            response = requests.post(
                url=f"{self.API_ENDPOINT}{self.MODEL_ID}:generateContent",
                headers=headers,
                json=payload
            )
        answer = response.json()
        asnswer_message = answer.get("candidates")[0].get("content").get("parts")[0].get("text")
        return asnswer_message