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

RAW_DATA_DIRECTORY_PATH = "./data/raw/"
RESULTS_DATA_DIRECTORY_PATH = "./data/results/"


#########################
# Classes and functions #
#########################

class OpenAireGraphSession(requests.Session):
    """
    Class for requesting info from OpenAIRE graph API.
    https://graph.openaire.eu/docs/apis/graph-api/
    """
    BASE_URL = "https://api.openaire.eu/graph/v3"

    def __init__(self, service: str) -> None:
        super().__init__()
        self.service_URL = f'{self.BASE_URL}/{service}'

    def get_items(self, i_page: int = None, n_per_page: int = None, parameters: dict = None) -> requests.Response:
        """
        Get items from service that the session was initiated with.
        Get page i_page with n_per_page items per page.
        """
        query_parameters = {}
        if i_page:
            query_parameters.update({"page": i_page})
        if n_per_page:
            query_parameters.update({"pageSize": n_per_page})
        if parameters:
            query_parameters.update(parameters)

        URL = f'{self.service_URL}'
        response = self.get(URL, params=query_parameters)
        return response


def limit_rate(last_lap_timestamp: float, requests_per_second_limit: int = 50) -> None:
    """
    Adds sleep to request cycles to adhere to the rate limits.
    Uses monotonic timestamps.
    """
    # Safety margin 0.1 triggers slowing down when request frequency is within 90% of rate limit
    safety_margin = 0.1

    requests_per_second_current = 1 / (time.monotonic() - last_lap_timestamp)
    requests_per_second_limit_safe = requests_per_second_limit * (1 - safety_margin)
    if requests_per_second_current >= requests_per_second_limit_safe:
        time.sleep(1 / requests_per_second_limit)


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


##################################################
# Get OpenAire research products of the articles #
##################################################

# OpenAIRE research products have links to the projects that funded them

# Reload data from save file
articles = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "articles")

openaire_graph_session = OpenAireGraphSession("research-products")

bad_response_threshold = 10         # Throw after this threshold of bad responses (don't spam API)
requests_per_second_limit = 2       # Limit requests that can be made per second to respect API rules (7200 per hour)

bad_responses = []
research_products = []
lap_timestamp = time.monotonic()
for article in tqdm.tqdm(articles, desc="Requesting OpenAire Graph research products"):
    DOI = article["DOI"]
    if not DOI:
        continue

    # Add delay if the pace of the requests is coming close to the API rate limit
    limit_rate(lap_timestamp, requests_per_second_limit)
    lap_timestamp = time.monotonic()
    # Quotes are needed for DOIs with parentheses, e.g. 10.1016/s1473-3099(22)00638-7
    response = openaire_graph_session.get_items(parameters={"pid": f'"{DOI}"'})

    if not response:
        bad_responses += [response]
        if len(bad_responses) >= bad_response_threshold:
            raise ConnectionError(f'Reached bad response threshold: {bad_response_threshold}')
        continue

    research_products += [{
        "GUID": article["GUID"],
        "DOI": DOI,
        "DATA": response.json().get("results") or []
    }]


##################################
# Save research products to file #
##################################

research_products_save_path = f'{RAW_DATA_DIRECTORY_PATH.rstrip("/")}/openaire_research_products_{get_timestamp_string()}.json'
with open(research_products_save_path, "w", encoding="utf8") as save_file:
    save_file.write(json.dumps(research_products, indent=2, ensure_ascii=False))

n_found = len([item for item in research_products if item["DATA"]])
info_string1 = f'OpenAire Graph has research products for {n_found} of the {len(articles)} scientific articles. Saved to {research_products_save_path}'
info_string2 = f'OpenAire Graph API failed to return data for {len(bad_responses)} articles'
logger.info(info_string1)
logger.info(info_string2)
