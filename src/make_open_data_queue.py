# standard
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
    # Random sample of 20 articles (seed 1913) that was selected for manual open data checks in Jan 2025
    # These come first in the queue, because some of them have reference results from the manual checks
OPENAIRE_GRANT_ID_PREFIXES = ["corda__h2020::", "corda_____he::"]
    # OpenAIRE ID prefixes of Horizon 2020 and Horizon Europe grants
PREPRINT_URL_PATTERN = r"arxiv\.org|biorxiv\.org|medrxiv\.org|chemrxiv\.org|techrxiv\.org|10\.36227/techrxiv|ssrn\.com|preprints\.org|researchsquare\.com|mpra\.ub\.uni-muenchen\.de"
    # Preprint servers and working paper archives. OpenAIRE doesn't always give them the instance type Preprint
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


def is_preprint(openaire_instance: dict) -> bool:
    """
    Tells whether an OpenAIRE open instance is a preprint: instance type Preprint or a preprint server.
    """
    if openaire_instance["TYPE"] == "Preprint":
        return True
    return bool(re.search(PREPRINT_URL_PATTERN, openaire_instance["URL"], flags=re.IGNORECASE))


def get_automatic_open_access(article: dict, openaire_open_instances: list[dict]) -> tuple[str | None, str | None]:
    """
    Gives the automatic open access verdict of an article (open, not_open) by ETIS, OpenAlex and the Jan 2025 manual check,
    and the code of the reason why the full text check has to settle it (codes in doc/data_schema.md). The verdict is None if the full text check has to settle it.
    Open access follows the Horizon mandate: the published version or the peer-reviewed author manuscript is free to read.
    openaire_open_instances: open copies in OpenAIRE that OpenAlex doesn't list.
    """
    ETIS_is_open_access = bool(article["ETIS"]["IS_OPEN_ACCESS"])
    openalex_has_open_peer_reviewed_version = bool(article["OPENALEX"]["HAS_OPEN_PEER_REVIEWED_VERSION"])
    manual_check_is_open_access = article["MANUAL_CHECK"]["IS_OPEN_ACCESS"]
    if manual_check_is_open_access is None:
        if ETIS_is_open_access != openalex_has_open_peer_reviewed_version:
            return None, "etis_openalex_disagree"
        is_open = ETIS_is_open_access
    else:
        # Jan 2025 manual checks counted any free version (incl. preprints)
        if manual_check_is_open_access and not openalex_has_open_peer_reviewed_version:
            return None, "manual_check_any_version"
        is_open = manual_check_is_open_access

    # Horizon projects often deposit accepted manuscripts in repositories (e.g. Zenodo) that OpenAlex doesn't know
    repository_copies = [instance for instance in openaire_open_instances if not is_preprint(instance)]
    if not is_open and repository_copies:
        return None, "openaire_copy_not_in_openalex"
    return "open" if is_open else "not_open", None


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

# The queue has everything that is known automatically about each article: the analysis and Claude's open data check
# (see .claude/skills/check-open-data) use it. See doc/data_schema.md

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

    # OpenAIRE knows many repository copies that OpenAlex doesn't (e.g. accepted manuscripts that Horizon projects upload to Zenodo)
    known_URLs = {normalise_URL(location[key]) for location in openalex_data.get("locations") or [] for key in ("pdf_url", "landing_page_url") if location.get(key)}
    if article["DOI"]:
        known_URLs.add(normalise_URL(f'https://doi.org/{article["DOI"]}'))
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

    automatic_verdict, check_needed_reason = get_automatic_open_access(article, openaire_open_instances)

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
            "CHECK_NEEDED_REASON": check_needed_reason,
            "ETIS": {
                "IS_OPEN_ACCESS": article["ETIS"]["IS_OPEN_ACCESS"],
                "OPEN_ACCESS_TYPE": article["ETIS"]["OPEN_ACCESS_TYPE"],
                "LICENSE": article["ETIS"]["LICENSE"],
                "URL": article["ETIS"]["URL"]
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

# Pilot articles first, then the rest by GUID. ETIS GUIDs are random (UUID version 4), so the GUID order is a random order:
# any number of checked articles is a random sample. Added articles get a random place, the others keep their order
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
logger.info(info_string1)
logger.info(info_string2)
