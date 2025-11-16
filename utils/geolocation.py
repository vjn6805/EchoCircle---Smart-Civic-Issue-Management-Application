import requests

def get_city_coordinates(city_name):
    """Fetch latitude and longitude from OpenStreetMap for the given city."""
    try:
        url = f"https://nominatim.openstreetmap.org/search?city={city_name}&format=json&limit=1"
        response = requests.get(url, headers={'User-Agent': 'EchoCircle/1.0'}).json()
        if response:
            return float(response[0]['lat']), float(response[0]['lon'])
    except Exception as e:
        print("Geocoding Error:", e)
    return 23.0225, 72.5714
