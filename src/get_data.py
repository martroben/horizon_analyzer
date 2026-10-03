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
from thefuzz import fuzz
import tqdm


##########
# Inputs #
##########

ETIS_SCIENTIFIC_ARTICLES_CLASSIFICATION_CODES = [
    "1.1.",     # Web of Science & Scopus scientific articles
    "1.2.",     # Other international scientific articles
    "1.3."      # scientific articles in Estonian journals
]
ETIS_HORIZON_PROGRAMME_CODES = [
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

OPENALEX_API_KEY_SECRET_NAME = "openalex_api_key"
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
    "funders",
    "authorships"
]
OPENALEX_PEER_REVIEWED_VERSIONS = [
    "publishedVersion",     # Version of record
    "acceptedVersion"       # Peer-reviewed author manuscript
]
    # OpenAlex location versions that count for the Horizon open access mandate: the published version or the peer-reviewed manuscript
    # Open submitted versions (preprints) and open copies of unknown version don't count
ESTONIAN_AFFILIATION_PATTERN = r"estonia|eesti|tallinn|tartu"
    # Raw affiliation strings of Estonian institutions. OpenAlex doesn't link every affiliation to an institution with a country
AUTHOR_SURNAME_SIMILARITY_THRESHOLD = 85
    # ETIS and OpenAlex can spell names differently (e.g. Šogenov - Shogenov). Fuzzy match score of surnames, 0-100
NAME_PARTICLES = ["de", "del", "della", "la", "le", "van", "von", "der", "den", "da", "das", "dos", "di", "du"]

RAW_DATA_DIRECTORY_PATH = "./data/raw/"
RESULTS_DATA_DIRECTORY_PATH = "./data/results/"
MANUALLY_CHECKED_PUBLICATIONS_PATH = "./data/manual/manually_checked_publications.json"
SECRETS_DIRECTORY_PATH = "./secrets/"
    # One file per secret, file name is the secret name. Not committed


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

    def get_work_by_ID(self, openalex_ID: str, fields: list[str] = None) -> requests.Response:
        """
        Get a single work by OpenAlex ID (e.g. https://openalex.org/W2741809807). Free like DOI lookups.
        Gives all authors - search results have at most 100 authors per work.
        Gives only the listed fields if fields are given.
        """
        query_parameters = {}
        if fields:
            query_parameters.update({"select": ",".join(fields)})

        URL = f'{self.BASE_URL}/works/{openalex_ID.rsplit("/", 1)[-1]}'
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


def clean_DOI(DOI: str | None) -> str | None:
    """
    Removes the leading doi.org URL or DOI:. Gives None if there is no DOI.
    Doesn't URL-encode the DOI - requests encodes query parameters itself.
    """
    DOI = (DOI or "").strip(" ").lower()
    if not DOI:
        return None
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


def split_author_name(name: str) -> list[str]:
    """
    Gives the words of an author name in lowercase ASCII, first names first. Hyphenated names are split into words.
    Names can be in "Name Surname" or "Surname, Name" order. Particles (de, van etc.) are left out.
    """
    if "," in name:
        surname, first_names = name.split(",", 1)
        name = f'{first_names} {surname}'
    # Estonian spelling of Russian names, e.g. Semtšenko - Semchenko, Šogenov - Shogenov
    name = name.lower().replace("tš", "ch").replace("š", "sh").replace("ž", "zh")
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return [word for word in re.sub(r"[^a-z\s]", " ", ascii_name).split() if word not in NAME_PARTICLES]


def is_same_author(name: str, other_name: str) -> bool:
    """
    Tells whether two author names are probably the same person: a similar surname and a common initial of the other names.
    Any word after the first one can be the surname, because sources shorten double surnames differently
    (e.g. Ivika Ostonen-Märtin - Ivika Ostonen, Manuel Alejandro Camargo Chavez - Manuel Camargo).
    """
    words = split_author_name(name)
    other_words = split_author_name(other_name)
    for surname in words[1:] or words:
        for other_surname in other_words[1:] or other_words:
            if fuzz.ratio(surname, other_surname) < AUTHOR_SURNAME_SIMILARITY_THRESHOLD:
                continue
            initials = {word[0] for word in words if word != surname}
            other_initials = {word[0] for word in other_words if word != other_surname}
            # Some sources give only the surname
            if not (initials and other_initials) or initials & other_initials:
                return True
    return False


def has_estonian_affiliation(openalex_data: dict) -> bool | None:
    """
    Tells whether an author of an OpenAlex work has an Estonian affiliation.
    Gives None if OpenAlex has no affiliations for the work.
    """
    authorships = openalex_data.get("authorships") or []
    if not any(authorship.get("institutions") or authorship.get("raw_affiliation_strings") for authorship in authorships):
        return None
    for authorship in authorships:
        if "EE" in (authorship.get("countries") or []):
            return True
        for affiliation in authorship.get("raw_affiliation_strings") or []:
            if re.search(ESTONIAN_AFFILIATION_PATTERN, affiliation, flags=re.IGNORECASE):
                return True
    return False


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


def check_bad_response(response: requests.Response, bad_responses: list, bad_response_threshold: int = 10) -> bool:
    """
    Gives True and keeps the response if it's bad. Throws after bad_response_threshold bad responses (don't spam API).
    """
    if response:
        return False
    bad_responses += [response]
    if len(bad_responses) >= bad_response_threshold:
        raise ConnectionError(f'Reached bad response threshold: {bad_response_threshold}. Last response: {response.status_code} {response.url}')
    return True


def get_timestamp_string() -> str:
    """
    Gives a standard current timestamp string to use in filenames.
    """
    timestamp_format = "%Y%m%d%H%M%S%Z"

    timestamp = datetime.datetime.now(datetime.timezone.utc)
    timestamp_string = datetime.datetime.strftime(timestamp, timestamp_format)
    return timestamp_string


def read_secret(dir_path: str, name: str) -> str | None:
    """
    Reads a secret from dir_path. Every secret is in its own file with the secret's name (like secrets mounted in Kubernetes).
    Gives None if there's no file for the secret.
    """
    path = f'{dir_path.rstrip("/")}/{name}'
    if not os.path.exists(path):
        return None

    with open(path, encoding="utf8") as read_file:
        secret = read_file.read().strip()

    return secret or None


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


def save_data(data: list[dict], dir_path: str, file_handle: str) -> str:
    """
    Saves data to dir_path in a file named by file_handle and the current timestamp. Gives the file path.
    """
    save_path = f'{dir_path.rstrip("/")}/{file_handle}_{get_timestamp_string()}.json'
    with open(save_path, "w", encoding="utf8") as save_file:
        save_file.write(json.dumps(data, indent=2, ensure_ascii=False))
    return save_path


#####################
# Environment setup #
#####################

# Create directories
os.makedirs(RAW_DATA_DIRECTORY_PATH, exist_ok=True)
os.makedirs(RESULTS_DATA_DIRECTORY_PATH, exist_ok=True)

# Logger
logger = logging.getLogger()
logger.setLevel("INFO")
logger.addHandler(logging.StreamHandler(sys.stdout))

# Secrets
OPENALEX_API_KEY = read_secret(SECRETS_DIRECTORY_PATH, OPENALEX_API_KEY_SECRET_NAME)
if not OPENALEX_API_KEY:
    logger.info(f'No OpenAlex API key in {SECRETS_DIRECTORY_PATH} - title searches have a $0.10 daily budget')


######################
# Pull ETIS Projects #
######################

ETIS_project_session = EtisSession(service="project")
ETIS_project_parameters = {
    "ProjectStatus": ETIS_FINISHED_PROJECT_STATUS_CODE,
}

items_per_request = 500             # Get items in batches

bad_responses = []
ETIS_projects = []
with tqdm.tqdm() as ETIS_progress_bar:
    _ = ETIS_progress_bar.set_description_str("Requesting ETIS projects")
    for programme_code in ETIS_HORIZON_PROGRAMME_CODES:
        ETIS_project_parameters["ProgrammeCode"] = programme_code
        i = 0
        while True:
            response = ETIS_project_session.get_items(
                n=items_per_request,
                i_start=i,
                parameters=ETIS_project_parameters)

            if check_bad_response(response, bad_responses):
                continue

            items = response.json()
            if not items:
                break

            ETIS_projects += items
            i += items_per_request
            _ = ETIS_progress_bar.update()

ETIS_projects_save_path = save_data(ETIS_projects, RAW_DATA_DIRECTORY_PATH, "etis_projects")

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

bad_responses = []
publications_without_data = []
for publication in tqdm.tqdm(publications, desc="Requesting ETIS publications"):
    publication["DATA"] = {}
    response = ETIS_publication_session.get_items(
        parameters={"Guid": publication["GUID"]}
    )
    if check_bad_response(response, bad_responses):
        publications_without_data += [publication]
        continue

    try:
        publication["DATA"] = response.json()[0]
    except Exception:
        publications_without_data += [publication]

publications_save_path = save_data(publications, RAW_DATA_DIRECTORY_PATH, "etis_publications")
publications_without_data_save_path = save_data(publications_without_data, RAW_DATA_DIRECTORY_PATH, "etis_publications_without_data")

info_string1 = f'Pulled publication data from ETIS. Saved to {publications_save_path}'
info_string2 = f'ETIS API failed to return data for {len(publications_without_data)} of the {len(publications)} publications. See {publications_without_data_save_path} for details'
logger.info(info_string1)
logger.info(info_string2)


###########################
# Get scientific articles #
###########################

# Reload data from save file
publications = read_latest_file(RAW_DATA_DIRECTORY_PATH, "etis_publications")

# Select only already published scientific articles
ETIS_articles = []
for publication in publications:
    if not publication["DATA"]:
        continue
    if publication["DATA"]["ClassificationCode"] not in ETIS_SCIENTIFIC_ARTICLES_CLASSIFICATION_CODES:
        continue
    if publication["DATA"]["PublicationStatusEng"].lower() != "published":
        continue

    ETIS_articles += [publication]

ETIS_articles_save_path = save_data(ETIS_articles, RAW_DATA_DIRECTORY_PATH, "etis_articles")

info_string = f'{len(ETIS_articles)} of the {len(publications)} publications are classified as scientific articles. Saved to {ETIS_articles_save_path}'
logger.info(info_string)


###################################
# Pull article info from OpenAlex #
###################################

# Reload data from save file
ETIS_articles = read_latest_file(RAW_DATA_DIRECTORY_PATH, "etis_articles")

openalex_session = OpenAlexSession(OPENALEX_API_KEY)

requests_per_second_limit = 10      # Limit requests that can be made per second to respect API rules
title_match_max_year_difference = 1 # Title search results must be published about the same year as given in ETIS

bad_responses = []
openalex_works = []
n_title_matches = 0
lap_timestamp = time.monotonic()
for ETIS_article in tqdm.tqdm(ETIS_articles, desc="Requesting article OpenAlex data"):
    DOI = clean_DOI(ETIS_article["DATA"]["Doi"])
    title = ETIS_article["DATA"]["Title"]
    year = ETIS_article["DATA"]["PublishingYear"]

    openalex_work = {
        "GUID": ETIS_article["GUID"],
        "FOUND_BY": None,
        "FAILED_QUERIES": [],
        "DATA": None}

    # Search by title only if there is no DOI or OpenAlex doesn't know it - searches cost money
    search_by_title = not DOI
    if DOI:
        # Add delay if the pace of the requests is coming close to the API rate limit
        limit_rate(lap_timestamp, requests_per_second_limit)
        lap_timestamp = time.monotonic()
        response = openalex_session.get_work(DOI, OPENALEX_WORK_FIELDS)

        if response:
            openalex_work["DATA"] = response.json()
            openalex_work["FOUND_BY"] = "doi"
        elif response.status_code == 404:
            openalex_work["FAILED_QUERIES"] += [DOI]
            search_by_title = True
        else:
            check_bad_response(response, bad_responses)

    if search_by_title and title:
        limit_rate(lap_timestamp, requests_per_second_limit)
        lap_timestamp = time.monotonic()
        response = openalex_session.search_works_by_title(title, fields=OPENALEX_WORK_FIELDS)

        if not check_bad_response(response, bad_responses):
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
                openalex_work["DATA"] = title_matches[0]
                openalex_work["FOUND_BY"] = "title_search"
                n_title_matches += 1
                # Search results have at most 100 authors per work - get the full work by ID
                limit_rate(lap_timestamp, requests_per_second_limit)
                lap_timestamp = time.monotonic()
                response = openalex_session.get_work_by_ID(title_matches[0]["id"], OPENALEX_WORK_FIELDS)
                if response:
                    openalex_work["DATA"] = response.json()
            else:
                openalex_work["FAILED_QUERIES"] += [title]

    openalex_works += [openalex_work]

openalex_works_save_path = save_data(openalex_works, RAW_DATA_DIRECTORY_PATH, "openalex_works")

n_found = len([item for item in openalex_works if item["DATA"]])
info_string1 = f'Checked article open access status by OpenAlex API. Saved results to {openalex_works_save_path}'
info_string2 = f'OpenAlex has data for {n_found} of the {len(ETIS_articles)} scientific articles ({n_title_matches} found by title search). OpenAlex API failed to return data for {len(bad_responses)} requests'
logger.info(info_string1)
logger.info(info_string2)


##########################
# Summarise article data #
##########################

# One record per article. See doc/data_schema.md

# Reload data from save files
openalex_works = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openalex_works")
ETIS_articles = read_latest_file(RAW_DATA_DIRECTORY_PATH, "etis_articles")

manually_checked_publications = []
if os.path.exists(MANUALLY_CHECKED_PUBLICATIONS_PATH):
    with open(MANUALLY_CHECKED_PUBLICATIONS_PATH, encoding="utf8") as read_file:
        manually_checked_publications = json.loads(read_file.read())

openalex_works_index = {item["GUID"]: item for item in openalex_works}
manual_check_results_index = {item["GUID"]: item for item in manually_checked_publications}

articles = []
for ETIS_article in ETIS_articles:
    ETIS_data = ETIS_article["DATA"]
    openalex_work = openalex_works_index.get(ETIS_article["GUID"]) or {}
    openalex_data = openalex_work.get("DATA") or {}
    openalex_open_access = openalex_data.get("open_access") or {}
    openalex_open_versions = None
    openalex_has_open_peer_reviewed_version = None
    if openalex_data:
        openalex_open_versions = sorted({location.get("version") or "unknown" for location in openalex_data.get("locations") or [] if location.get("is_oa")})
        openalex_has_open_peer_reviewed_version = any(version in OPENALEX_PEER_REVIEWED_VERSIONS for version in openalex_open_versions)
    manual_check_result = manual_check_results_index.get(ETIS_article["GUID"]) or {}

    # ETIS authors and institutions are Estonian researchers and institutions. ETIS can list the same one twice
    openalex_author_names = []
    for authorship in openalex_data.get("authorships") or []:
        openalex_author_names += [name for name in (authorship["author"].get("display_name"), authorship.get("raw_author_name")) if name]
    authors = []
    for author in ETIS_data["Authors"] or []:
        if author["Guid"] in [item["GUID"] for item in authors]:
            continue
        authors += [{
            "GUID": author["Guid"],
            "NAME": author["Name"],
            "IS_IN_OPENALEX_AUTHORS": any(is_same_author(author["Name"], name) for name in openalex_author_names) if openalex_author_names else None
        }]
    institutions = []
    for institution in ETIS_data["Institutions"] or []:
        if institution["Guid"] in [item["GUID"] for item in institutions]:
            continue
        institutions += [{
            "GUID": institution["Guid"],
            "NAME": institution["NameEng"] or institution["Name"],
            "REGISTRY_CODE": institution.get("BusinessRegNo") or None     # Business registry code of the legal entity
        }]

    # An article has an Estonian author if an author in the published author list (OpenAlex) has an Estonian affiliation,
    # or if an ETIS author is in the list and ETIS gives an Estonian institution (OpenAlex lacks many affiliations).
    # Without the OpenAlex author list, the Estonian institutions in ETIS decide
    openalex_has_estonian_affiliation = has_estonian_affiliation(openalex_data) if openalex_data else None
    if openalex_has_estonian_affiliation:
        has_estonian_author = True
    elif openalex_author_names:
        has_estonian_author = bool(institutions) and any(author["IS_IN_OPENALEX_AUTHORS"] for author in authors)
    else:
        has_estonian_author = bool(institutions) or None

    ETIS_DOI = clean_DOI(ETIS_data["Doi"])
    openalex_DOI = clean_DOI(openalex_data.get("doi"))
    articles += [{
        "GUID": ETIS_article["GUID"],
        "TITLE": ETIS_data["Title"] or None,
        "PERIODICAL": ETIS_data["Periodical"] or None,
        # Without an ETIS DOI, OpenAlex can only have found the article by title search
        "DOI": ETIS_DOI or openalex_DOI,
        "PROJECT_GUIDS": ETIS_article["PROJECT_GUIDS"],
        "AUTHORS": authors,
        "INSTITUTIONS": institutions,
        "HAS_ESTONIAN_AUTHOR": has_estonian_author,
        "ETIS": {
            "DOI": ETIS_DOI,
            "URL": ETIS_data["Url"] or None,
            "IS_OPEN_ACCESS": ETIS_data["IsOpenAccessEng"].lower() == "yes",
            "OPEN_ACCESS_TYPE": ETIS_data["OpenAccessTypeNameEng"] or None,
            "LICENSE": ETIS_data.get("OpenAccessLicenceNameEng") or None
        },
        "OPENALEX": {
            "ID": openalex_data.get("id"),
            "FOUND_BY": openalex_work.get("FOUND_BY"),
            "DOI": openalex_DOI,
            "IS_OPEN_ACCESS": openalex_open_access.get("is_oa"),
            "OPEN_ACCESS_TYPE": openalex_open_access.get("oa_status"),
            "OPEN_ACCESS_URL": openalex_open_access.get("oa_url"),
            "OPEN_VERSIONS": openalex_open_versions,
            "HAS_OPEN_PEER_REVIEWED_VERSION": openalex_has_open_peer_reviewed_version,
            "HAS_ESTONIAN_AFFILIATION": openalex_has_estonian_affiliation
        },
        "MANUAL_CHECK": {
            # Jan 2025 manual check counted any free version (incl. preprints)
            "IS_OPEN_ACCESS": manual_check_result.get("IS_AVAILABLE")
        }
    }]

articles_save_path = save_data(articles, RESULTS_DATA_DIRECTORY_PATH, "articles")

n_estonian_author = len([item for item in articles if item["HAS_ESTONIAN_AUTHOR"]])
n_no_estonian_author = len([item for item in articles if item["HAS_ESTONIAN_AUTHOR"] is False])
info_string1 = f'Summarised article data. Saved results to {articles_save_path}'
info_string2 = f'{n_estonian_author} of the {len(articles)} articles have an Estonian author, {n_no_estonian_author} don\'t, the rest are unknown'
logger.info(info_string1)
logger.info(info_string2)
