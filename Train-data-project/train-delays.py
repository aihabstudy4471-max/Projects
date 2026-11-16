import os
import requests

API_KEY = os.environ["RDM_API_KEY"]
URL = "https://api1.raildata.org.uk/1010-historical-service-performance-_hsp_1_1/serviceMetrics"
print(URL)
headers = {"x-apikey": API_KEY, "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
body = {
    "from_loc": "SWI",
    "to_loc": "BTH",
    "from_time": "0730",
    "to_time": "0930",
    "from_date": "2026-11-02",
    "to_date": "2026-11-06",
    "days": "WEEKDAY",
}

response = requests.post(URL, headers=headers, json=body)
print(response.status_code)
print(response.text[:200])
data = response.json()
services = data["Services"]

print(len(services))
print(services[0]["serviceAttributesMetrics"]["gbtt_ptd"])

for i in services:
    print(i)