# standard
import datetime
import json
import logging
import os
import re
import sys
import time
import urllib
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
RESULTS_DATA_DIRECTORY_PATH = "./data/results/"
MANUALLY_CHECKED_PUBLICATIONS_PATH = "./data/manual/manually_checked_publications.json"


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


def limit_rate(last_lap_timestamp: float, requests_per_second_limit: int = 50) -> None:
    """
    Adds sleep to request cycles to adher to the rate limits.
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
    path = f'{dir_path.strip("/")}/{files_latest}'

    with open(path) as read_file:
        data = json.loads(read_file.read())
    
    return data


#####################
# Environment setup #
#####################

# Create directories
if not os.path.exists(RAW_DATA_DIRECTORY_PATH):
    os.makedirs(RAW_DATA_DIRECTORY_PATH)

if not os.path.exists(RESULTS_DATA_DIRECTORY_PATH):
    os.makedirs(RESULTS_DATA_DIRECTORY_PATH)

# Logger
logger = logging.getLogger()
logger.setLevel("INFO")
logger.addHandler(logging.StreamHandler(sys.stdout))


######################
# Pull ETIS Projects #
######################

ETIS_project_session = EtisSession(service="project")
ETIS_project_parameters = {
    "ProjectStatus": ETIS_FINISHED_PROJECT_STATUS_CODE,
}

n_bad_responses = 0
bad_response_threshold = 10         # Throw after this threshold of bad responses (don't spam API)
items_per_request = 500             # Get items in batches

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

# Reload data from save file
projects = read_latest_file(RAW_DATA_DIRECTORY_PATH, "projects")

# Parse publications
# Select unique publications (same publications can be reported under several projects)
n_publications = 0
projects_with_no_publications = []
publications_index = {}
for project in projects:
    if not project["Publications"]:
        projects_with_no_publications += [project]
        continue

    project_GUID = project["Guid"]
    for publication in project["Publications"]:
        n_publications += 1
        GUID = publication["Guid"]
        publication_data = publications_index.get(GUID) or {}

        if not publication_data:
            publication_data["GUID"] = GUID
            publication_data["PROJECT_GUIDS"] = []

        publication_data["PROJECT_GUIDS"] += [project_GUID]
        publications_index[GUID] = publication_data

publications = list(publications_index.values())

info_string = f'Found {n_publications} publications under the projects. {len(publications)} of these are unique. {len(projects_with_no_publications)} of the {len(projects)} projects have no publications'
logger.info(info_string)


###################################
# Pull publication info from ETIS #
###################################

ETIS_publication_session = EtisSession(service="publication")

n_bad_responses = 0
bad_response_threshold = 10         # Throw after this threshold of bad responses (don't spam API)

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
info_string2 = f'ETIS API failed to return data for {len(publications_with_no_data)} of the {len(publications)} publications. See {publications_with_no_data_save_path} for details'
logger.info(info_string1)
logger.info(info_string2)


###########################
# Get scientific articles #
###########################

# Reload data from save file
publications = read_latest_file(RAW_DATA_DIRECTORY_PATH, "publications")

# Select only already published scientific articles
scientific_articles = []
for publication in publications:
    if not publication["DATA"]:
        continue
    if not publication["DATA"]["ClassificationCode"] in ETIS_SCIENTIFIC_ARTICLES_CLASSIFICATION_CODES:
        continue
    if not publication["DATA"]["PublicationStatusEng"].lower() == "published":
        continue

    scientific_articles += [publication]

scientific_articles_save_path = f'{RAW_DATA_DIRECTORY_PATH.strip("/")}/scientific_articles_{get_timestamp_string()}.json'
with open(scientific_articles_save_path, "w") as save_file:
    save_file.write(json.dumps(scientific_articles, indent=2))

info_string = f'{len(scientific_articles)} of the {len(publications)} publications are classified as scientific articles. Saved to {scientific_articles_save_path}'
logger.info(info_string)


#################################################
# Pull publication info from Open Access Button #
#################################################

# Reload data from save file
scientific_articles = read_latest_file(RAW_DATA_DIRECTORY_PATH, "scientific_articles")

open_access_button_session = OpenAccessButtonSession()

n_bad_responses = 0
bad_response_threshold = 10         # Throw after this threshold of bad responses (don't spam API)
requests_per_second_limit = 1       # Limit requests that can be made per second to respect API rules

bad_responses = []
oa_button_reponses = []
lap_timestamp = time.monotonic()
for publication in tqdm.tqdm(scientific_articles, desc="Requesting publication Open Access Button data"):
    inputs = [
        clean_DOI(publication["DATA"]["Doi"]),
        publication["DATA"]["Url"],
        publication["DATA"]["Title"]
    ]
    inputs = [input for input in inputs if input]       # Drop null inputs

    oa_button_reponse = {
        "GUID": publication["GUID"],
        "UNSUCCESSFUL_INPUTS": [],
        "SUCCESSFUL_INPUT": None,
        "DATA": None}
    
    for input in inputs:
        # Add delay if the pace of the requests is coming close to the API rate limit
        limit_rate(lap_timestamp, requests_per_second_limit)
        lap_timestamp = time.monotonic()
        response = open_access_button_session.find(input)
        
        if not response:
            bad_responses += [response]
            n_bad_responses += 1
            if n_bad_responses >= bad_response_threshold:
                raise ConnectionError(f'Reached bad response threshold: {bad_response_threshold}')
            continue

        oa_button_reponse["DATA"] = response.json()

        if response.json().get("url"):
            oa_button_reponse["SUCCESSFUL_INPUT"] = input
            break

        oa_button_reponse["UNSUCCESSFUL_INPUTS"] += [input]
    
    oa_button_reponses += [oa_button_reponse]

oa_button_reponses_save_path = f'{RAW_DATA_DIRECTORY_PATH.strip("/")}/oa_button_reponses_{get_timestamp_string()}.json'
with open(oa_button_reponses_save_path, "w") as save_file:
    save_file.write(json.dumps(oa_button_reponses, indent=2))

info_string1 = f'Checked publication open access status by Open Access Button API. Saved results to {oa_button_reponses_save_path}'
info_string2 = f'Open Access Button API failed to return data for {len(bad_responses)} of the {len(scientific_articles)} scientific articles'
logger.info(info_string1)
logger.info(info_string2)


##############################
# Summarise open access data #
##############################

# Reload data from save file
oa_button_reponses = read_latest_file(RAW_DATA_DIRECTORY_PATH, "oa_button_reponses")
scientific_articles = read_latest_file(RAW_DATA_DIRECTORY_PATH, "scientific_articles")

manually_checked_publications = []
if os.path.exists(MANUALLY_CHECKED_PUBLICATIONS_PATH):
    with open(MANUALLY_CHECKED_PUBLICATIONS_PATH) as read_file:
        manually_checked_publications = json.loads(read_file.read())

oa_button_reponses_index = {item["GUID"]: item for item in oa_button_reponses}
open_access_manual_check_results_index = {item["GUID"]: item for item in manually_checked_publications}

open_access_data = []
for article in scientific_articles:
    ETIS_data = article["DATA"]
    oa_button_reponse = oa_button_reponses_index.get(article["GUID"]) or {}
    oa_button_data = oa_button_reponse.get("DATA") or {}
    manual_check_result = open_access_manual_check_results_index.get(article["GUID"]) or {}

    open_access_datum = {
        "GUID": article["GUID"],
        "PROJECT_GUIDS": article["PROJECT_GUIDS"],
        "TITLE": ETIS_data["Title"],
        "PERIODICAL": ETIS_data["Periodical"],
        "DOI": clean_DOI(ETIS_data["Doi"]),
        "URL": ETIS_data["Url"],
        "IS_OPEN_ACCESS": ETIS_data["IsOpenAccessEng"].lower() == "yes",
        "OPEN_ACCESS_TYPE": ETIS_data["OpenAccessTypeNameEng"],
        "LICENSE": ETIS_data.get("OpenAccessLicenceNameEng"),
        "IS_PUBLIC_FILE": ETIS_data["PublicFile"],
        "OA_BUTTON_URL": oa_button_data.get("url"),
        "IS_AVAILABLE_MANUALLY_CHECKED": manual_check_result.get("IS_AVAILABLE")
    }
    open_access_data += [open_access_datum]

open_access_data_save_path = f'{RESULTS_DATA_DIRECTORY_PATH.strip("/")}/open_access_data_{get_timestamp_string()}.json'
with open(open_access_data_save_path, "w") as save_file:
    save_file.write(json.dumps(open_access_data, indent=2))

info_string = f'Summarised publication open access data. Saved results to {open_access_data_save_path}'
logger.info(info_string)


########################################
# Check for ambiguous open access data #
########################################

# Reload data from save file
open_access_data = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_access_data")

# A publication has ambiguous open access data if it's ETIS and Open Access Button information doesn't align.

open_access_data_ambiguous = []
for publication in open_access_data:
    # Publications where ETIS info and Open Access Button info both agree that publication is available
    if publication["IS_OPEN_ACCESS"] and publication["OA_BUTTON_URL"]:
        continue

    # Check for publication where publication is available according to ETIS,
    # but not according to Open Access Button (or vice versa). Skip the ones that don't have that problem
    if not (publication["IS_OPEN_ACCESS"] or publication["OA_BUTTON_URL"]):
        continue

    # Publications with manually checked availability are not ambiguous
    if publication["IS_AVAILABLE_MANUALLY_CHECKED"] is not None:
        continue

    # All remaining publications have some mismatch in ETIS and Open Access Button info
    open_access_data_ambiguous += [publication]

open_access_data_ambiguous_save_path = f'{RESULTS_DATA_DIRECTORY_PATH.strip("/")}/open_access_data_ambiguous_{get_timestamp_string()}.json'
with open(open_access_data_ambiguous_save_path, "w") as save_file:
    save_file.write(json.dumps(open_access_data_ambiguous, indent=2))

info_string1 = f'{len(open_access_data_ambiguous)} publications have ambiguous open access status. See details in {open_access_data_ambiguous_save_path}'
info_string2 = f'You can manually set the publication availability status in {MANUALLY_CHECKED_PUBLICATIONS_PATH}'
logger.info(info_string1)
logger.info(info_string2)
