import os
import json
import base64
import requests
from typing import Any
from imports.mcp.base import MCPServer

class SpotifyMCP(MCPServer):
    def __init__(self, secrets_path: str = "./data/spotify_secrets.json"):
        super().__init__()
        self.secrets_path = secrets_path
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.client_id: str | None = None
        self.client_secret: str | None = None
        
        self._load_tokens()

    def _load_tokens(self) -> None:
        if os.path.exists(self.secrets_path):
            try:
                with open(self.secrets_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.access_token = data.get("access_token")
                        self.refresh_token = data.get("refresh_token")
                        self.client_id = data.get("client_id")
                        self.client_secret = data.get("client_secret")
            except Exception as e:
                print(f"SpotifyMCP: Failed to read tokens: {e}")

    def _save_tokens(self, access_token: str, refresh_token: str | None = None) -> None:
        self.access_token = access_token
        if refresh_token:
            self.refresh_token = refresh_token
            
        data: dict = {}
        if os.path.exists(self.secrets_path):
            try:
                with open(self.secrets_path, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                    if isinstance(file_data, dict):
                        data = file_data
            except:
                pass
            
        data["access_token"] = self.access_token
        if self.refresh_token:
            data["refresh_token"] = self.refresh_token
            
        os.makedirs(os.path.dirname(os.path.abspath(self.secrets_path)), exist_ok=True)
        with open(self.secrets_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _refresh_access_token(self) -> bool:
        if not self.refresh_token:
            return False
            
        url = "https://accounts.spotify.com/api/token"
        auth_string = f"{self.client_id}:{self.client_secret}"
        b64_auth = base64.b64encode(auth_string.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {b64_auth}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token
        }
        
        try:
            response = requests.post(url, headers=headers, data=data, timeout=10)
            if response.status_code == 200:
                resp_data = response.json()
                new_access_token = resp_data.get("access_token")
                new_refresh_token = resp_data.get("refresh_token") # sometimes Spotify doesn't return a new one
                self._save_tokens(new_access_token, new_refresh_token)
                return True
        except Exception as e:
            print(f"SpotifyMCP: Token refresh failed: {e}")
            
        return False

    def _make_request(self, method: str, endpoint: str, params: dict | None = None, json_data: dict | None = None) -> dict:
        if not self.access_token:
            # Try to load just in case
            self._load_tokens()
            if not self.access_token:
                return {"status": "error", "message": "No access token. Please authenticate Spotify."}

        # Build full URL if the endpoint is relative to API
        url = endpoint if endpoint.startswith("http") else f"https://api.spotify.com/v1{endpoint}"
        
        for attempt in range(2):
            headers = {"Authorization": f"Bearer {self.access_token}"}
            try:
                response = requests.request(method, url, headers=headers, params=params, json=json_data, timeout=10)
                
                if response.status_code == 401:
                    if attempt == 0 and self._refresh_access_token():
                        continue
                    return {"status": "error", "message": "Unauthorized or token expired"}
                
                if response.status_code == 403:
                    return {"status": "error", "message": "Forbidden. Possibly no active device or premium required."}
                
                if response.status_code == 404:
                    return {"status": "error", "message": "Resource not found or invalid ID."}
                
                if 200 <= response.status_code < 300:
                    try:
                        data = response.json()
                        return {"status": "success", "data": data}
                    except ValueError:
                        return {"status": "success", "data": None, "message": "Success"}
                
                return {
                    "status": "error", 
                    "message": f"Spotify API error: {response.status_code} - {response.text}"
                }
                
            except requests.exceptions.Timeout:
                if attempt == 0:
                    continue
                return {"status": "error", "message": "Request timed out"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        return {"status": "error", "message": "Request failed after retries."}

    def _rpc_tool_execute(self, params: dict) -> Any:
        name = params.get("name")
        args = params.get("arguments", {})
        
        if name == "playback_control":
            action = args.get("action", "")
            if action == "play":
                req_data = {}
                uris = args.get("uris")
                context_uri = args.get("context_uri")
                offset = args.get("offset")
                
                if uris:
                    req_data["uris"] = uris
                elif context_uri:
                    req_data["context_uri"] = context_uri
                    
                if offset is not None:
                    req_data["offset"] = offset
                    
                if req_data:
                    return self._make_request("PUT", "/me/player/play", json_data=req_data)
                return self._make_request("PUT", "/me/player/play")
            elif action == "pause":
                return self._make_request("PUT", "/me/player/pause")
            elif action == "next":
                return self._make_request("POST", "/me/player/next")
            elif action == "previous":
                return self._make_request("POST", "/me/player/previous")
            return {"status": "error", "message": f"Unknown action: {action}"}
            
        elif name == "playback_mode":
            repeat = args.get("repeat")
            shuffle = args.get("shuffle")
            
            res1 = {"status": "success"}
            if repeat is not None:
                res1 = self._make_request("PUT", "/me/player/repeat", params={"state": repeat})
            
            res2 = {"status": "success"}
            if shuffle is not None:
                res2 = self._make_request("PUT", "/me/player/shuffle", params={"state": "true" if shuffle else "false"})
                
            if res1.get("status") == "error": return res1
            if res2.get("status") == "error": return res2
            return {"status": "success", "message": "Playback mode updated"}
            
        elif name == "spotify_search":
            query = args.get("query", "")
            limit = args.get("limit", 5)
            types_list = args.get("type", ["track"])
            types_str = ",".join(types_list)
            
            res = self._make_request("GET", "/search", params={"q": query, "type": types_str, "limit": limit})
            if res.get("status") == "success":
                results = []
                # Spotify returns items nested under type name with 's' suffix, e.g. tracks, albums
                for t in types_list:
                    key = t + "s"
                    items = res["data"].get(key, {}).get("items", [])
                    for item in items:
                        if not item: # sometimes API can return None in the list
                            continue
                        artists = ", ".join([a.get("name") for a in item.get("artists", [])]) if "artists" in item else None
                        results.append({
                            "type": item.get("type"),
                            "name": item.get("name"),
                            "artist": artists,
                            "id": item.get("id"),
                            "uri": item.get("uri")
                        })
                return {"status": "success", "data": results}
            return res
            
        elif name == "create_playlist":
            playlist_name = args.get("name")
            # 1. Check if playlist already exists
            user_playlists_res = self._make_request("GET", "/me/playlists")
            if user_playlists_res.get("status") == "success":
                playlists = user_playlists_res.get("data", {}).get("items", [])
                for pl in playlists:
                    if pl.get("name") == playlist_name:
                        return {
                            "status": "success",
                            "message": f"Playlist '{playlist_name}' already exists. Found existing ID.",
                            "data": {
                                "id": pl.get("id"),
                                "name": pl.get("name"),
                                "description": pl.get("description")
                            }
                        }

            # 2. Proceed with creation if not found
            return self._make_request("POST", "/me/playlists", json_data={
                "name": playlist_name,
                "description": args.get("description", ""),
                "public": args.get("public", True)
            })
            
        elif name == "add_to_playlist":
            playlist_id = args.get("playlist_id")
            # Accept both a single track_uri (string) and track_uris (list)
            track_uris = args.get("track_uris") or args.get("uris")
            if not track_uris:
                single = args.get("track_uri")
                track_uris = [single] if single else []
            if not isinstance(track_uris, list):
                track_uris = [track_uris]
            if not track_uris:
                return {"status": "error", "message": "No track URIs provided."}
            # Spotify allows up to 100 URIs per request
            results = []
            for i in range(0, len(track_uris), 100):
                chunk = track_uris[i:i + 100]
                res = self._make_request("POST", f"/playlists/{playlist_id}/items", json_data={"uris": chunk})
                results.append(res)
                if res.get("status") != "success":
                    return res
            return {"status": "success", "message": f"Added {len(track_uris)} track(s) to playlist."}
            
        elif name == "remove_from_playlist":
            playlist_id = args.get("playlist_id")
            track_uri = args.get("track_uri")
            return self._make_request("DELETE", f"/playlists/{playlist_id}/items", json_data={"tracks": [{"uri": track_uri}]})
            
        elif name == "get_playlist":
            playlist_id = args.get("playlist_id")
            return self._make_request("GET", f"/playlists/{playlist_id}")
            
        elif name == "get_playback_state":
            res = self._make_request("GET", "/me/player")
            if res.get("status") == "success" and res.get("data"):
                data = res["data"]
                return {
                    "status": "success",
                    "data": {
                        "device": data.get("device", {}).get("name"),
                        "track": data.get("item", {}).get("name") if data.get("item") else None,
                        "state": "play" if data.get("is_playing") else "paused",
                        "playback_mode": {
                            "repeat": data.get("repeat_state"),
                            "shuffle": data.get("shuffle_state")
                        }
                    }
                }
            return res
            
        elif name == "get_playback_device":
            return self._make_request("GET", "/me/player/devices")
            
        elif name == "set_playback_device":
            device_id = args.get("device_id")
            return self._make_request("PUT", "/me/player", json_data={"device_ids": [device_id]})
            
        elif name == "get_lyrics":
            artist = args.get("artist", "")
            track_name = args.get("track_name", "")
            try:
                # lyrics.ovh API
                response = requests.get(f"https://api.lyrics.ovh/v1/{artist}/{track_name}", timeout=10)
                if response.status_code == 200:
                    return {"status": "success", "data": {"lyrics": response.json().get("lyrics")}}
                return {"status": "error", "message": f"Lyrics not found. Status: {response.status_code}"}
            except Exception as e:
                return {"status": "error", "message": str(e)}
                
        else:
            raise ValueError(f"SpotifyMCP: Unknown tool {name}")
