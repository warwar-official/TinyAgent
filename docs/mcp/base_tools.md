# Base Tools MCP

## Purpose
Provides a collection of "standard" tools for web interaction and data retrieval.

## Abilities
- **Weather Skills**: Fetching current conditions and forecasts.
- **Web Browsing**: Searching the web and fetching clean text content from URLs.
- **YouTube Skills**: Extracting transcripts from YouTube videos.

## Tools
### 1. `fetch_weather`
- **Description**: Gets current weather for a city.
- **Input**: `location` (string)
- **Output**: JSON with temperature, conditions, and forecast.

### 2. `web_search`
- **Description**: Searches the web.
- **Input**: `query` (string), `count` (integer)
- **Output**: List of snippets and URLs.

### 3. `web_fetch`
- **Description**: Fetches text content from a URL.
- **Input**: `url` (string)
- **Output**: Markdown-formatted text content.

### 4. `get_youtube_transcript`
- **Description**: Fetches transcript for a YouTube video.
- **Input**: `url` (string)
- **Output**: Full transcript text.

## Examples
- "What is the weather in Kyiv?" -> `fetch_weather(location="Kyiv")`
- "Read this article: https://example.com" -> `web_fetch(url="https://example.com")`
