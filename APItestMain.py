import requests
import time

url = "https://meritindia.in/StateWiseDetails/BindCurrentStateStatus?StateCode=CTG"

while True:
    r = requests.get(url, verify=False)
    data = r.json()[0]

    print(
        f"Demand={data['Demand']} MW | "
        f"ISGS={data['ISGS']} MW | "
        f"Import={data['ImportData']} MW"
    )

    time.sleep(60)