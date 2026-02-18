from requests import request
import os
import dotenv
dotenv.load_dotenv()

def web_search(query: str, count: int = 3) -> dict:
    if count > 5:
        count = 5
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": os.getenv("BRAVE_API_KEY")
    }

    response = request("GET", f"https://api.search.brave.com/res/v1/web/search?q={query}&country=US&search_lang=en&count={count}", headers=headers)
    while response.status_code != 200:
        if response.status_code == 422:
            time.sleep(60)
        else:
            return {"error": f"Error while searching the web. Status code: {response.status_code}"}
        response = request("GET", f"https://api.search.brave.com/res/v1/web/search?q={query}&country=US&search_lang=en&count={count}", headers=headers)
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
    

    return result
