# standard
import datetime
import json
import logging
import os
import re
import sys
# external
import requests
import tqdm


##########
# Inputs #
##########

ETIS_HORIZON_PROGRAMME_CODES = [
    "136",      # Horizon 2020 EIT support
    "137",      # Horisont 2020 ERA \u00f5ppetoolide toetus
    "442",      # Horizon 2020
    "443",      # ERA-NET (Horizon 2020)
    "450",      # Horizon Europe Programme
    "451"       # ERA-NET (Horizon Europe)
]

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
    path = f'{dir_path.rstrip("/")}/{files_latest}'

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


########################################
# Get ETIS Horizon projects to search #
########################################

# Reload data from save file
projects = read_latest_file(RAW_DATA_DIRECTORY_PATH, "etis_projects")

# ETIS project fields to search: field name in the saved searches, ETIS field and OpenAIRE search API parameter
search_fields = {
    "FINANCIER_PROJECT_NUMBER": ("FinancierProjectNr", "grantID"),
    "ACRONYM": ("Acronym", "acronym"),
    "TITLE": ("TitleEng", "name")
}

horizon_projects = [project for project in projects if project["ProgrammeCode"] in ETIS_HORIZON_PROGRAMME_CODES]


#########################
# Request OpenAIRE data #
#########################

openaire_session = OpenAireSession("projects")

project_searches = []
for project in tqdm.tqdm(horizon_projects, desc="OpenAIRE requests"):
    searches = {}
    for field, (ETIS_field, search_parameter) in search_fields.items():
        search = {"QUERY": project[ETIS_field] or None, "STATUS_CODE": None, "HORIZON_IDS": []}
        searches[field] = search
        if not search["QUERY"]:
            continue

        # Horizon projects are funded by European Commission - other funders' projects can have the same codes
        response = openaire_session.get_items(parameters={search_parameter: search["QUERY"], "funder": "EC"})

        search["STATUS_CODE"] = response.status_code
        if not response:
            continue

        response_json = response.json()
        n_items = int(response_json["response"]["header"]["total"]["$"])
        if n_items == 0:
            continue

        search["HORIZON_IDS"] = [item["metadata"]["oaf:entity"]["oaf:project"]["code"]["$"] for item in response_json["response"]["results"]["result"]]

        n_used_requests = int(response.headers["x-ratelimit-used"])
        n_request_limit = int(response.headers["x-ratelimit-limit"])

        if n_used_requests >= n_request_limit:
            raise RuntimeError("OpenAIRE request limit reached.")

    project_searches += [{
        "GUID": project["Guid"],
        "SEARCHES": searches
    }]

project_searches_save_path = f'{RAW_DATA_DIRECTORY_PATH.rstrip("/")}/openaire_project_searches_{get_timestamp_string()}.json'
with open(project_searches_save_path, "w", encoding="utf8") as save_file:
    save_file.write(json.dumps(project_searches, indent=2, ensure_ascii=False))

n_found = len([item for item in project_searches if any(search["HORIZON_IDS"] for search in item["SEARCHES"].values())])
info_string = f'OpenAIRE search API has matches for {n_found} of the {len(project_searches)} ETIS Horizon projects. Saved to {project_searches_save_path}'
logger.info(info_string)
