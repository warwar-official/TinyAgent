

class BaseAPIModel:
    API_ENDPOINT: str
    API_KEY: str
    MODEL_ID: str
    def make_request(self, payload: dict) -> str:
        raise NotImplementedError