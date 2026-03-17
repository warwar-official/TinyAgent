import json
import time
import random
import requests
from typing import Any
from imports.mcp.base import MCPServer
from imports.image_manager import ImageManager


class ImageGeneratorMCP(MCPServer):
    """MCP server that generates images via a local ComfyUI instance.

    Loads a ComfyUI workflow JSON (e.g. FLUX.2-Q), injects the user's
    prompt, sends it to ComfyUI's ``/prompt`` endpoint, waits for
    completion, downloads the result, and stores it through
    ``ImageManager``.
    """

    def __init__(
        self,
        workflow_path: str = "./data/workflows/FLUX.2-Q.json",
        comfyui_url: str = "http://127.0.0.1:8188",
        image_manager: ImageManager | None = None,
    ) -> None:
        super().__init__()
        self.comfyui_url = comfyui_url.rstrip("/")
        self.image_manager = image_manager
        self._workflow_template = self._load_workflow(workflow_path)

    # ------------------------------------------------------------------
    # RPC handler
    # ------------------------------------------------------------------

    def _rpc_tool_execute(self, params: dict) -> dict:
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "generate_image":
            return self.generate_image(**args)
        else:
            raise ValueError(f"ImageGeneratorMCP: Unknown tool {tool_name}")

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "bad geometry, abnormal body parts, unnatural faces, bad fonts",
        steps: int | None = 5,
        width: int | None = 1024,
        height: int | None = 1024,
    ) -> dict:
        """Queue a ComfyUI workflow with the given prompt and return the image hash."""
        width = min(width, 1024)
        height = min(height, 1024)
        steps = min(steps, 15)
        if not self._workflow_template:
            return {"status": "error", "message": "Workflow template not loaded."}

        try:
            workflow = self._prepare_workflow(prompt, negative_prompt, steps, width, height)
            prompt_id = self._queue_prompt(workflow)
            image_data = self._poll_and_download(prompt_id)

            if self.image_manager:
                image_hash = self.image_manager.save_image_from_bytes(image_data, ext="png")
                return {"status": "ok", "image_hash": image_hash}
            else:
                return {"status": "error", "message": "ImageManager not available."}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_workflow(path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"ImageGeneratorMCP: Failed to load workflow from {path}: {e}")
            return {}

    def _prepare_workflow(
        self,
        prompt: str,
        negative_prompt: str,
        steps: int | None,
        width: int | None,
        height: int | None,
    ) -> dict:
        """Clone the workflow template and inject user parameters."""
        wf = json.loads(json.dumps(self._workflow_template, ensure_ascii=False))  # deep copy

        # Inject positive prompt (node "18")
        if "18" in wf:
            wf["18"]["inputs"]["value"] = prompt

        # Inject negative prompt (node "19")
        if "19" in wf:
            wf["19"]["inputs"]["value"] = negative_prompt

        # Override steps via PrimitiveInt node "20"
        if steps is not None and "20" in wf:
            wf["20"]["inputs"]["value"] = steps

        # Override latent image size (node "2")
        if "2" in wf:
            if width is not None:
                wf["2"]["inputs"]["width"] = width
            if height is not None:
                wf["2"]["inputs"]["height"] = height

        # Randomize seed
        if "3" in wf:
            wf["3"]["inputs"]["seed"] = random.randint(0, 2**53)

        return wf

    def _queue_prompt(self, workflow: dict) -> str:
        """Send the workflow to ComfyUI and return the prompt_id."""
        payload = {"prompt": workflow}
        resp = requests.post(
            f"{self.comfyui_url}/prompt",
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise ValueError(f"ComfyUI did not return a prompt_id: {data}")
        return prompt_id

    def _poll_and_download(self, prompt_id: str, timeout: int = 300, interval: int = 3) -> bytes:
        """Poll ComfyUI /history until the prompt completes, then download the image."""
        deadline = time.time() + timeout

        while time.time() < deadline:
            resp = requests.get(
                f"{self.comfyui_url}/history/{prompt_id}",
                timeout=15,
            )
            resp.raise_for_status()
            history = resp.json()

            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                # Find the SaveImage node output
                for node_id, node_output in outputs.items():
                    images = node_output.get("images", [])
                    if images:
                        img_info = images[0]
                        return self._download_image(
                            img_info["filename"],
                            img_info.get("subfolder", ""),
                            img_info.get("type", "output"),
                        )
                raise ValueError("ComfyUI prompt completed but no images found in outputs.")

            time.sleep(interval)

        raise TimeoutError(f"ComfyUI prompt {prompt_id} did not complete within {timeout}s.")

    def _download_image(self, filename: str, subfolder: str, folder_type: str) -> bytes:
        """Download a generated image from ComfyUI /view endpoint."""
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        resp = requests.get(
            f"{self.comfyui_url}/view",
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.content
