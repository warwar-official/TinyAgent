from __future__ import annotations
import json
import urllib.request
import urllib.error
import os
import time
from imports.history_manager import HistoryRecord
from dataclasses import dataclass


@dataclass
class Model:
    provider: str
    model_id: str
    api_key_name: str | None
    def __init__(self, provider: str, model_id: str, api_key_name: str | None):
        self.provider = provider
        self.model_id = model_id
        self.api_key_name = api_key_name

class ProvidersManager:
    def __init__(self, providers: list[dict]):
        self.providers_dict = {p["name"]: p for p in providers}

    def _render_google_compatible_payload(self, payload: list[HistoryRecord]) -> dict:
        contents = []
        for record in payload:
            role = "user" if record.role.lower() in ["user", "tool"] else "model"
            contents.append({
                "role": role,
                "parts": [{"text": record.message}]
            })
        return {"contents": contents}

    def _render_openai_compatible_payload(self, model_id: str, payload: list[HistoryRecord]) -> dict:
        messages = []
        for record in payload:
            role = "user" if record.role.lower() in ["user", "human"] else "assistant"
            if record.role.lower() == "system":
                role = "system"
            messages.append({
                "role": role,
                "content": record.message
            })
        return {
            "model": model_id,
            "messages": messages
        }

    def _render_payload(self, structure: str, model_id: str, payload: list[HistoryRecord]) -> dict:
        if structure == "google-compatible":
            return self._render_google_compatible_payload(payload)
        elif structure == "openai-compatible":
            return self._render_openai_compatible_payload(model_id, payload)
        else:
            raise ValueError(f"Unknown structure: {structure}")

    def _get_api_key(self, api_key_name: str | None) -> str | None:
        if api_key_name:
            api_key = os.getenv(api_key_name)
            if not api_key:
                raise ValueError(f"Environment variable for API key '{api_key_name}' not found or empty.")
            return api_key
        return None

    def _execute_request_with_retries(self, req: urllib.request.Request) -> dict:
        max_retries = 3
        for _ in range(max_retries):
            try:
                with urllib.request.urlopen(req) as response:
                    return json.loads(response.read().decode('utf-8'))
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(60)
                    continue
                elif e.code >= 500:
                    time.sleep(1)
                    continue
                else:
                    raise RuntimeError(f"Request failed with HTTP {e.code}: {e.read().decode('utf-8')}") from e
        raise RuntimeError(f"Request failed after {max_retries} retries.")

    def generation_request(self, model: Model, payload: list[HistoryRecord]) -> str:
        if model.provider not in self.providers_dict:
            raise ValueError(f"Provider '{model.provider}' not found.")
        
        with open("payloads_log.json", "a") as f:
            payload_list = []
            for record in payload:
                payload_list.append({"role": record.role, "message": record.message})
            json.dump(payload_list, f, indent=4, ensure_ascii=False)
            f.write(",\n")
            
        provider_info = self.providers_dict[model.provider]
        endpoint = provider_info["endpoint"]
        structure = provider_info["structure"]
        
        rendered_payload = self._render_payload(structure, model.model_id, payload)
        
        headers = {'Content-Type': 'application/json'}
        api_key = self._get_api_key(model.api_key_name)
            
        if api_key:
            if structure == "google-compatible":
                headers['x-goog-api-key'] = api_key
            else:
                headers['Authorization'] = f'Bearer {api_key}'
        
        request_url = endpoint
        if structure == "google-compatible":
            if not request_url.endswith("/"):
                request_url += "/"
            request_url += f"{model.model_id}:generateContent"
        elif structure == "openai-compatible":
            if not request_url.endswith("/"):
                request_url += "/"
            request_url += "chat/completions"
            
        req = urllib.request.Request(
            request_url, 
            data=json.dumps(rendered_payload).encode('utf-8'), 
            headers=headers, 
            method='POST'
        )
        
        response_data = self._execute_request_with_retries(req)
        
        if structure == "google-compatible":
            return response_data["candidates"][0]["content"]["parts"][0]["text"]
        elif structure == "openai-compatible":
            return response_data["choices"][0]["message"]["content"]
        else:
            raise ValueError(f"Unknown structure: {structure}")

    def embeding_request(self, provider: str, model_id: str, API_KEY_NAME: str | None, payload: str) -> list[float]:
        if provider not in self.providers_dict:
            raise ValueError(f"Provider '{provider}' not found.")
            
        provider_info = self.providers_dict[provider]
        endpoint = provider_info["endpoint"]
        structure = provider_info["structure"]
        
        headers = {'Content-Type': 'application/json'}
        api_key = self._get_api_key(API_KEY_NAME)
            
        if api_key:
            if structure == "google-compatible":
                headers['x-goog-api-key'] = api_key
            else:
                headers['Authorization'] = f'Bearer {api_key}'
                
        if structure == "google-compatible":
            request_data = {
                "model": f"models/{model_id}",
                "content": {"parts": [{"text": payload}]}
            }
            
            request_url = endpoint
            if not request_url.endswith("/"):
                request_url += "/"
            request_url += f"{model_id}:embedContent"
            
        elif structure == "openai-compatible":
            request_data = {
                "model": model_id,
                "input": payload
            }
            
            request_url = endpoint
            if not request_url.endswith("/"):
                request_url += "/"
            request_url += "embeddings"
            
        else:
            raise ValueError(f"Unknown structure: {structure}")
            
        req = urllib.request.Request(
            request_url, 
            data=json.dumps(request_data).encode('utf-8'), 
            headers=headers, 
            method='POST'
        )
        
        response_data = self._execute_request_with_retries(req)
        
        if structure == "google-compatible":
            return response_data["embedding"]["values"]
        elif structure == "openai-compatible":
            return response_data["data"][0]["embedding"]
        else:
            raise ValueError(f"Unknown structure: {structure}")
