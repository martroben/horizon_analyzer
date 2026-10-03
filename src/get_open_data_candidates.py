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

SCHOLEXPLORER_TARGET_TYPES = ["dataset", "software"]
SCHOLEXPLORER_MAX_PAGES = 10            # 10 links per page
DATACITE_RELATION_TYPES = [
    "IsSupplementTo",
    "IsReferencedBy",
    "IsCitedBy",
    "IsDescribedBy",
    "IsDocumentedBy",
    "IsPartOf",
    "IsSourceOf",
    "IsDerivedFrom"
]
    # Relations from a DataCite record (e.g. a dataset) to the article that suggest that the record belongs to the article
    # Records that only reference or cite the article (References, Cites) are mostly other works that cite it
EUROPEPMC_RECORD_FIELDS = [
    "id", "source", "pmid", "pmcid", "doi", "title", "pubYear", "isOpenAccess", "inEPMC", "inPMC", "hasPDF", "hasSuppl",
    "hasData", "hasTMAccessionNumbers", "tmAccessionTypeList", "dbCrossReferenceList", "license", "authMan",
    "epmcAuthMan", "nihAuthMan", "fullTextUrlList"
]
PROJECT_DATASETS_MAX = 100              # Number of project datasets to save per project (one page)

RAW_DATA_DIRECTORY_PATH = "./data/raw/"
RESULTS_DATA_DIRECTORY_PATH = "./data/results/"


#########################
# Classes and functions #
#########################

class ScholexplorerSession(requests.Session):
    """
    Class for requesting links between publications and datasets/software from ScholeXplorer.
    https://api.scholexplorer.openaire.eu/swagger-ui/index.html
    """
    BASE_URL = "https://api.scholexplorer.openaire.eu/v3"

    def get_links(self, source_PID: str, target_type: str, i_page: int = 0) -> requests.Response:
        """
        Get page i_page of the links from source_PID (e.g. a DOI) to targets of target_type (dataset, software, publication).
        """
        query_parameters = {
            "sourcePid": source_PID,
            "targetType": target_type,
            "page": i_page
        }
        URL = f'{self.BASE_URL}/Links'
        response = self.get(URL, params=query_parameters)
        return response


class DataCiteSession(requests.Session):
    """
    Class for requesting info from DataCite REST API.
    https://support.datacite.org/docs/api
    """
    BASE_URL = "https://api.datacite.org"

    def get_related_records(self, DOI: str, relation_types: list[str], n_per_page: int = 1000) -> requests.Response:
        """
        Get DataCite records that have DOI as a related identifier with one of the relation_types.
        The query can't require the DOI and the relation type to be in the same related identifier - check the results.
        """
        relation_types_string = " OR ".join(relation_types)
        # Some records give the DOI as a URL (e.g. the University of Minnesota data repository)
        query_parameters = {
            "query": f'relatedIdentifiers.relatedIdentifier:("{DOI}" OR "https://doi.org/{DOI}") AND relatedIdentifiers.relationType:({relation_types_string})',
            "page[size]": n_per_page,
            "fields[dois]": "doi,titles,types,publisher,publicationYear,relatedIdentifiers,url"
        }
        URL = f'{self.BASE_URL}/dois'
        response = self.get(URL, params=query_parameters)
        return response


class EuropePmcSession(requests.Session):
    """
    Class for requesting info from Europe PMC REST and annotations APIs.
    https://europepmc.org/RestfulWebService
    https://europepmc.org/AnnotationsApi
    """
    BASE_URL = "https://www.ebi.ac.uk/europepmc"

    def search_by_DOI(self, DOI: str) -> requests.Response:
        """
        Get the Europe PMC records of a DOI.
        """
        query_parameters = {
            "query": f'DOI:"{DOI}"',
            "resultType": "core",
            "format": "json"
        }
        URL = f'{self.BASE_URL}/webservices/rest/search'
        response = self.get(URL, params=query_parameters)
        return response

    def get_accession_numbers(self, PMCID: str) -> requests.Response:
        """
        Get database accession numbers (e.g. GEO, PDB, ENA) that Europe PMC text mining found in the full text of PMCID.
        """
        query_parameters = {
            "articleIds": f'PMC:{PMCID}',
            "type": "Accession Numbers",
            "format": "JSON"
        }
        URL = f'{self.BASE_URL}/annotations_api/annotationsByArticleIds'
        response = self.get(URL, params=query_parameters)
        return response


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
    Adds sleep to request cycles to adher to the rate limits.
    Uses monotonic timestamps.
    """
    # Safety margin 0.1 triggers slowing down when request frequency is within 90% of rate limit
    safety_margin = 0.1

    requests_per_second_current = 1 / (time.monotonic() - last_lap_timestamp)
    requests_per_second_limit_safe = requests_per_second_limit * (1 - safety_margin)
    if requests_per_second_current >= requests_per_second_limit_safe:
        time.sleep(1 / requests_per_second_limit)


def request_with_retry(request_function, *args, max_retries: int = 6, **kwargs) -> requests.Response:
    """
    Makes a request and retries it with growing waits when the API says it's rate limited or unavailable (429, 503).
    Uses the Retry-After header if the API gives it.
    """
    wait_seconds = 30
    for _ in range(max_retries):
        response = request_function(*args, **kwargs)
        if response.status_code not in (429, 503):
            return response
        retry_after = response.headers.get("Retry-After")
        time.sleep(int(retry_after) if retry_after and retry_after.isdigit() else wait_seconds)
        wait_seconds = min(wait_seconds * 2, 300)
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
    path = f'{dir_path.strip("/")}/{files_latest}'

    with open(path, encoding="utf8") as read_file:
        data = json.loads(read_file.read())

    return data


def save_raw_data(data: list[dict], file_handle: str) -> str:
    """
    Saves data to a timestamped file in the raw data directory and gives the file path.
    """
    save_path = f'{RAW_DATA_DIRECTORY_PATH.strip("/")}/{file_handle}_{get_timestamp_string()}.json'
    with open(save_path, "w", encoding="utf8") as save_file:
        save_file.write(json.dumps(data, indent=2, ensure_ascii=False))
    return save_path


def get_article_DOIs(open_access_data: list[dict]) -> list[dict]:
    """
    Gives GUID and DOI of the articles that have a DOI.
    Uses the DOI found by OpenAlex title search if ETIS doesn't have a DOI.
    """
    article_DOIs = []
    for publication in open_access_data:
        DOI = publication["DOI"] or publication["OPENALEX_DOI"]
        if DOI:
            article_DOIs += [{"GUID": publication["GUID"], "DOI": DOI}]
    return article_DOIs


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


def summarise_scholexplorer_link(link: dict) -> dict:
    """
    Gives the parts of a ScholeXplorer link that help to tell if the target is the article's own data or code.
    """
    target = link.get("target") or {}
    identifiers = []
    for identifier in target.get("Identifier") or []:
        if identifier.get("IDScheme") == "openaireIdentifier":
            continue
        identifier_string = f'{identifier.get("IDScheme")}:{identifier.get("ID")}'
        if identifier_string not in identifiers:
            identifiers += [identifier_string]

    return {
        "RELATION": (link.get("RelationshipType") or {}).get("SubType") or (link.get("RelationshipType") or {}).get("Name"),
        "TYPE": target.get("Type"),
        "TITLE": target.get("Title"),
        "IDENTIFIERS": identifiers,
        "PUBLISHERS": sorted({publisher.get("name") for publisher in target.get("Publisher") or [] if publisher.get("name")}),
        "LINK_PROVIDERS": sorted({provider.get("name") for provider in link.get("LinkProvider") or [] if provider.get("name")})
    }


def summarise_datacite_record(record: dict, DOI: str) -> dict | None:
    """
    Gives a summary of a DataCite record if it relates to DOI with one of DATACITE_RELATION_TYPES. Otherwise gives None.
    """
    attributes = record.get("attributes") or {}
    relation_types = []
    for related_identifier in attributes.get("relatedIdentifiers") or []:
        identifier = (related_identifier.get("relatedIdentifier") or "").lower()
        if not identifier.endswith(DOI.lower()):
            continue
        if related_identifier.get("relationType") in DATACITE_RELATION_TYPES:
            relation_types += [related_identifier["relationType"]]
    if not relation_types:
        return None

    titles = attributes.get("titles") or []
    return {
        "DOI": attributes.get("doi"),
        "TITLE": titles[0].get("title") if titles else None,
        "TYPE": (attributes.get("types") or {}).get("resourceTypeGeneral"),
        "PUBLISHER": attributes.get("publisher"),
        "YEAR": attributes.get("publicationYear"),
        "RELATIONS": sorted(set(relation_types)),
        "URL": attributes.get("url")
    }


def summarise_openaire_dataset(dataset: dict) -> dict:
    """
    Gives the main info of an OpenAIRE research product of type dataset.
    """
    instances = dataset.get("instances") or []
    URLs = [URL for instance in instances for URL in instance.get("urls") or []]
    hosts = [(instance.get("hostedBy") or {}).get("value") for instance in instances]
    return {
        "TITLE": dataset.get("mainTitle"),
        "DATE": dataset.get("publicationDate"),
        "PIDS": [f'{pid.get("scheme")}:{pid.get("value")}' for pid in dataset.get("pids") or []],
        "URL": URLs[0] if URLs else None,
        "HOST": next((host for host in hosts if host), None),
        "ACCESS_RIGHT": (dataset.get("bestAccessRight") or {}).get("label")
    }


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


###########################
# Get ScholeXplorer links #
###########################

# ScholeXplorer collects links between publications and datasets/software from Crossref, DataCite, OpenAIRE, PDB, etc.
# Many links are the article citing other people's data or software - Claude checks them during the open data check

# Reload data from save file
open_access_data = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_access_data")

scholexplorer_session = ScholexplorerSession()
requests_per_second_limit = 5

bad_responses = []
scholexplorer_links = []
lap_timestamp = time.monotonic()
for article in tqdm.tqdm(get_article_DOIs(open_access_data), desc="Requesting ScholeXplorer links"):
    links = {target_type: [] for target_type in SCHOLEXPLORER_TARGET_TYPES}
    for target_type in SCHOLEXPLORER_TARGET_TYPES:
        i_page = 0
        n_pages = 1
        while i_page < min(n_pages, SCHOLEXPLORER_MAX_PAGES):
            # Add delay if the pace of the requests is coming close to the API rate limit
            limit_rate(lap_timestamp, requests_per_second_limit)
            lap_timestamp = time.monotonic()
            response = request_with_retry(scholexplorer_session.get_links, article["DOI"], target_type, i_page)
            if check_bad_response(response, bad_responses):
                break
            response_data = response.json()
            links[target_type] += response_data.get("result") or []
            n_pages = response_data.get("totalPages") or 0
            i_page += 1

    scholexplorer_links += [{
        "GUID": article["GUID"],
        "DOI": article["DOI"],
        "DATA": links
    }]

scholexplorer_links_save_path = save_raw_data(scholexplorer_links, "scholexplorer_links")
n_found = len([item for item in scholexplorer_links if any(item["DATA"].values())])
info_string1 = f'ScholeXplorer has dataset or software links for {n_found} of the {len(scholexplorer_links)} articles with a DOI. Saved to {scholexplorer_links_save_path}'
info_string2 = f'ScholeXplorer API failed to return data for {len(bad_responses)} requests'
logger.info(info_string1)
logger.info(info_string2)


################################
# Get DataCite related records #
################################

# DataCite records (datasets in Zenodo, Figshare, Dryad, CCDC, institutional repositories) can name the article as a related identifier

# Reload data from save file
open_access_data = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_access_data")

datacite_session = DataCiteSession()
requests_per_second_limit = 1.5         # DataCite allows 500 requests in 5 minutes without identification: https://support.datacite.org/docs/rate-limit

bad_responses = []
datacite_records = []
lap_timestamp = time.monotonic()
for article in tqdm.tqdm(get_article_DOIs(open_access_data), desc="Requesting DataCite related records"):
    limit_rate(lap_timestamp, requests_per_second_limit)
    lap_timestamp = time.monotonic()
    response = request_with_retry(datacite_session.get_related_records, article["DOI"], DATACITE_RELATION_TYPES)
    if check_bad_response(response, bad_responses):
        continue

    datacite_records += [{
        "GUID": article["GUID"],
        "DOI": article["DOI"],
        "N_FOUND": (response.json().get("meta") or {}).get("total"),
        "DATA": response.json().get("data") or []
    }]

datacite_records_save_path = save_raw_data(datacite_records, "datacite_related_records")
n_found = len([item for item in datacite_records if any(summarise_datacite_record(record, item["DOI"]) for record in item["DATA"])])
info_string1 = f'DataCite has related records for {n_found} of the {len(datacite_records)} articles with a DOI. Saved to {datacite_records_save_path}'
info_string2 = f'DataCite API failed to return data for {len(bad_responses)} requests'
logger.info(info_string1)
logger.info(info_string2)


##########################
# Get Europe PMC records #
##########################

# Europe PMC gives PMC IDs (needed for full text) and accession numbers that text mining found in PMC full texts

# Reload data from save file
open_access_data = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_access_data")

europepmc_session = EuropePmcSession()
requests_per_second_limit = 5

bad_responses = []
europepmc_records = []
lap_timestamp = time.monotonic()
for article in tqdm.tqdm(get_article_DOIs(open_access_data), desc="Requesting Europe PMC records"):
    limit_rate(lap_timestamp, requests_per_second_limit)
    lap_timestamp = time.monotonic()
    response = request_with_retry(europepmc_session.search_by_DOI, article["DOI"])
    if check_bad_response(response, bad_responses):
        continue

    # Keep only records of the same DOI (search can give near matches) and only the fields that are used
    records = []
    for record in (response.json().get("resultList") or {}).get("result") or []:
        if (record.get("doi") or "").lower() != article["DOI"].lower():
            continue
        records += [{field: record.get(field) for field in EUROPEPMC_RECORD_FIELDS if field in record}]

    accession_numbers = []
    PMCIDs = [record["pmcid"] for record in records if record.get("pmcid") and record.get("hasTMAccessionNumbers") == "Y"]
    for PMCID in PMCIDs[:1]:
        limit_rate(lap_timestamp, requests_per_second_limit)
        lap_timestamp = time.monotonic()
        response = request_with_retry(europepmc_session.get_accession_numbers, PMCID)
        if check_bad_response(response, bad_responses):
            continue
        for annotated_article in response.json() or []:
            accession_numbers += annotated_article.get("annotations") or []

    europepmc_records += [{
        "GUID": article["GUID"],
        "DOI": article["DOI"],
        "DATA": records,
        "ACCESSION_NUMBERS": accession_numbers
    }]

europepmc_records_save_path = save_raw_data(europepmc_records, "europepmc_records")
n_found = len([item for item in europepmc_records if item["DATA"]])
n_PMC = len([item for item in europepmc_records if any(record.get("pmcid") for record in item["DATA"])])
info_string1 = f'Europe PMC has records for {n_found} of the {len(europepmc_records)} articles with a DOI ({n_PMC} with a PMC ID). Saved to {europepmc_records_save_path}'
info_string2 = f'Europe PMC API failed to return data for {len(bad_responses)} requests'
logger.info(info_string1)
logger.info(info_string2)


#####################################
# Get OpenAIRE datasets of projects #
#####################################

# Datasets that OpenAIRE links to the Horizon projects of the articles
# Project datasets are reported separately - they count as open data of an article only if the article itself links to them

# Reload data from save file
open_access_data = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_access_data")
etis_project_horizon_ids = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "etis_project_horizon_ids")

article_project_GUIDs = {project_GUID for publication in open_access_data for project_GUID in publication["PROJECT_GUIDS"]}
OpenAIRE_projects = {}
for project in etis_project_horizon_ids:
    if project["GUID"] in article_project_GUIDs and project["OPENAIRE_ID"]:
        OpenAIRE_projects[project["OPENAIRE_ID"]] = project["HORIZON_ID"]

openaire_graph_session = OpenAireGraphSession("research-products")
requests_per_second_limit = 2           # Respect API rate limit (7200 per hour)

bad_responses = []
project_datasets = []
lap_timestamp = time.monotonic()
for OpenAIRE_ID, horizon_ID in tqdm.tqdm(OpenAIRE_projects.items(), desc="Requesting OpenAIRE project datasets"):
    limit_rate(lap_timestamp, requests_per_second_limit)
    lap_timestamp = time.monotonic()
    response = request_with_retry(openaire_graph_session.get_items, n_per_page=PROJECT_DATASETS_MAX, parameters={"type": "dataset", "relProjectId": OpenAIRE_ID})
    if check_bad_response(response, bad_responses):
        continue

    project_datasets += [{
        "OPENAIRE_ID": OpenAIRE_ID,
        "HORIZON_ID": horizon_ID,
        "N_FOUND": (response.json().get("header") or {}).get("numFound"),
        "DATA": response.json().get("results") or []
    }]

project_datasets_save_path = save_raw_data(project_datasets, "openaire_project_datasets")
n_found = len([item for item in project_datasets if item["N_FOUND"]])
info_string1 = f'OpenAIRE has datasets for {n_found} of the {len(project_datasets)} Horizon projects with articles. Saved to {project_datasets_save_path}'
info_string2 = f'OpenAIRE graph API failed to return data for {len(bad_responses)} requests'
logger.info(info_string1)
logger.info(info_string2)


#######################################
# Summarise open data candidate links #
#######################################

# Reload data from save files
open_access_data = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_access_data")
scholexplorer_links = read_latest_file(RAW_DATA_DIRECTORY_PATH, "scholexplorer_links")
datacite_records = read_latest_file(RAW_DATA_DIRECTORY_PATH, "datacite_related_records")
europepmc_records = read_latest_file(RAW_DATA_DIRECTORY_PATH, "europepmc_records")
project_datasets = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openaire_project_datasets")

scholexplorer_links_index = {item["GUID"]: item for item in scholexplorer_links}
datacite_records_index = {item["GUID"]: item for item in datacite_records}
europepmc_records_index = {item["GUID"]: item for item in europepmc_records}

open_data_candidates = []
for publication in open_access_data:
    scholexplorer_item = scholexplorer_links_index.get(publication["GUID"]) or {}
    datacite_item = datacite_records_index.get(publication["GUID"]) or {}
    europepmc_item = europepmc_records_index.get(publication["GUID"]) or {}
    europepmc_record = next((record for record in europepmc_item.get("DATA") or [] if record.get("pmcid")), None)
    europepmc_record = europepmc_record or next(iter(europepmc_item.get("DATA") or []), {})

    scholexplorer_link_summaries = []
    for target_type, links in (scholexplorer_item.get("DATA") or {}).items():
        for link in links:
            link_summary = summarise_scholexplorer_link(link)
            if link_summary not in scholexplorer_link_summaries:
                scholexplorer_link_summaries += [link_summary]

    datacite_record_summaries = []
    for record in datacite_item.get("DATA") or []:
        record_summary = summarise_datacite_record(record, datacite_item["DOI"])
        if record_summary:
            datacite_record_summaries += [record_summary]

    accession_numbers = []
    for annotation in europepmc_item.get("ACCESSION_NUMBERS") or []:
        # Tag URIs look like http://identifiers.org/pdbe/pdb:7JJC (database pdb) or http://identifiers.org/doi:10.15252/embr.201439246 (doi)
        # A few are database pages, e.g. https://www.proteinatlas.org/search/HPA023918 (www.proteinatlas.org)
        databases = set()
        for tag in annotation.get("tags") or []:
            if not tag.get("uri"):
                continue
            if "identifiers.org/" in tag["uri"]:
                databases.add(tag["uri"].split("identifiers.org/", 1)[1].split(":", 1)[0].rsplit("/", 1)[-1])
            else:
                databases.add(re.sub(r"^https?://", "", tag["uri"]).split("/", 1)[0])
        databases = sorted(databases)
        accession_number = {
            "ID": annotation.get("exact"),
            "DATABASE": ", ".join(databases) or None,
            "SECTION": re.sub(r"\s*\(http.*\)$", "", annotation.get("section") or "") or None
        }
        if accession_number not in accession_numbers:
            accession_numbers += [accession_number]

    open_data_candidates += [{
        "GUID": publication["GUID"],
        "DOI": scholexplorer_item.get("DOI") or datacite_item.get("DOI") or europepmc_item.get("DOI"),
        "PMID": europepmc_record.get("pmid"),
        "PMCID": europepmc_record.get("pmcid"),
        "EUROPEPMC_IS_OPEN_ACCESS": europepmc_record.get("isOpenAccess") == "Y" if europepmc_record else None,
        "EUROPEPMC_IS_AUTHOR_MANUSCRIPT": europepmc_record.get("authMan") == "Y" if europepmc_record else None,
        "EUROPEPMC_HAS_SUPPLEMENTARY_FILES": europepmc_record.get("hasSuppl") == "Y" if europepmc_record else None,
        "EUROPEPMC_LICENSE": europepmc_record.get("license"),
        "ACCESSION_NUMBERS": accession_numbers,
        "SCHOLEXPLORER_LINKS": scholexplorer_link_summaries,
        "DATACITE_RECORDS": datacite_record_summaries
    }]

open_data_candidates_save_path = f'{RESULTS_DATA_DIRECTORY_PATH.strip("/")}/open_data_candidates_{get_timestamp_string()}.json'
with open(open_data_candidates_save_path, "w", encoding="utf8") as save_file:
    save_file.write(json.dumps(open_data_candidates, indent=2, ensure_ascii=False))

project_dataset_summaries = []
for project in project_datasets:
    project_dataset_summaries += [{
        "OPENAIRE_ID": project["OPENAIRE_ID"],
        "HORIZON_ID": project["HORIZON_ID"],
        "N_FOUND": project["N_FOUND"],
        "DATASETS": [summarise_openaire_dataset(dataset) for dataset in project["DATA"]]
    }]

project_datasets_save_path = f'{RESULTS_DATA_DIRECTORY_PATH.strip("/")}/project_datasets_{get_timestamp_string()}.json'
with open(project_datasets_save_path, "w", encoding="utf8") as save_file:
    save_file.write(json.dumps(project_dataset_summaries, indent=2, ensure_ascii=False))

n_with_candidates = len([item for item in open_data_candidates if item["ACCESSION_NUMBERS"] or item["SCHOLEXPLORER_LINKS"] or item["DATACITE_RECORDS"]])
info_string1 = f'{n_with_candidates} of the {len(open_data_candidates)} articles have candidate data links (accession numbers, ScholeXplorer links or DataCite records). Saved to {open_data_candidates_save_path}'
info_string2 = f'Saved OpenAIRE datasets of {len(project_dataset_summaries)} Horizon projects to {project_datasets_save_path}'
logger.info(info_string1)
logger.info(info_string2)
