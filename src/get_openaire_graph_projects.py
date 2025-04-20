# standard
import datetime
import json
import logging
import sys
# external
import requests
import tqdm


##########
# Inputs #
##########

RAW_DATA_DIRECTORY_PATH = "./data/raw/"


#########################
# Classes and functions #
#########################

class OpenAireGraphSession(requests.Session):
    """
    Class for requesting info from OpenAIRE graph API.
    https://graph.openaire.eu/docs/apis/graph-api/
    """
    BASE_URL = "https://api.openaire.eu/graph/v1"

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


def get_timestamp_string() -> str:
    """
    Gives a standard current timestamp string to use in filenames.
    """
    timestamp_format = "%Y%m%d%H%M%S%Z"

    timestamp = datetime.datetime.now(datetime.timezone.utc)
    timestamp_string = datetime.datetime.strftime(timestamp, timestamp_format)
    return timestamp_string


#####################
# Environment setup #
#####################

# Logger
logger = logging.getLogger()
logger.setLevel("INFO")
logger.addHandler(logging.StreamHandler(sys.stdout))


#########################
# Get OpenAire projects #
#########################

openaire_graph_session = OpenAireGraphSession("projects")
openaire_graph_parameters = {
    "relOrganizationCountryCode": "EE",
}

n_bad_responses = 0
bad_response_threshold = 10         # Throw after this threshold of bad responses (don't spam API)
items_per_request = 100             # Get items in batches

projects = []
bad_responses = []
with tqdm.tqdm() as openaire_graph_progress_bar:
    _ = openaire_graph_progress_bar.set_description_str("Requesting OpenAire Graph projects")

    i_page = 1
    while True:
        response = openaire_graph_session.get_items(
            i_page=i_page,
            n_per_page=items_per_request,
            parameters=openaire_graph_parameters)
        
        if not response:
            bad_responses += [response]
            n_bad_responses += 1
            if n_bad_responses >= bad_response_threshold:
                raise ConnectionError(f'Reached bad response threshold: {bad_response_threshold}')
            continue

        items = response.json().get("results")
        if not items:
            break

        projects += items
        i_page += 1
        _ = openaire_graph_progress_bar.update()


#########################
# Save projects to file #
#########################

projects_save_path = f'{RAW_DATA_DIRECTORY_PATH.strip("/")}/openaire_graph_projects_{get_timestamp_string()}.json'
with open(projects_save_path, "w", encoding="utf8") as save_file:
    save_file.write(json.dumps(projects, indent=2, ensure_ascii=False))

info_string = f'Found {len(projects)} relevant projects in OpenAire Graph. Saved to {projects_save_path}'
logger.info(info_string)
