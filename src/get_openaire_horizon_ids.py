# standard
import datetime
import json
import logging
import os
import re
import sys
import time
# external
import requests
import tqdm


##########
# Inputs #
##########

ETIS_SCIENTIFIC_ARTICLES_CLASSIFICATION_CODES = [
    "1.1.",     # Web of Science & Scopus scientific articles
    "1.2.",     # Other international scientific articles
    "1.3."      # scientific articles in Estonian journals
]
ETIS_HORIZON_PROGRAM_CODES = [
    "136",      # Horizon 2020 EIT support
    "137",      # Horisont 2020 ERA \u00f5ppetoolide toetus
    "442",      # Horizon 2020
    "443",      # ERA-NET (Horizon 2020)
    "450",      # Horizon Europe Programme
    "451"       # ERA-NET (Horizon Europe)
]
ETIS_FINISHED_PROJECT_STATUS_CODE = 3
    # 1 - all projects
    # 2 - ongoing projects
    # 3 - finished projects

RAW_DATA_DIRECTORY_PATH = "./data/raw/"


#########################
# Classes and functions #
#########################


class OpenAireSession(requests.Session):
    """
    Class for requesting info from OpenAIRE search API.
    https://graph.openaire.eu/docs/apis/search-api/projects
    https://zenodo.org/records/2643199
    """
    BASE_URL = "https://api.openaire.eu/search"

    def __init__(self, service: str) -> None:
        super().__init__()
        self.service_URL = f'{self.BASE_URL}/{service}'

    def get_items(self, i_page: int = None, n_per_page: int = None, parameters: dict = None) -> requests.Response:
        """
        Get items from service that the session was initiated with.
        Get page i_page with n_per_page items per page.
        """
        query_parameters = {
            "format": "json"
        }   
        if i_page:
            query_parameters.update({"page": i_page})
        if n_per_page:
            query_parameters.update({"size": n_per_page})
        if parameters:
            query_parameters.update(parameters)

        URL = f'{self.service_URL}'
        response = self.get(URL, params=query_parameters)
        return response


def get_timestamp_string() -> str:
    """
    Gives a standard current timestamp string to use in filenames.
    """
    timestamp_format = "%Y%m%d%H%M%S%Z"

    timestamp = datetime.datetime.now(datetime.timezone.utc)
    timestamp_string = datetime.datetime.strftime(timestamp, timestamp_format)
    return timestamp_string


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


#####################
# Environment setup #
#####################

# Logger
logger = logging.getLogger()
logger.setLevel("INFO")
logger.addHandler(logging.StreamHandler(sys.stdout))


#############################
# Check Horizon identifiers #
#############################

# Reload data from save file
projects = read_latest_file(RAW_DATA_DIRECTORY_PATH, "projects")

ETIS_openaire_map = {
    "FinancierProjectNr": "grantID",
    "Acronym": "acronym",
    "TitleEng": "name"
}

input_parameters = list(ETIS_openaire_map.keys()) + ["Guid"]
openaire_inputs = []
for project in projects:
    if not (project["ProgrammeCode"] in ETIS_HORIZON_PROGRAM_CODES):
        continue

    openaire_inputs += [{parameter: project[parameter] for parameter in input_parameters}]


#########################
# Request OpenAIRE data #
#########################

openaire_session = OpenAireSession("projects")

openaire_results = []
for input in tqdm.tqdm(openaire_inputs, desc="OpenAIRE requests"):
    result = {key: {"input": value} for key, value in input.items()}  
    for input_key, input_value in input.items():
        if not input_value or input_key == "Guid":
            continue

        response = openaire_session.get_items(parameters={ETIS_openaire_map[input_key]: input_value})

        result[input_key]["status"] = response.status_code
        result[input_key]["result"] = []
        if not response:
            continue

        response_json = response.json()
        n_items = int(response_json["response"]["header"]["total"]["$"])
        if n_items == 0:
           continue

        result[input_key]["result"] = [item["metadata"]["oaf:entity"]["oaf:project"]["code"]["$"] for item in response_json["response"]["results"]["result"]]

        n_used_requests = int(response.headers["x-ratelimit-used"])
        n_request_limit = int(response.headers["x-ratelimit-limit"])

        if n_used_requests >= n_request_limit:
            raise RuntimeError("OpenAIRE request limit reached.")

    openaire_results += [result]


openaire_horizon_ids_save_path = f'{RAW_DATA_DIRECTORY_PATH.strip("/")}/openaire_horizon_ids_{get_timestamp_string()}.json'
with open(openaire_horizon_ids_save_path, "w", encoding="utf8") as save_file:
    save_file.write(json.dumps(openaire_results, indent=2, ensure_ascii=False))
