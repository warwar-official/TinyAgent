import os
import requests
import json
import hashlib
import uuid
from typing import Any
from imports.mcp.base import MCPServer
from imports.embedding_service import EmbeddingService
from imports.knowledge_base_rag import KnowledgeBaseRAG

class YoutubeMCP(MCPServer):
    """MCP server that manages YouTube related tools."""
    
    def __init__(self, app_config: dict = None) -> None:
        super().__init__()
        self.kb_rag = None
        if app_config and app_config.get("context", {}).get("memory", {}).get("active", False):
            mem_cfg = app_config["context"]["memory"]
            emb_service = EmbeddingService.get_instance(
                emb_model_name=mem_cfg.get("emb_model_name", "intfloat/multilingual-e5-large"),
                models_cache_path=mem_cfg.get("models_cache_path", "./data/memory/models/")
            )
            self.kb_rag = KnowledgeBaseRAG.get_instance(
                db_path=mem_cfg.get("db_path", "./data/memory/db/"),
                embedding_service=emb_service
            )

    def _rpc_tool_execute(self, params: dict) -> Any:
        name: str = params["name"]
        arguments: dict = params.get("arguments", {})

        # API key verification for all but get_transcript
        if name != "get_transcript" and not os.getenv("YOUTUBE_API_KEY"):
            return {
                "tool_name": name,
                "tool_arguments": arguments,
                "tool_result": None,
                "truncate": False,
                "error": "Error: YOUTUBE_API_KEY not found in environment variables",
            }

        try:
            if name == "get_transcript":
                return self.get_transcript(**arguments)
            elif name == "search":
                return self.search(**arguments)
            elif name == "get_video_info":
                return self.get_video_info(**arguments)
            elif name == "get_channel":
                return self.get_channel(**arguments)
            elif name == "get_playlist":
                return self.get_playlist(**arguments)
            else:
                return {
                    "tool_name": name,
                    "tool_arguments": arguments,
                    "tool_result": None,
                    "truncate": False,
                    "error": "Error: Tool not found",
                }
        except Exception as e:
            return {
                "tool_name": name,
                "tool_arguments": arguments,
                "tool_result": None,
                "truncate": False,
                "error": str(e),
            }

    def get_transcript(self, url: str) -> dict:
        tool_answer = {"tool_name": "get_transcript", "tool_arguments": {"url": url}, "tool_result": None, "truncate": False, "error": None}
        
        url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
        cache_dir = "data/cache/youtube_transcripts"
        cache_file = os.path.join(cache_dir, f"{url_hash}.json")
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                    tool_answer["tool_result"] = cached_data
                    return tool_answer
            except Exception:
                pass

        try:
            # Extract video_id
            video_id = None
            if "v=" in url:
                video_id = url.split("v=")[1].split("&")[0]
            elif "youtu.be/" in url:
                video_id = url.split("youtu.be/")[1].split("?")[0]
            
            if not video_id:
                tool_answer["error"] = "Invalid YouTube URL"
                return tool_answer

            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; TinyAgent/1.0)'
            }
            cookies = {
                'anonymous_user_id': str(uuid.uuid4())
            }
            
            api_url = f"https://notegpt.io/api/v2/video-transcript?platform=youtube&video_id={video_id}"
            response = requests.get(api_url, headers=headers, cookies=cookies, timeout=15)
            response_json = response.json()
            
            if response_json.get("code") != 100000:
                tool_answer["tool_result"] = {
                    "code": response_json.get("code"),
                    "message": response_json.get("message")
                }
                return tool_answer
            
            data = response_json.get("data", {})
            video_info = data.get("videoInfo", {})
            
            # Find transcription
            transcript = None
            lang_codes = data.get("language_code", [])
            if lang_codes:
                first_lang = lang_codes[0].get("code")
                transcripts_dict = data.get("transcripts", {}).get(first_lang, {})
                for t_type in ["custom", "default", "auto"]:
                    if transcripts_dict.get(t_type):
                        transcript = transcripts_dict[t_type]
                        break
            
            tool_answer["tool_result"] = {
                "name": video_info.get("name"),
                "author": video_info.get("author"),
                "transcript": transcript
            }
            
            os.makedirs(cache_dir, exist_ok=True)
            try:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(tool_answer["tool_result"], f, ensure_ascii=False)
            except Exception:
                pass
                
            try:
                if self.kb_rag and transcript:
                    full_text = []
                    for t in transcript:
                        if isinstance(t, dict) and "text" in t:
                            full_text.append(t["text"])
                    if full_text:
                        merged_transcript = " ".join(full_text)
                        self.kb_rag.add_document(
                            text=merged_transcript,
                            url=url,
                            title=f"{video_info.get('author')} - {video_info.get('name')}"
                        )
            except Exception as e:
                print(f"Failed to ingest YouTube transcript into KBRAG: {e}")

            return tool_answer

        except Exception as e:
            tool_answer["error"] = str(e)
            return tool_answer

    def _sanitize_text(self, text: str) -> str:
        if not text:
            return ""
        # Remove new lines and trim
        return " ".join(text.split())

    def search(self, query: str, type: list[str] = None, limit: int = 5) -> dict:
        tool_answer = {"tool_name": "search", "tool_arguments": {"query": query, "type": type, "limit": limit}, "tool_result": None, "truncate": False, "error": None}
        api_key = os.getenv("YOUTUBE_API_KEY")
        
        type_str = "video,channel,playlist" if not type else ",".join(type)
        url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={query}&type={type_str}&maxResults={min(limit, 20)}&key={api_key}"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            results = []
            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                item_id = item.get("id", {})
                
                res_type = ""
                res_id = ""
                if "videoId" in item_id:
                    res_type = "video"
                    res_id = item_id["videoId"]
                elif "channelId" in item_id:
                    res_type = "channel"
                    res_id = item_id["channelId"]
                elif "playlistId" in item_id:
                    res_type = "playlist"
                    res_id = item_id["playlistId"]
                
                results.append({
                    "id": res_id,
                    "type": res_type,
                    "title": snippet.get("title", ""),
                    "description": self._sanitize_text(snippet.get("description", "")),
                    "channelTitle": snippet.get("channelTitle", ""),
                    "publishedAt": snippet.get("publishedAt", "")
                })
                
            tool_answer["tool_result"] = results
            return tool_answer
        except Exception as e:
            tool_answer["error"] = str(e)
            return tool_answer

    def get_video_info(self, videoId: str) -> dict:
        tool_answer = {"tool_name": "get_video_info", "tool_arguments": {"videoId": videoId}, "tool_result": None, "truncate": False, "error": None}
        api_key = os.getenv("YOUTUBE_API_KEY")
        
        url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails&id={videoId}&key={api_key}"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if not data.get("items"):
                tool_answer["error"] = "Video not found"
                return tool_answer
                
            item = data["items"][0]
            snippet = item.get("snippet", {})
            details = item.get("contentDetails", {})
            
            tool_answer["tool_result"] = {
                "id": videoId,
                "title": snippet.get("title", ""),
                "description": self._sanitize_text(snippet.get("description", "")),
                "channelTitle": snippet.get("channelTitle", ""),
                "duration": details.get("duration", ""),
                "publishedAt": snippet.get("publishedAt", ""),
                "tags": snippet.get("tags", [])[:5] if snippet.get("tags") else []
            }
            return tool_answer
        except Exception as e:
            tool_answer["error"] = str(e)
            return tool_answer

    def get_channel(self, channelId: str) -> dict:
        tool_answer = {"tool_name": "get_channel", "tool_arguments": {"channelId": channelId}, "tool_result": None, "truncate": False, "error": None}
        api_key = os.getenv("YOUTUBE_API_KEY")
        
        url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet,contentDetails&id={channelId}&key={api_key}"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if not data.get("items"):
                tool_answer["error"] = "Channel not found"
                return tool_answer
                
            item = data["items"][0]
            snippet = item.get("snippet", {})
            details = item.get("contentDetails", {})
            
            uploads_playlist_id = details.get("relatedPlaylists", {}).get("uploads", "")
            
            tool_answer["tool_result"] = {
                "id": channelId,
                "title": snippet.get("title", ""),
                "description": self._sanitize_text(snippet.get("description", "")),
                "publishedAt": snippet.get("publishedAt", ""),
                "customUrl": snippet.get("customUrl", ""),
                "uploads_playlist_id": uploads_playlist_id
            }
            return tool_answer
        except Exception as e:
            tool_answer["error"] = str(e)
            return tool_answer

    def get_playlist(self, playlistId: str, limit: int = 10) -> dict:
        tool_answer = {"tool_name": "get_playlist", "tool_arguments": {"playlistId": playlistId, "limit": limit}, "tool_result": None, "truncate": False, "error": None}
        api_key = os.getenv("YOUTUBE_API_KEY")
        
        url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId={playlistId}&maxResults={min(limit, 50)}&key={api_key}"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            results = []
            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                
                results.append({
                    "videoId": snippet.get("resourceId", {}).get("videoId", ""),
                    "title": snippet.get("title", ""),
                    "channelTitle": snippet.get("videoOwnerChannelTitle", "")
                })
                
            tool_answer["tool_result"] = results
            return tool_answer
        except Exception as e:
            tool_answer["error"] = str(e)
            return tool_answer
