from requests import request

def current_weather(location: str) -> dict:
    tool_answer = {
        "tool_name": "current_weather",
        "tool_arguments": {
            "location": location
        },
        "tool_result": None,
        "truncate": False,
        "error": None
    }

    headers = {
        "User-Agent": "TinyAgent"
    }
    location_url = location.replace(" ", "+")
    response = request("GET", f"https://nominatim.openstreetmap.org/search?q={location_url}&format=json", headers=headers)
    location_json = response.json()
    if location_json:
        lat = location_json[0]["lat"]
        lon = location_json[0]["lon"]
        weather_json = request("GET", f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true", headers=headers).json()
        if weather_json:
            answer = {
                "temperature": weather_json["current_weather"]["temperature"],
                "windspeed": weather_json["current_weather"]["windspeed"],
                "winddirection": weather_json["current_weather"]["winddirection"],
                "weathercode": weather_json["current_weather"]["weathercode"],
                "is_day": weather_json["current_weather"]["is_day"],
                "time": weather_json["current_weather"]["time"],
            }
            tool_answer["tool_result"] = answer
        else:
            tool_answer["error"] = "Weather not found"
    else:
        tool_answer["error"] = "Location not found"
    return tool_answer