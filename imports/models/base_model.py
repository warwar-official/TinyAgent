

class BaseAPIModel:
    API_ENDPOINT: str
    API_KEY: str
    MODEL_ID: str
    def make_request(self, prompt: str, tools: list[dict]) -> str:
        raise NotImplementedError