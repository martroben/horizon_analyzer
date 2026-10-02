# standard
import datetime
import json
import logging
import os
import re
import sys
import time
import unicodedata
import urllib.parse
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

OPENALEX_API_KEY = os.environ.get("OPENALEX_API_KEY")
    # Optional. Without a key, title searches are limited by a $0.10 daily budget ($0.001 per search)
    # A free key raises the budget to $1: https://openalex.org/settings/api
OPENALEX_WORK_FIELDS = [
    "id",
    "doi",
    "ids",
    "title",
    "publication_year",
    "type",
    "is_retracted",
    "open_access",
    "best_oa_location",
    "primary_location",
    "locations",
    "has_content",
    "content_urls",
    "awards",
    "funders"
]

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


class OpenAlexSession(requests.Session):
    """
    Class for requesting info from OpenAlex API.
    https://docs.openalex.org
    Single work lookups are free. Searches are charged against a daily budget.
    """
    BASE_URL = "https://api.openalex.org"

    def __init__(self, API_key: str = None) -> None:
        super().__init__()
        if API_key:
            self.headers.update({"Authorization": f'Bearer {API_key}'})

    def get_work(self, DOI: str, fields: list[str] = None) -> requests.Response:
        """
        Get a single work by DOI. Responds with status 404 if OpenAlex doesn't know the DOI.
        Gives only the listed fields if fields are given.
        """
        query_parameters = {}
        if fields:
            query_parameters.update({"select": ",".join(fields)})

        # DOIs can contain characters that have a special meaning in URL paths (e.g. # or ?)
        URL = f'{self.BASE_URL}/works/doi:{urllib.parse.quote(DOI, safe="/")}'
        response = self.get(URL, params=query_parameters)
        return response

    def search_works_by_title(self, title: str, n: int = 5, fields: list[str] = None) -> requests.Response:
        """
        Get the n works with the most relevant titles.
        Gives only the listed fields if fields are given.
        """
        # Use only lowercase words: commas would separate filters and uppercase AND, OR, NOT are search operators
        search_string = " ".join(re.sub(r"[^\w\s]", " ", title).lower().split())
        query_parameters = {
            "filter": f'title.search:{search_string}',
            "per_page": n
        }
        if fields:
            query_parameters.update({"select": ",".join(fields)})

        URL = f'{self.BASE_URL}/works'
        response = self.get(URL, params=query_parameters)
        return response


def clean_DOI(DOI: str) -> str:
    """
    Removes the leading doi.org URL or DOI:.
    Doesn't URL-encode the DOI - requests encodes query parameters itself.
    """
    DOI = DOI.strip(" ").lower()
    if not DOI:
        return DOI
    if DOI[:4] == "doi:":
        # Drop leading "DOI: "
        DOI = DOI[4:].strip(" ")
    if "doi.org" in DOI:
        # Drop leading http://dx.doi.org/ or https://doi.org/ (ETIS sometimes has an extra slash)
        DOI = re.sub(r"^.+doi.org/[/\s]*", "", DOI)

    return DOI


def normalise_title(title: str) -> str:
    """
    Gives a lowercase title with only words, for comparing titles from different sources.
    """
    title = unicodedata.normalize("NFKC", title)
    title = re.sub(r"<[^<>]+>", " ", title)         # Drop html tags, e.g. <i>
    title = re.sub(r"[^\w\s]", " ", title.lower())
    return " ".join(title.split())


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

    with open(path, encoding="utf8") as read_file:
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
ETIS_projects = []
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

            ETIS_projects += items
            i += items_per_request
            _ = ETIS_progress_bar.update()


ETIS_projects_save_path = f'{RAW_DATA_DIRECTORY_PATH.strip("/")}/etis_projects_{get_timestamp_string()}.json'
with open(ETIS_projects_save_path, "w", encoding="utf8") as save_file:
    save_file.write(json.dumps(ETIS_projects, indent=2, ensure_ascii=False))

info_string = f'Found {len(ETIS_projects)} relevant projects in ETIS. Saved to {ETIS_projects_save_path}'
logger.info(info_string)


################################
# Get project publication info #
################################

# Reload data from save file
ETIS_projects = read_latest_file(RAW_DATA_DIRECTORY_PATH, "etis_projects")

# Parse publications
# Select unique publications (same publications can be reported under several projects)
n_publications = 0
projects_with_no_publications = []
publications_index = {}
for project in ETIS_projects:
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

info_string = f'Found {n_publications} publications under the projects. {len(publications)} of these are unique. {len(projects_with_no_publications)} of the {len(ETIS_projects)} projects have no publications'
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
    publication["DATA"] = {}
    response = ETIS_publication_session.get_items(
        parameters={"Guid": publication["GUID"]}
    )
    if not response:
        bad_responses += [response]
        publications_with_no_data += [publication]
        n_bad_responses += 1
        if n_bad_responses >= bad_response_threshold:
            raise ConnectionError(f'Reached bad response threshold: {bad_response_threshold}')
        continue

    try:
        publication["DATA"] = response.json()[0]
    except Exception as exception:
        publications_with_no_data += [publication]

publications_save_path = f'{RAW_DATA_DIRECTORY_PATH.strip("/")}/publications_{get_timestamp_string()}.json'
with open(publications_save_path, "w", encoding="utf8") as save_file:
    save_file.write(json.dumps(publications, indent=2, ensure_ascii=False))

publications_with_no_data_save_path = f'{RAW_DATA_DIRECTORY_PATH.strip("/")}/publications_with_no_data_{get_timestamp_string()}.json'
with open(publications_with_no_data_save_path, "w", encoding="utf8") as save_file:
    save_file.write(json.dumps(publications_with_no_data, indent=2, ensure_ascii=False))

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
with open(scientific_articles_save_path, "w", encoding="utf8") as save_file:
    save_file.write(json.dumps(scientific_articles, indent=2, ensure_ascii=False))

info_string = f'{len(scientific_articles)} of the {len(publications)} publications are classified as scientific articles. Saved to {scientific_articles_save_path}'
logger.info(info_string)


#######################################
# Pull publication info from OpenAlex #
#######################################

# Reload data from save file
scientific_articles = read_latest_file(RAW_DATA_DIRECTORY_PATH, "scientific_articles")

openalex_session = OpenAlexSession(OPENALEX_API_KEY)

n_bad_responses = 0
bad_response_threshold = 10         # Throw after this threshold of bad responses (don't spam API)
requests_per_second_limit = 10      # Limit requests that can be made per second to respect API rules
title_match_max_year_difference = 1 # Title search results must be published about the same year as given in ETIS

bad_responses = []
openalex_responses = []
n_title_matches = 0
lap_timestamp = time.monotonic()
for publication in tqdm.tqdm(scientific_articles, desc="Requesting publication OpenAlex data"):
    DOI = clean_DOI(publication["DATA"]["Doi"])
    title = publication["DATA"]["Title"]
    year = publication["DATA"]["PublishingYear"]

    openalex_response = {
        "GUID": publication["GUID"],
        "UNSUCCESSFUL_INPUTS": [],
        "SUCCESSFUL_INPUT": None,
        "DATA": None}

    # Search by title only if there is no DOI or OpenAlex doesn't know it - searches cost money
    search_by_title = not DOI
    if DOI:
        # Add delay if the pace of the requests is coming close to the API rate limit
        limit_rate(lap_timestamp, requests_per_second_limit)
        lap_timestamp = time.monotonic()
        response = openalex_session.get_work(DOI, OPENALEX_WORK_FIELDS)

        if response:
            openalex_response["DATA"] = response.json()
            openalex_response["SUCCESSFUL_INPUT"] = DOI
        elif response.status_code == 404:
            openalex_response["UNSUCCESSFUL_INPUTS"] += [DOI]
            search_by_title = True
        else:
            bad_responses += [response]
            n_bad_responses += 1
            if n_bad_responses >= bad_response_threshold:
                raise ConnectionError(f'Reached bad response threshold: {bad_response_threshold}')

    if search_by_title and title:
        limit_rate(lap_timestamp, requests_per_second_limit)
        lap_timestamp = time.monotonic()
        response = openalex_session.search_works_by_title(title, fields=OPENALEX_WORK_FIELDS)

        if not response:
            bad_responses += [response]
            n_bad_responses += 1
            if n_bad_responses >= bad_response_threshold:
                raise ConnectionError(f'Reached bad response threshold: {bad_response_threshold}')
        else:
            # Accept only an unambiguous match: a single work with the same title and publication year
            title_matches = []
            for work in response.json()["results"]:
                if not (work["title"] and work["publication_year"] and year):
                    continue
                if normalise_title(work["title"]) != normalise_title(title):
                    continue
                if abs(work["publication_year"] - year) > title_match_max_year_difference:
                    continue
                title_matches += [work]

            if len(title_matches) == 1:
                openalex_response["DATA"] = title_matches[0]
                openalex_response["SUCCESSFUL_INPUT"] = title
                n_title_matches += 1
            else:
                openalex_response["UNSUCCESSFUL_INPUTS"] += [title]

    openalex_responses += [openalex_response]

openalex_responses_save_path = f'{RAW_DATA_DIRECTORY_PATH.strip("/")}/openalex_responses_{get_timestamp_string()}.json'
with open(openalex_responses_save_path, "w", encoding="utf8") as save_file:
    save_file.write(json.dumps(openalex_responses, indent=2, ensure_ascii=False))

n_found = len([item for item in openalex_responses if item["DATA"]])
info_string1 = f'Checked publication open access status by OpenAlex API. Saved results to {openalex_responses_save_path}'
info_string2 = f'OpenAlex has data for {n_found} of the {len(scientific_articles)} scientific articles ({n_title_matches} found by title search). OpenAlex API failed to return data for {len(bad_responses)} requests'
logger.info(info_string1)
logger.info(info_string2)


##############################
# Summarise open access data #
##############################

# Reload data from save file
openalex_responses = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openalex_responses")
scientific_articles = read_latest_file(RAW_DATA_DIRECTORY_PATH, "scientific_articles")

manually_checked_publications = []
if os.path.exists(MANUALLY_CHECKED_PUBLICATIONS_PATH):
    with open(MANUALLY_CHECKED_PUBLICATIONS_PATH, encoding="utf8") as read_file:
        manually_checked_publications = json.loads(read_file.read())

openalex_responses_index = {item["GUID"]: item for item in openalex_responses}
open_access_manual_check_results_index = {item["GUID"]: item for item in manually_checked_publications}

open_access_data = []
for article in scientific_articles:
    ETIS_data = article["DATA"]
    openalex_response = openalex_responses_index.get(article["GUID"]) or {}
    openalex_data = openalex_response.get("DATA") or {}
    openalex_open_access = openalex_data.get("open_access") or {}
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
        "OPENALEX_ID": openalex_data.get("id"),
        "OPENALEX_DOI": clean_DOI(openalex_data.get("doi") or ""),
        "OPENALEX_IS_OPEN_ACCESS": openalex_open_access.get("is_oa"),
        "OPENALEX_OPEN_ACCESS_TYPE": openalex_open_access.get("oa_status"),
        "OPENALEX_OPEN_ACCESS_URL": openalex_open_access.get("oa_url"),
        "IS_AVAILABLE_MANUALLY_CHECKED": manual_check_result.get("IS_AVAILABLE")
    }
    open_access_data += [open_access_datum]

open_access_data_save_path = f'{RESULTS_DATA_DIRECTORY_PATH.strip("/")}/open_access_data_{get_timestamp_string()}.json'
with open(open_access_data_save_path, "w", encoding="utf8") as save_file:
    save_file.write(json.dumps(open_access_data, indent=2, ensure_ascii=False))

info_string = f'Summarised publication open access data. Saved results to {open_access_data_save_path}'
logger.info(info_string)


########################################
# Check for ambiguous open access data #
########################################

# Reload data from save file
open_access_data = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_access_data")

# A publication has ambiguous open access data if it's ETIS and OpenAlex information doesn't align.

open_access_data_ambiguous = []
for publication in open_access_data:
    # Skip publications where ETIS and OpenAlex info both agree that publication is available
    if publication["IS_OPEN_ACCESS"] and publication["OPENALEX_IS_OPEN_ACCESS"]:
        continue

    # Skip publications where ETIS and OpenAlex info both agree that publication is not available
    if not (publication["IS_OPEN_ACCESS"] or publication["OPENALEX_IS_OPEN_ACCESS"]):
        continue

    # Skip publications that have manually checked availability status
    if publication["IS_AVAILABLE_MANUALLY_CHECKED"] is not None:
        continue

    # All remaining publications have ambiguous open access status
    open_access_data_ambiguous += [publication]

if open_access_data_ambiguous:
    open_access_data_ambiguous_save_path = f'{RESULTS_DATA_DIRECTORY_PATH.strip("/")}/open_access_data_ambiguous_{get_timestamp_string()}.json'
    with open(open_access_data_ambiguous_save_path, "w", encoding="utf8") as save_file:
        save_file.write(json.dumps(open_access_data_ambiguous, indent=2, ensure_ascii=False))

    info_string1 = f'{len(open_access_data_ambiguous)} publications have ambiguous open access status. See details in {open_access_data_ambiguous_save_path}'
    info_string2 = f'You can manually override the publication availability status in {MANUALLY_CHECKED_PUBLICATIONS_PATH}'
    logger.info(info_string1)
    logger.info(info_string2)
