from __future__ import annotations
import json
import re
import urllib.request
import urllib.error
import os
import time
from imports.history_manager import HistoryRecord
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Model:
    provider: str
    model_id: str
    api_key_name: str | None
    response_format: str = "text"
    def __init__(self, provider: str, model_id: str, api_key_name: str | None,
                 vision_enabled: bool = False, response_format: str = "text"):
        self.provider = provider
        self.model_id = model_id
        self.api_key_name = api_key_name
        self.vision_enabled = vision_enabled
        self.response_format = response_format

class ProvidersManager:
    def __init__(self, providers: list[dict]):
        self.providers_dict = {p["name"]: p for p in providers}

    def _render_google_compatible_payload(
        self,
        payload: list[HistoryRecord],
        encode_images: bool = True,
        image_resolver: Callable[[str], str | None] | None = None,
    ) -> dict:
        contents = []
        for record in payload:
            role = "user" if record.role.lower() in ["user", "tool", "system"] else "model"
            
            message_text = record.message
            if record.role.lower() == "user":
                timestamp = record.create_time.strftime("[%H:%M, %-d %B]")
                message_text = f"{timestamp} {message_text}"
                
            parts: list[dict] = [{"text": message_text}]

            if encode_images and image_resolver and record.image_hashes:
                for img_hash in record.image_hashes:
                    b64 = image_resolver(img_hash)
                    if b64:
                        parts.append({
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": b64,
                            }
                        })

            contents.append({"role": role, "parts": parts})
        return {"contents": contents}

    def _render_openai_compatible_payload(
        self,
        model_id: str,
        payload: list[HistoryRecord],
        encode_images: bool = True,
        image_resolver: Callable[[str], str | None] | None = None,
    ) -> dict:
        messages = []
        for record in payload:
            role = "user" if record.role.lower() in ["user", "human"] else "assistant"
            if record.role.lower() == "system":
                role = "system"

            message_text = record.message
            if record.role.lower() == "user":
                timestamp = record.create_time.strftime("[%H:%M, %-d %B]")
                message_text = f"{timestamp} {message_text}"

            if encode_images and image_resolver and record.image_hashes:
                content = [{"type": "text", "text": message_text}]
                for img_hash in record.image_hashes:
                    b64 = image_resolver(img_hash)
                    if b64:
                        content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}"
                            }
                        })
            else:
                content = message_text

            messages.append({"role": role, "content": content})
        return {
            "model": model_id,
            "messages": messages
        }

    def _render_payload(
        self,
        structure: str,
        model_id: str,
        payload: list[HistoryRecord],
        encode_images: bool = True,
        image_resolver: Callable[[str], str | None] | None = None,
    ) -> dict:
        if structure == "google-compatible":
            return self._render_google_compatible_payload(payload, encode_images, image_resolver)
        elif structure == "openai-compatible":
            return self._render_openai_compatible_payload(model_id, payload, encode_images, image_resolver)
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
        max_retries = 5
        for _ in range(max_retries):
            try:
                with urllib.request.urlopen(req) as response:
                    return json.loads(response.read().decode('utf-8'))
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(30)
                    continue
                elif e.code >= 500:
                    time.sleep(5)
                    continue
                elif e.code == 400:
                    error_body = e.read().decode('utf-8')
                    raise RuntimeError(
                        f"Request rejected (HTTP 400). The model may not support this input format. "
                        f"Details: {error_body}"
                    ) from e
                else:
                    raise RuntimeError(f"Request failed with HTTP {e.code}: {e.read().decode('utf-8')}") from e
        raise RuntimeError(f"Request failed after {max_retries} retries.")

    def generation_request(
        self,
        model: Model,
        payload: list[HistoryRecord],
        encode_images: bool = True,
        image_resolver: Callable[[str], str | None] | None = None,
    ) -> str:
        if model.provider not in self.providers_dict:
            raise ValueError(f"Provider '{model.provider}' not found.")
        
        with open("logs/payloads_log.json", "a") as f:
            payload_list = []
            for record in payload:
                payload_list.append({"role": record.role, "message": record.message, "image_hashes": record.image_hashes})
            json.dump(payload_list, f, indent=4, ensure_ascii=False)
            f.write(",\n")
            
        provider_info = self.providers_dict[model.provider]
        endpoint = provider_info["endpoint"]
        structure = provider_info["structure"]
        
        rendered_payload = self._render_payload(
            structure, model.model_id, payload,
            encode_images=encode_images,
            image_resolver=image_resolver,
        )
        
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
            
        while True:
            if model.response_format == "json":
                if structure == "google-compatible":
                    rendered_payload["generationConfig"] = {"responseMimeType": "application/json"}
                elif structure == "openai-compatible":
                    rendered_payload["response_format"] = {"type": "json_object"}
            else:
                if structure == "google-compatible" and "generationConfig" in rendered_payload:
                    del rendered_payload["generationConfig"]
                elif structure == "openai-compatible" and "response_format" in rendered_payload:
                    del rendered_payload["response_format"]

            # Normalize payload to fix nested stringified JSON (prevent double escaping)
            normalized_payload = self._normalize_payload(rendered_payload)

            req = urllib.request.Request(
                request_url, 
                data=json.dumps(normalized_payload, ensure_ascii=False).encode('utf-8'), 
                headers=headers, 
                method='POST'
            )
            
            try:
                response_data = self._execute_request_with_retries(req)
                break
            except RuntimeError as e:
                if "HTTP 400" in str(e) and model.response_format == "json":
                    print("Модель не підтримує JSON-відповіді, використано текстовий режим.")
                    model.response_format = "text"
                    continue
                else:
                    raise
        
        if structure == "google-compatible":
            try:
                raw_text = response_data["candidates"][0]["content"]["parts"][0]["text"]
            except KeyError:
                print(response_data)
                raise RuntimeError("Google API returned unexpected response format.")
        elif structure == "openai-compatible":
            raw_text = response_data["choices"][0]["message"]["content"]
        else:
            raise ValueError(f"Unknown structure: {structure}")
            
        # Strip <think>...</think> block anywhere in the output
        cleaned_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL)
        # Also clean up any leading/trailing whitespace left by the removal
        return cleaned_text.strip()

    def _normalize_json_string(self, value: Any) -> Any:
        """Attempts to parse a string as JSON. If successful, returns the parsed object."""
        if isinstance(value, str):
            trimmed = value.strip()
            # Basic check for JSON-like structure
            if (trimmed.startswith("{") and trimmed.endswith("}")) or \
               (trimmed.startswith("[") and trimmed.endswith("]")):
                try:
                    return json.loads(trimmed)
                except:
                    return value
        return value

    def _normalize_payload(self, obj: Any) -> Any:
        """Recursively parses any stringified JSON within a data structure."""
        if isinstance(obj, dict):
            return {k: self._normalize_payload(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._normalize_payload(v) for v in obj]
        else:
            return self._normalize_json_string(obj)
