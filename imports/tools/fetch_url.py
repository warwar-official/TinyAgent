import requests
from html.parser import HTMLParser

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

def fetch_url(url: str) -> str:
    """
    Fetches the content of a URL, returning clean text, links, and table data as a string.
    Ignores headers, footers, navigation, scripts, and styles.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; TinyAgent/1.0)'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Check content type, only parse HTML
        content_type = response.headers.get('Content-Type', '').lower()
        if 'text/html' not in content_type:
            return f"Content-Type: {content_type}\n\n{response.text[:10000]}"

        parser = PageContentParser()
        parser.feed(response.text)
        
        # Format output
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
            # Deduplicate links while keeping order roughly
            unique_links = list(set(parser.links))
            output_parts.append("\n".join(unique_links))
            
        return "\n".join(output_parts)

    except Exception as e:
        return f"Error fetching URL: {str(e)}"
