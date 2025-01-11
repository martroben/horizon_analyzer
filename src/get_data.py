# standard
import datetime
import json
import logging
import os
import re
import time
import urllib
# external
import requests
import tqdm


##########
# Inputs #
##########

ETIS_SCIENTIFIC_ARTICLES_CLASSIFICATION_CODES = ["1.1.", "1.2.", "1.3."]
    # 1.1. - Web of Science & Scopus scientific articles
    # 1.2. - Other international scientific articles
    # 1.3. - scientific articles in Estonian journals
ETIS_HORIZON_PROGRAM_CODES = ["136", "137", "442", "443", "450", "451"]
    # 136 - Horizon 2020 EIT support
    # 137 - Horisont 2020 ERA \u00f5ppetoolide toetus
    # 442 - Horizon 2020
    # 443 - ERA-NET (Horizon 2020)
    # 450 - Horizon Europe Programme
    # 451 - ERA-NET (Horizon Europe)
ETIS_FINISHED_PROJECT_STATUS_CODE = 3
    # 1 - all projects
    # 2 - ongoing projects
    # 3 - finished projects


#########################
# Classes and functions #
#########################

class EtisSession(requests.Session):
    """
    Class for requesting info from ETIS API.
    """
    # https://www.etis.ee:2346/api - test
    # https://www.etis.ee:7443/api - live
    BASE_URL = "https://www.etis.ee:7443/api"

    def __init__(self, service: str) -> None:
        super().__init__()
        self.service_URL = f'{self.BASE_URL}/{service}'

    def get_items(self, n: int = 1, i_start: int = None, parameters: dict = None) -> requests.Response:
        """
        Get items from service that the session was initiated with.
        Start from item i and request n items.
        """
        endpoint = "getitems"
        query_parameters = {
            "Format": "json",
            "Take": n,
        }
        if i_start:
            query_parameters.update({"Skip": i_start})
        if parameters:
            query_parameters.update(parameters)

        URL = f'{self.service_URL}/{endpoint}'
        response = self.get(URL, params=query_parameters)
        return response


class OpenAccessButtonSession(requests.Session):
    """
    Class for requesting info from Open Access Button API.
    https://openaccessbutton.org/api
    """
    BASE_URL = "https://api.openaccessbutton.org"

    def __init__(self, API_key: str = None) -> None:
        super().__init__()
        self.API_key = API_key

    def find(self, ID: str) -> requests.Response:
        """
        Gives URL to any Open Access paper.
        Accepts a single parameter called "id", which should contain (in order of preference)
        a URL-encoded doi, pmc, pmid, url, title, or citation.
        """
        query_parameters = {
            "id": ID
        }
        URL = f'{self.BASE_URL}/find'
        response = self.get(URL, params=query_parameters)
        return response


def clean_DOI(DOI: str) -> str:
    """
    Removes the leading doi.org URL or DOI:.
    URL-encodes the DOI.
    """
    DOI = DOI.strip(" ").lower()
    if not DOI:
        return DOI
    if DOI[:4] == "doi:":
        # Drop leading "DOI: "
        DOI = DOI[4:].strip(" ")
    if "doi.org" in DOI:
        # Drop leading http://dx.doi.org/ or https://doi.org/
        DOI = re.sub(r"^.+doi.org/\s*", "", DOI)
        
    URL_safe_DOI = urllib.parse.quote(DOI)
    return URL_safe_DOI


def limit_rate(last_lap_timestamp: float, requests_per_interval: int = 50, interval_s: int = 1) -> None:
    """
    Adds sleep to request cycles to adher to the rate limits.
    E.g. requests_per_interval = 1, interval = 10: 1 request per 10 seconds.
    Takes the end timestamp of the last cycle and limit information from the request response headers.
    Uses monotonic timestamps.
    """
    # Safety margin 0.1 triggers slowing down when request frequency is within 90% of rate limit
    safety_margin = 0.1

    requests_per_second_current = 1 / (time.monotonic() - last_lap_timestamp)
    requests_per_second_limit = requests_per_interval / interval_s * (1 - safety_margin)
    if requests_per_second_current >= requests_per_second_limit:
        time.sleep(interval_s / requests_per_interval)


def get_timestamp_string() -> str:
    """
    Gives a standard current timestamp string to use in filenames.
    """
    timestamp_format = "%Y%m%d%H%M%S%Z"

    timestamp = datetime.datetime.now(datetime.timezone.utc)
    timestamp_string = datetime.datetime.strftime(timestamp, timestamp_format)
    return timestamp_string


#########
# Setup #
#########

# Save directories
RAW_DATA_DIRECTORY_PATH = "./data/raw/"
if not os.path.exists(RAW_DATA_DIRECTORY_PATH):
    os.makedirs(RAW_DATA_DIRECTORY_PATH)

# Logger
logger = logging.getLogger()
logger.setLevel("INFO")


######################
# Pull ETIS Projects #
######################

ETIS_project_session = EtisSession(service="project")
ETIS_project_parameters = {
    "ProjectStatus": ETIS_FINISHED_PROJECT_STATUS_CODE,
}

items_per_request = 500             # Get items in batches
bad_response_threshold = 10         # Throw after this threshold of bad responses (don't spam API)
n_bad_responses = 0
bad_responses = []
projects = []

with tqdm.tqdm() as ETIS_progress_bar:
    _ = ETIS_progress_bar.set_description_str("Requesting ETIS projects")
    for program_code in ETIS_HORIZON_PROGRAM_CODES:
        ETIS_project_parameters["ProgrammeCode"] = program_code
        i = 0
        while True:
            response = ETIS_project_session.get_items(
                n=items_per_request,
                i_start=i,
                parameters=ETIS_project_parameters)
            
            if not response:
                bad_responses += [response]
                n_bad_responses += 1
                if n_bad_responses >= bad_response_threshold:
                    raise ConnectionError(f'Reached bad response threshold: {bad_response_threshold}')
                continue

            items = response.json()
            if not items:
                break

            projects += items
            i += items_per_request
            _ = ETIS_progress_bar.update()


projects_save_path = f'{RAW_DATA_DIRECTORY_PATH.strip("/")}/projects_{get_timestamp_string()}.json'
with open(projects_save_path, "w") as save_file:
    save_file.write(json.dumps(projects, indent=2))

info_string = f'Found {len(projects)} relevant projects in ETIS. Saved to {projects_save_path}'
logger.info(info_string)


################################
# Get project publication info #
################################

# Reload data from latest save file
projects_save_file_pattern = r'projects_(\d{14})'
projects_save_files = [file for file in os.listdir(RAW_DATA_DIRECTORY_PATH) if re.match(projects_save_file_pattern, file)]
projects_save_files_latest = sorted(projects_save_files, key=lambda x: re.match(projects_save_file_pattern, x).groups()[0])[-1]
projects_save_path = f'{RAW_DATA_DIRECTORY_PATH.strip("/")}/{projects_save_files_latest}'

with open(projects_save_path) as read_file:
    projects = json.loads(read_file.read())

# Parse publications
projects_with_no_publications = []
publications = []
for project in projects:
    if not project["Publications"]:
        projects_with_no_publications += [project]
        continue

    for publication in project["Publications"]:
        publication_data = {}
        publication_data["PROJECT_GUID"] = project["Guid"]
        publication_data["GUID"] = publication["Guid"]

        publications += [publication_data]

info_string = f'Found {len(publications)} publications under the projects. {len(projects_with_no_publications)} of the {len(projects)} projects have no publications'
logger.info(info_string)


###################################
# Pull publication info from ETIS #
###################################

ETIS_publication_session = EtisSession(service="publication")

bad_response_threshold = 10         # Throw after this threshold of bad responses (don't spam API)
n_bad_responses = 0
bad_responses = []
publications_with_no_data = []
for publication in tqdm.tqdm(publications, desc="Requesting ETIS publications"):
    response = ETIS_publication_session.get_items(
        parameters={"Guid": publication["GUID"]}
    )
    if not response:
        bad_responses += [response]
        n_bad_responses += 1
        if n_bad_responses >= bad_response_threshold:
            raise ConnectionError(f'Reached bad response threshold: {bad_response_threshold}')
        continue

    publication["DATA"] = {}
    try:
        publication["DATA"] = response.json()[0]
    except Exception as exception:
        publications_with_no_data += [publication]

publications_save_path = f'{RAW_DATA_DIRECTORY_PATH.strip("/")}/publications_{get_timestamp_string()}.json'
with open(publications_save_path, "w") as save_file:
    save_file.write(json.dumps(publications, indent=2))

publications_with_no_data_save_path = f'{RAW_DATA_DIRECTORY_PATH.strip("/")}/publications_with_no_data_{get_timestamp_string()}.json'
with open(publications_with_no_data_save_path, "w") as save_file:
    save_file.write(json.dumps(publications_with_no_data, indent=2))

info_string1 = f'Pulled publication data from ETIS. Saved to {publications_save_path}'
info_string2 = f'ETIS API did not return data for {len(publications_with_no_data)} of the {len(publications)} publications. See {publications_with_no_data_save_path} for details'
logger.info(info_string1)
logger.info(info_string2)


########################
# Get open access info #
########################

# Select only scientific publications
scientific_articles = []
for publication in project_publications:
    if not publication["DATA"]:
        continue
    if not publication["DATA"]["ClassificationCode"] in ETIS_SCIENTIFIC_ARTICLES_CLASSIFICATION_CODES:
        continue
    scientific_articles += [publication]

# Parse publication open access info
publication_open_access_info = []
for publication in scientific_articles:
    data = publication["DATA"]
    open_access_data = {
        "GUID": publication["GUID"],
        "PROJECT_GUID": publication["PROJECT_GUID"],
        "TITLE": data["Title"],
        "PERIODICAL": data["Periodical"],
        "DOI": clean_DOI(data["Doi"]),
        "URL": data["Url"],
        "IS_OPEN_ACCESS": data["IsOpenAccessEng"].lower() == "yes",
        "OPEN_ACCESS_TYPE": data["OpenAccessTypeNameEng"],
        "LICENSE": data.get("OpenAccessLicenceNameEng"),
        "IS_PUBLIC_FILE": data["PublicFile"]
    }
    publication_open_access_info += [open_access_data]


# Pull open access info from Open Access Button
open_access_button_session = OpenAccessButtonSession()

lap_timestamp = time.monotonic()
for publication in tqdm.tqdm(publication_open_access_info, desc="Requesting publication Open Access Button data"):
    ID = publication["DOI"] or publication["URL"] or publication["TITLE"]
    response = open_access_button_session.find(ID)

    if not response:
        bad_responses += [response]
        publication["DATA"] = {}
    else:
        publication["DATA"] = response.json()

    # Add delay if the pace of the requests is coming close to the API rate limit
    limit_rate(
        last_lap_timestamp=lap_timestamp,
        requests_per_interval=1,
        interval_s=1
    )
    lap_timestamp = time.monotonic()


with open("publication_open_access_info.json", "w") as save_file:
    save_file.write(json.dumps(publication_open_access_info, indent=2))


false_open_access_publications = []
for publication in publication_open_access_info:
    # Publications where ETIS info and Open Access Button info both agree that publication is available
    if publication["IS_OPEN_ACCESS"] and publication["DATA"].get("url"):
        continue

    # Check for publication where publication is available according to ETIS,
    # but not according to Open Access Button (or vice versa). Skip the ones that don't have that problem
    if not (publication["IS_OPEN_ACCESS"] or publication["DATA"].get("url")):
        continue

    # All remaining publications have some mismatch in ETIS and Open Access Button info
    false_open_access_publications += [publication]


with open("false_open_access_publications.json", "w") as save_file:
    save_file.write(json.dumps(false_open_access_publications, indent=2))


##############################
# Summarise open access info #
##############################

with open("./data/publications_manually_checked_20241215.json") as read_file:
    publications_manually_checked = json.loads(read_file.read())

with open("./data/publication_open_access_info_20241215.json") as read_file:
    publication_open_access_info = json.loads(read_file.read())

publications_manually_checked_index = {
    publication["PUBLICATION_GUID"]: {"IS_AVAILABLE_MANUALLY_CHECKED": publication["IS_AVAILABLE_MANUALLY_CHECKED"]}
    for publication in publications_manually_checked}

n_open = 0

for publication in publication_open_access_info:
    manually_checked_info = publications_manually_checked_index.get(publication["GUID"])
    if manually_checked_info:
        if manually_checked_info["IS_AVAILABLE_MANUALLY_CHECKED"]:
            n_open += 1
        continue

    if publication["IS_OPEN_ACCESS"] and publication["DATA"].get("url"):
        n_open += 1
        continue


