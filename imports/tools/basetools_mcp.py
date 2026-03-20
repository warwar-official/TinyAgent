import os
import time
import requests
from html.parser import HTMLParser
import uuid
from typing import Any
from imports.mcp.base import MCPServer

class PageContentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_content: list[str] = []
        self.links: list[str] = []
        self.tables: list[str] = []
        
        # State
        self.ignore_tags = {'script', 'style', 'head', 'header', 'footer', 'nav', 'aside', 'noscript', 'iframe', 'svg'}
        self.ignore_depth = 0
        self.in_table = False
        self.current_table_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag in self.ignore_tags:
            self.ignore_depth += 1
        if self.ignore_depth == 0:
            if tag == 'a':
                attrs_dict = dict(attrs)
                href = attrs_dict.get('href')
                if href and not href.startswith('#') and not href.startswith('javascript:'):
                    self.links.append(href)
            elif tag == 'table':
                self.in_table = True
                self.current_table_text = []

    def handle_endtag(self, tag: str):
        if tag in self.ignore_tags:
            if self.ignore_depth > 0:
                self.ignore_depth -= 1
        if self.ignore_depth == 0:
            if tag == 'table':
                self.in_table = False
                if self.current_table_text:
                    self.tables.append(" | ".join(self.current_table_text))

    def handle_data(self, data: str):
        if self.ignore_depth == 0:
            text = data.strip()
            if text:
                self.text_content.append(text)
                if self.in_table:
                    self.current_table_text.append(text)


class BaseToolsMCP(MCPServer):
    """MCP server that manages the base agent tools directly without dynamic loading."""
    
    def __init__(self) -> None:
        pass

    def _rpc_tool_execute(self, params: dict) -> Any:
        name: str = params["name"]
        arguments: dict = params.get("arguments", {})

        try:
            if name == "fetch_weather":
                return self.fetch_weather(**arguments)
            elif name == "web_search":
                return self.web_search(**arguments)
            elif name == "web_fetch":
                return self.web_fetch(**arguments)
            elif name == "get_youtube_transcript":
                return self.get_youtube_transcript(**arguments)
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

    def fetch_weather(self, location: str) -> dict:
        tool_answer = {"tool_name": "fetch_weather", "tool_arguments": {"location": location}, "tool_result": None, "truncate": False, "error": None}
        headers = {"User-Agent": "TinyAgent"}
        location_url = location.replace(" ", "+")
        response = requests.request("GET", f"https://nominatim.openstreetmap.org/search?q={location_url}&format=json", headers=headers)
        location_json = response.json()
        if location_json:
            lat = location_json[0]["lat"]
            lon = location_json[0]["lon"]
            weather_json = requests.request("GET", f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true", headers=headers).json()
            if weather_json:
                tool_answer["tool_result"] = {
                    "temperature": weather_json["current_weather"]["temperature"],
                    "windspeed": weather_json["current_weather"]["windspeed"],
                    "winddirection": weather_json["current_weather"]["winddirection"],
                    "weathercode": weather_json["current_weather"]["weathercode"],
                    "is_day": weather_json["current_weather"]["is_day"],
                    "time": weather_json["current_weather"]["time"],
                }
            else:
                tool_answer["error"] = "Weather not found"
        else:
            tool_answer["error"] = "Location not found"
        return tool_answer

    def web_search(self, query: str, count: int = 3) -> dict:
        TOKEN = os.getenv("BRAVE_API_KEY")
        if not TOKEN:
            return {
                "tool_name": "web_search", 
                "tool_arguments": {"query": query, "count": count}, 
                "tool_result": None, 
                "truncate": False, 
                "error": "BRAVE_API_KEY not found in environment variables"
            }
        query = query.replace("\"", "").replace("\\"," ").replace("'", " ")
        tool_answer = {"tool_name": "web_search", "tool_arguments": {"query": query, "count": count}, "tool_result": None, "truncate": False, "error": None}
        
        if count > 5:
            count = 5
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": TOKEN
        }

        response = requests.request("GET", f"https://api.search.brave.com/res/v1/web/search?q={query}&country=US&search_lang=en&count={count}", headers=headers)
        while response.status_code != 200:
            if response.status_code == 422:
                time.sleep(30)
            else:
                tool_answer["error"] = f"Error while searching the web. Status code: {response.status_code}"
                return tool_answer
            response = requests.request("GET", f"https://api.search.brave.com/res/v1/web/search?q={query}&country=US&search_lang=en&count={count}", headers=headers)
        
        response_json = response.json()
        
        result = {
            "news": [],
            "web": []
        }
        if "news" in response_json:
            for news in response_json["news"]["results"]:
                result["news"].append({
                    "title": news["title"],
                    "url": news["url"],
                    "description": news["description"],
                    "age": news["age"],
                    "extra_snippet": news.get("extra_snippet", "")
                })
        if "web" in response_json:
            for web in response_json["web"]["results"]:
                result["web"].append({
                    "title": web["title"],
                    "url": web["url"],
                    "description": web["description"],
                    "language": web["language"],
                    "age": web.get("age", "")
                })
        
        tool_answer["tool_result"] = result
        return tool_answer

    def web_fetch(self, url: str) -> dict:
        tool_answer = {"tool_name": "web_fetch", "tool_arguments": {"url": url}, "tool_result": None, "truncate": False, "error": None}
        
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (compatible; TinyAgent/1.0)'}
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' not in content_type:
                if len(response.text) > 10000:
                    tool_answer["truncate"] = True
                    tool_answer["tool_result"] = f"Content-Type: {content_type}\n\n{response.text[:10000]}... (truncated)"
                else:
                    tool_answer["tool_result"] = f"Content-Type: {content_type}\n\n{response.text}"
                return tool_answer

            parser = PageContentParser()
            parser.feed(response.text)
            
            output_parts = []
            if parser.text_content:
                output_parts.append("=== Text Content ===")
                output_parts.append(" ".join(parser.text_content))
                output_parts.append("")
                
            if parser.tables:
                output_parts.append("=== Tables ===")
                for i, table in enumerate(parser.tables, 1):
                    output_parts.append(f"Table {i}: {table}")
                output_parts.append("")
                
            if parser.links:
                output_parts.append("=== Links ===")
                unique_links = list(set(parser.links))
                output_parts.append("\n".join(unique_links))
                
            result = "\n".join(output_parts)
            if len(result) > 10000:
                tool_answer["truncate"] = True
                tool_answer["tool_result"] = result[:10000] + "\n... (truncated)"
            else:
                tool_answer["tool_result"] = result
            return tool_answer

        except Exception as e:
            tool_answer["error"] = str(e)
            return tool_answer
    def get_youtube_transcript(self, url: str) -> dict:
        tool_answer = {"tool_name": "get_youtube_transcript", "tool_arguments": {"url": url}, "tool_result": None, "truncate": False, "error": None}
        
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
            return tool_answer

        except Exception as e:
            tool_answer["error"] = str(e)
            return tool_answer
