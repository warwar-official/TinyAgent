from requests import request

def get_current_weather(location: str) -> dict:
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
            return answer
        return {"error": "Weather not found"}
    return {"error": "Location not found"}