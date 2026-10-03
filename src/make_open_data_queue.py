# standard
import datetime
import json
import logging
import os
import random
import re
import sys


##########
# Inputs #
##########

PILOT_GUIDS_PATH = "./data/manual/manual_check_guids_20250118112133UTC.txt"
    # Random sample of 20 articles (seed 1913) that was selected for manual open data checks in Jan 2025
    # These come first in the queue, because some of them have reference results from the manual checks
QUEUE_RANDOM_SEED = 20261003
    # The rest of the articles are in a random order, so that any number of checked articles is a random sample

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
    path = f'{dir_path.strip("/")}/{files_latest}'

    with open(path, encoding="utf8") as read_file:
        data = json.loads(read_file.read())

    return data


def get_framework_programme(OpenAIRE_ID: str) -> str | None:
    """
    Gives the framework programme of an OpenAIRE project ID: corda__h2020:: - H2020, corda_____he:: - HE.
    """
    if not OpenAIRE_ID:
        return None
    if OpenAIRE_ID.startswith("corda__h2020::"):
        return "H2020"
    if OpenAIRE_ID.startswith("corda_____he::"):
        return "HE"
    return OpenAIRE_ID.split("::")[0]


def get_data_mandate_group(projects: list[dict]) -> str:
    """
    Gives the data mandate group of an article from the Horizon grants of its ETIS projects:
    H2020 mandate, H2020 no mandate, HE (all have a mandate), several groups joined with + or unknown.
    """
    groups = set()
    for project in projects:
        if not project["HORIZON_ID"] or project["OPEN_ACCESS_MANDATE_FOR_DATASET"] is None:
            continue
        framework = get_framework_programme(project["OPENAIRE_ID"])
        if framework == "H2020":
            groups.add("H2020 mandate" if project["OPEN_ACCESS_MANDATE_FOR_DATASET"] else "H2020 no mandate")
        else:
            groups.add(framework)
    return " + ".join(sorted(groups)) or "unknown"


def normalise_URL(URL: str) -> str:
    """
    Gives a URL in lower case without scheme, www. and trailing slash, to compare URLs.
    """
    return re.sub(r"^https?://(dx\.)?(www\.)?", "", URL.strip().lower()).rstrip("/")


def get_open_access_check_reason(publication: dict) -> str | None:
    """
    Gives the reason why the full text check has to settle the open access status of an article, or None.
    Open access follows the Horizon mandate: the published version or the peer-reviewed author manuscript is free to read.
    """
    if publication["IS_AVAILABLE_MANUALLY_CHECKED"] is None:
        if bool(publication["IS_OPEN_ACCESS"]) != bool(publication["OPENALEX_HAS_OPEN_PEER_REVIEWED_VERSION"]):
            return "ETIS and OpenAlex disagree"
        return None
    # Jan 2025 manual checks counted any free version (incl. preprints)
    if publication["IS_AVAILABLE_MANUALLY_CHECKED"] and not publication["OPENALEX_HAS_OPEN_PEER_REVIEWED_VERSION"]:
        return "Jan 2025 manual check counted any free version and OpenAlex has no open published version or author manuscript"
    return None


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

# The queue has everything that Claude needs for the open data check of an article (see .claude/skills/check-open-data)

# Reload data from save files
open_access_data = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_access_data")
etis_project_horizon_ids = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "etis_project_horizon_ids")
open_data_candidates = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_data_candidates")
project_datasets = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "project_datasets")
fulltext_index = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "fulltext_index")
openalex_responses = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openalex_responses")
openaire_graph_projects = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openaire_graph_projects")
openaire_research_products = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openaire_research_products")

with open(PILOT_GUIDS_PATH, encoding="utf8") as read_file:
    pilot_GUIDs = [line.strip() for line in read_file if line.strip()]

etis_projects_index = {item["GUID"]: item for item in etis_project_horizon_ids}
open_data_candidates_index = {item["GUID"]: item for item in open_data_candidates}
project_datasets_index = {item["OPENAIRE_ID"]: item for item in project_datasets}
fulltext_index_index = {item["GUID"]: item for item in fulltext_index}
openalex_responses_index = {item["GUID"]: item for item in openalex_responses}
acronyms_index = {item["id"]: item.get("acronym") for item in openaire_graph_projects}
openaire_research_products_index = {item["GUID"]: item["DATA"] for item in openaire_research_products}

queue = []
for publication in open_access_data:
    projects = [etis_projects_index[GUID] for GUID in publication["PROJECT_GUIDS"] if GUID in etis_projects_index]
    candidates = open_data_candidates_index.get(publication["GUID"]) or {}
    fulltext = fulltext_index_index.get(publication["GUID"]) or {}
    openalex_data = (openalex_responses_index.get(publication["GUID"]) or {}).get("DATA") or {}

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
    DOI = publication["DOI"] or publication["OPENALEX_DOI"]
    known_URLs = {normalise_URL(location[key]) for location in openalex_data.get("locations") or [] for key in ("pdf_url", "landing_page_url") if location.get(key)}
    if DOI:
        known_URLs.add(normalise_URL(f'https://doi.org/{DOI}'))
    openaire_open_instances = []
    for research_product in openaire_research_products_index.get(publication["GUID"]) or []:
        for instance in research_product.get("instances") or []:
            if (instance.get("accessRight") or {}).get("label") != "OPEN":
                continue
            for URL in instance.get("urls") or []:
                if normalise_URL(URL) in known_URLs:
                    continue
                known_URLs.add(normalise_URL(URL))
                openaire_open_instances += [{
                    "URL": URL,
                    "HOST": (instance.get("hostedBy") or {}).get("value"),
                    "TYPE": instance.get("type")
                }]

    queue += [{
        "GUID": publication["GUID"],
        "TITLE": publication["TITLE"],
        "PERIODICAL": publication["PERIODICAL"],
        "DOI": DOI or None,
        "ETIS_URL": f'https://www.etis.ee/Portal/Publications/Display/{publication["GUID"]}',
        "PROJECTS": [{
            "GUID": project["GUID"],
            "TITLE": project["TITLE"],
            "HORIZON_ID": project["HORIZON_ID"],
            "ACRONYM": acronyms_index.get(project["OPENAIRE_ID"]),
            "FRAMEWORK_PROGRAMME": get_framework_programme(project["OPENAIRE_ID"]),
            "OPEN_ACCESS_MANDATE_FOR_DATASET": project["OPEN_ACCESS_MANDATE_FOR_DATASET"],
            "PROJECT_DATASETS_FOUND": (project_datasets_index.get(project["OPENAIRE_ID"]) or {}).get("N_FOUND")
        } for project in projects],
        "DATA_MANDATE_GROUP": get_data_mandate_group(projects),
        "OPEN_ACCESS": {
            "ETIS_IS_OPEN_ACCESS": publication["IS_OPEN_ACCESS"],
            "ETIS_OPEN_ACCESS_TYPE": publication["OPEN_ACCESS_TYPE"],
            "ETIS_LICENSE": publication["LICENSE"],
            "ETIS_PUBLICATION_URL": publication["URL"],
            "OPENALEX_IS_OPEN_ACCESS": publication["OPENALEX_IS_OPEN_ACCESS"],
            "OPENALEX_OPEN_ACCESS_TYPE": publication["OPENALEX_OPEN_ACCESS_TYPE"],
            "OPENALEX_HAS_OPEN_PEER_REVIEWED_VERSION": publication["OPENALEX_HAS_OPEN_PEER_REVIEWED_VERSION"],
            "OPENALEX_OPEN_LOCATIONS": open_locations,
            "OPENAIRE_OPEN_INSTANCES": openaire_open_instances,
            "MANUALLY_CHECKED_IS_AVAILABLE": publication["IS_AVAILABLE_MANUALLY_CHECKED"],
            "CHECK_NEEDED_REASON": get_open_access_check_reason(publication)
        },
        "CANDIDATES": {key: value for key, value in candidates.items() if key not in ("GUID", "DOI")},
        "FULLTEXT": {key: value for key, value in fulltext.items() if key not in ("GUID", "DOI")}
    }]

# Pilot articles first, then the rest in a fixed random order
queue_index = {item["GUID"]: item for item in queue}
other_GUIDs = sorted(GUID for GUID in queue_index if GUID not in pilot_GUIDs)
random.Random(QUEUE_RANDOM_SEED).shuffle(other_GUIDs)
queue_ordered = []
for i, GUID in enumerate([GUID for GUID in pilot_GUIDs if GUID in queue_index] + other_GUIDs, start=1):
    queue_ordered += [{"QUEUE_POSITION": i, "IS_PILOT": GUID in pilot_GUIDs, **queue_index[GUID]}]

queue_save_path = f'{RESULTS_DATA_DIRECTORY_PATH.strip("/")}/open_data_queue_{get_timestamp_string()}.json'
with open(queue_save_path, "w", encoding="utf8") as save_file:
    save_file.write(json.dumps(queue_ordered, indent=2, ensure_ascii=False))

n_fulltext = len([item for item in queue_ordered if item["FULLTEXT"].get("TEXT_FILE")])
n_open_access_check = len([item for item in queue_ordered if item["OPEN_ACCESS"]["CHECK_NEEDED_REASON"]])
info_string1 = f'Saved open data queue of {len(queue_ordered)} articles ({len([item for item in queue_ordered if item["IS_PILOT"]])} pilot articles first) to {queue_save_path}'
info_string2 = f'{n_fulltext} articles have a cached full text. {n_open_access_check} articles need an open access check'
logger.info(info_string1)
logger.info(info_string2)
