# standard
import collections
import datetime
import json
import logging
import os
import re
import sys


##########
# Inputs #
##########

PILOT_GUIDS_PATH = "./data/manual/manual_check_guids_20250118112133UTC.txt"
    # Random sample of 20 articles (seed 1913) for the Jan 2025 manual open data checks. First in the queue
OPENAIRE_GRANT_ID_PREFIXES = ["corda__h2020::", "corda_____he::"]
    # OpenAIRE ID prefixes of Horizon 2020 and Horizon Europe grants
PUBLISHER_OPEN_ACCESS_TYPES = ["gold", "diamond", "hybrid", "bronze"]
    # OpenAlex oa_status values of articles that are free to read on the publisher site (green: only elsewhere)
ABSTRACT_DATABASE_URL_PATTERN = r"scopus\.com|webofscience\.com|webofknowledge\.com"
    # OpenAIRE marks some abstract database records open, but they are not copies of the article

RAW_DATA_DIRECTORY_PATH = "./data/raw/"
RESULTS_DATA_DIRECTORY_PATH = "./data/results/"


#########################
# Classes and functions #
#########################

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


def normalise_URL(URL: str) -> str:
    """
    Gives a URL in lower case without scheme, www. and trailing slash, to compare URLs.
    """
    return re.sub(r"^https?://(dx\.)?(www\.)?", "", URL.strip().lower()).rstrip("/")


def get_ETIS_link_status(article: dict, open_URLs: set[str], openalex_URLs: set[str], fulltext_attempts: list[dict]) -> str | None:
    """
    Tells whether ETIS links to a free copy of the article: open (a free copy in OpenAlex or OpenAIRE, or get_fulltext got the full text from an ETIS link),
    closed (only links to the DOI or OpenAlex locations that aren't free), unverified (a link that no source knows), None (no link).
    open_URLs, openalex_URLs: normalised URLs of the free copies and of all OpenAlex locations and the DOI.
    """
    ETIS_URLs = [normalise_URL(URL) for URL in (article["ETIS"]["URL"], article["ETIS"]["FULLTEXT_URL"]) if URL]
    if not ETIS_URLs:
        return None
    if any(URL in open_URLs for URL in ETIS_URLs) or any(attempt["SOURCE"] == "etis" and attempt["RESULT"] == "ok" for attempt in fulltext_attempts):
        return "open"
    if all(URL in openalex_URLs for URL in ETIS_URLs):
        return "closed"
    return "unverified"


def get_automatic_open_access(article: dict, ETIS_link_status: str | None, fulltext_attempts: list[dict]) -> tuple[str | None, str | None, str | None]:
    """
    Gives the automatic open access verdict of an article (open, not_open; None if the full text check has to settle it),
    the source that the verdict rests on, and the reason why the full text check has to settle it (codes in doc/data_schema.md).
    Open access: free to read on the publisher site (DOI) or through a link in ETIS (any version).
    """
    manual_open_results = {attempt["RESULT"] for attempt in fulltext_attempts if attempt["SOURCE"] == "manual_open"}
    is_publisher_open = article["OPENALEX"]["OPEN_ACCESS_TYPE"] in PUBLISHER_OPEN_ACCESS_TYPES
    ETIS_is_open_access = bool(article["ETIS"]["IS_OPEN_ACCESS"])
    manual_check_is_open_access = article["MANUAL_CHECK"]["IS_OPEN_ACCESS"]
    is_found_closed_by_hand = "not_found" in manual_open_results or manual_check_is_open_access is False

    if "ok" in manual_open_results:
        return "open", "manual_open", None
    if is_publisher_open and (ETIS_is_open_access or manual_check_is_open_access) and not is_found_closed_by_hand:
        return "open", "openalex_publisher", None
    if ETIS_link_status == "open":
        return "open", "etis_link", None
    if is_publisher_open:
        return None, None, "manual_check_disagrees" if is_found_closed_by_hand else "etis_openalex_disagree"
    if ETIS_link_status == "unverified":
        return None, None, "etis_link_unverified"
    if "not_found" in manual_open_results:
        return "not_open", "manual_not_found", None
    if ETIS_is_open_access:
        return None, None, "etis_openalex_disagree"
    # Jan 2025 manual checks counted any free version anywhere
    if manual_check_is_open_access:
        return None, None, "manual_check_any_version"
    if manual_check_is_open_access is False:
        return "not_open", "manual_check", None
    return "not_open", "etis_and_openalex", None


def get_linked_horizon_IDs(research_products: list[dict], openalex_data: dict) -> set[str]:
    """
    Gives the Horizon grants that an article links to: OpenAIRE research product project links and OpenAlex awards.
    """
    horizon_IDs = set()
    for research_product in research_products:
        for project_link in research_product.get("projects") or []:
            if project_link["id"].startswith(tuple(OPENAIRE_GRANT_ID_PREFIXES)):
                horizon_IDs.add(project_link["code"])
    for award in openalex_data.get("awards") or []:
        # Award IDs are free text, e.g. "ePerMed (grant no. 692145)"
        horizon_IDs.update(re.findall(r"\b\d{6,9}\b", award["funder_award_id"] or ""))
    return horizon_IDs


#####################
# Environment setup #
#####################

# Logger
logger = logging.getLogger()
logger.setLevel("INFO")
logger.addHandler(logging.StreamHandler(sys.stdout))


########################
# Make open data queue #
########################

# One record per article, in check order. See doc/data_schema.md

# Reload data from save files
articles = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "articles")
projects = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "projects")
open_data_candidates = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_data_candidates")
grant_datasets = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "grant_datasets")
fulltext_index = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "fulltext_index")
openalex_works = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openalex_works")
openaire_research_products = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openaire_research_products")

with open(PILOT_GUIDS_PATH, encoding="utf8") as read_file:
    pilot_GUIDs = [line.strip() for line in read_file if line.strip()]

projects_index = {item["GUID"]: item for item in projects}
open_data_candidates_index = {item["GUID"]: item for item in open_data_candidates}
grant_datasets_index = {item["HORIZON_ID"]: item for item in grant_datasets}
fulltext_index_index = {item["GUID"]: item for item in fulltext_index}
openalex_works_index = {item["GUID"]: item for item in openalex_works}
openaire_research_products_index = {item["GUID"]: item["DATA"] for item in openaire_research_products}

queue = []
for article in articles:
    article_projects = [projects_index[GUID] for GUID in article["PROJECT_GUIDS"] if GUID in projects_index]
    candidates = open_data_candidates_index.get(article["GUID"]) or {}
    fulltext = fulltext_index_index.get(article["GUID"]) or {}
    openalex_data = (openalex_works_index.get(article["GUID"]) or {}).get("DATA") or {}

    open_locations = []
    for location in openalex_data.get("locations") or []:
        if not location.get("is_oa"):
            continue
        open_locations += [{
            "VERSION": location.get("version"),
            "URL": location.get("pdf_url") or location.get("landing_page_url"),
            "HOST": (location.get("source") or {}).get("display_name"),
            "HOST_TYPE": (location.get("source") or {}).get("type"),
            "LICENSE": location.get("license")
        }]

    # Open copies in OpenAIRE that OpenAlex doesn't list
    openalex_URLs = {normalise_URL(location[key]) for location in openalex_data.get("locations") or [] for key in ("pdf_url", "landing_page_url") if location.get(key)}
    if article["DOI"]:
        openalex_URLs.add(normalise_URL(f'https://doi.org/{article["DOI"]}'))
    known_URLs = set(openalex_URLs)
    research_products = openaire_research_products_index.get(article["GUID"]) or []
    openaire_open_instances = []
    for research_product in research_products:
        for instance in research_product.get("instances") or []:
            if (instance.get("accessRight") or {}).get("label") != "OPEN":
                continue
            for URL in instance.get("urls") or []:
                if normalise_URL(URL) in known_URLs or re.search(ABSTRACT_DATABASE_URL_PATTERN, URL, flags=re.IGNORECASE):
                    continue
                known_URLs.add(normalise_URL(URL))
                openaire_open_instances += [{
                    "URL": URL,
                    "HOST": (instance.get("hostedBy") or {}).get("value"),
                    "TYPE": instance.get("type")
                }]

    # Free copies: open OpenAlex locations, open OpenAIRE copies and links that get_fulltext got a full text from
    fulltext_attempts = fulltext.get("ATTEMPTS") or []
    open_URLs = {normalise_URL(location[key]) for location in openalex_data.get("locations") or [] if location.get("is_oa") for key in ("pdf_url", "landing_page_url") if location.get(key)}
    open_URLs |= {normalise_URL(instance["URL"]) for instance in openaire_open_instances}
    open_URLs |= {normalise_URL(attempt["URL"]) for attempt in fulltext_attempts if attempt["RESULT"] == "ok" and attempt["URL"]}
    ETIS_link_status = get_ETIS_link_status(article, open_URLs, openalex_URLs, fulltext_attempts)
    automatic_verdict, automatic_verdict_source, check_needed_reason = get_automatic_open_access(article, ETIS_link_status, fulltext_attempts)

    # Articles don't always acknowledge the ETIS project's grant. Unknown if neither OpenAIRE nor OpenAlex has the article
    linked_horizon_IDs = get_linked_horizon_IDs(research_products, openalex_data)
    has_grant_link_data = bool(research_products or openalex_data)

    queue += [{
        "GUID": article["GUID"],
        "TITLE": article["TITLE"],
        "PERIODICAL": article["PERIODICAL"],
        "DOI": article["DOI"],
        "ETIS_PAGE_URL": f'https://www.etis.ee/Portal/Publications/Display/{article["GUID"]}',
        "HAS_ESTONIAN_AUTHOR": article["HAS_ESTONIAN_AUTHOR"],
        "AUTHORS": article["AUTHORS"],
        "INSTITUTIONS": article["INSTITUTIONS"],
        "PROJECTS": [{
            "GUID": project["GUID"],
            "TITLE": project["TITLE"],
            "PROGRAMME_CODES": project["PROGRAMME_CODES"],
            "FRAMEWORK_PROGRAMME": project["FRAMEWORK_PROGRAMME"],
            "HORIZON_ID": project["HORIZON_ID"],
            "ACRONYM": project["ACRONYM"],
            "HAS_PUBLICATION_MANDATE": project["HAS_PUBLICATION_MANDATE"],
            "HAS_DATA_MANDATE": project["HAS_DATA_MANDATE"],
            "IS_GRANT_LINKED": project["HORIZON_ID"] in linked_horizon_IDs if project["HORIZON_ID"] and has_grant_link_data else None,
            "N_GRANT_DATASETS": (grant_datasets_index.get(project["HORIZON_ID"]) or {}).get("N_DATASETS")
        } for project in article_projects],
        "OPEN_ACCESS": {
            "AUTOMATIC_VERDICT": automatic_verdict,
            "AUTOMATIC_VERDICT_SOURCE": automatic_verdict_source,
            "CHECK_NEEDED_REASON": check_needed_reason,
            "ETIS": {
                "IS_OPEN_ACCESS": article["ETIS"]["IS_OPEN_ACCESS"],
                "OPEN_ACCESS_TYPE": article["ETIS"]["OPEN_ACCESS_TYPE"],
                "LICENSE": article["ETIS"]["LICENSE"],
                "URL": article["ETIS"]["URL"],
                "FULLTEXT_URL": article["ETIS"]["FULLTEXT_URL"]
            },
            "OPENALEX": {
                "IS_OPEN_ACCESS": article["OPENALEX"]["IS_OPEN_ACCESS"],
                "OPEN_ACCESS_TYPE": article["OPENALEX"]["OPEN_ACCESS_TYPE"],
                "HAS_OPEN_PEER_REVIEWED_VERSION": article["OPENALEX"]["HAS_OPEN_PEER_REVIEWED_VERSION"],
                "OPEN_LOCATIONS": open_locations
            },
            "OPENAIRE": {
                "OPEN_INSTANCES": openaire_open_instances
            },
            "MANUAL_CHECK": article["MANUAL_CHECK"]
        },
        "CANDIDATES": {key: value for key, value in candidates.items() if key not in ("GUID", "DOI")},
        "FULLTEXT": {key: value for key, value in fulltext.items() if key not in ("GUID", "DOI")}
    }]

# Pilot articles first, then the rest by GUID (ETIS GUIDs are random, so this is a random order)
queue_index = {item["GUID"]: item for item in queue}
other_GUIDs = sorted(GUID for GUID in queue_index if GUID not in pilot_GUIDs)
queue_ordered = []
for i, GUID in enumerate([GUID for GUID in pilot_GUIDs if GUID in queue_index] + other_GUIDs, start=1):
    queue_ordered += [{"QUEUE_POSITION": i, "IS_PILOT": GUID in pilot_GUIDs, **queue_index[GUID]}]

queue_save_path = f'{RESULTS_DATA_DIRECTORY_PATH.rstrip("/")}/open_data_queue_{get_timestamp_string()}.json'
with open(queue_save_path, "w", encoding="utf8") as save_file:
    save_file.write(json.dumps(queue_ordered, indent=2, ensure_ascii=False))

n_fulltext = len([item for item in queue_ordered if item["FULLTEXT"].get("TEXT_FILE")])
n_open_access_check = len([item for item in queue_ordered if item["OPEN_ACCESS"]["CHECK_NEEDED_REASON"]])
n_no_estonian_author = len([item for item in queue_ordered if item["HAS_ESTONIAN_AUTHOR"] is False])
info_string1 = f'Saved open data queue of {len(queue_ordered)} articles ({len([item for item in queue_ordered if item["IS_PILOT"]])} pilot articles first) to {queue_save_path}'
info_string2 = f'{n_fulltext} articles have a cached full text. {n_open_access_check} articles need an open access check. {n_no_estonian_author} articles have no Estonian author and are skipped by next_open_data_batch'
info_string3 = f'Automatic open access verdicts by source: {dict(collections.Counter((item["OPEN_ACCESS"]["AUTOMATIC_VERDICT"], item["OPEN_ACCESS"]["AUTOMATIC_VERDICT_SOURCE"]) for item in queue_ordered if item["OPEN_ACCESS"]["AUTOMATIC_VERDICT"]))}'
info_string4 = f'Open access checks needed by reason: {dict(collections.Counter(item["OPEN_ACCESS"]["CHECK_NEEDED_REASON"] for item in queue_ordered if item["OPEN_ACCESS"]["CHECK_NEEDED_REASON"]))}'
logger.info(info_string1)
logger.info(info_string2)
logger.info(info_string3)
logger.info(info_string4)
