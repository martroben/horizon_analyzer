
import datetime
import json
import os
import random
import re

def read_latest_file(dir_path: str, file_handle: str = None) -> list[dict]:
    """
    Reads file with the latest timestamp in filename from given dir_path.
    If file_handle is given, checks only filenames with the given file_handle followed by a timestamp.
    """
    if not file_handle:
        file_handle = ".+"
    name_pattern = file_handle + r'_(\d+)'

    files = [file for file in os.listdir(dir_path) if re.match(name_pattern, file)]
    files_latest = sorted(files, key=lambda x: re.match(name_pattern, x).group(1))[-1]
    path = f'{dir_path.strip("/")}/{files_latest}'

    with open(path, encoding="utf8") as read_file:
        data = json.loads(read_file.read())
    
    return data


data = read_latest_file("data/results/", "open_access_data")

random.seed(1913)
selected_data = random.sample(data, 20)
guids = [item["GUID"] for item in selected_data]

timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%SUTC")
output_file_path = f'./data/manual/manual_check_guids_{timestamp}.txt'

# Save the GUIDs to the file
with open(output_file_path, "w", encoding="utf8") as output_file:
    for guid in guids:
        output_file.write(f"{guid}\n")
