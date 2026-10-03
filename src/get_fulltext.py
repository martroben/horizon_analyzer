# standard
import datetime
import json
import logging
import os
import re
import sys
import time
import urllib.parse
# external
import requests
import tqdm
# local
import fulltext_conversion


##########
# Inputs #
##########

OPENALEX_API_KEY_SECRET_NAME = "openalex_api_key"
    # Optional. Needed for OpenAlex cached full texts ($0.01 per download, free key has a $1 daily budget)
    # https://openalex.org/settings/api
BROWSER_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
    # Many publishers (e.g. MDPI) refuse open access PDFs to non-browser user agents
PEER_REVIEWED_VERSIONS = [
    "publishedVersion",     # Version of record
    "acceptedVersion"       # Peer-reviewed author manuscript
]
MIN_TEXT_LENGTH = 5000          # Shorter PDF or XML text is not a full text (e.g. scanned PDF without text layer)
MIN_HTML_TEXT_LENGTH = 20000    # Shorter HTML text is not a full text (e.g. abstract page of a paywalled article)
HOST_REQUEST_INTERVAL = 1       # Seconds between requests to the same host
RETRY_FAILED = True             # Retry articles that had no full text in an earlier run

FULLTEXT_DIRECTORY_PATH = "./data/fulltext/"
RAW_DATA_DIRECTORY_PATH = "./data/raw/"
RESULTS_DATA_DIRECTORY_PATH = "./data/results/"
SECRETS_DIRECTORY_PATH = "./secrets/"
    # One file per secret, file name is the secret name. Not committed


#########################
# Classes and functions #
#########################

class NcbiSession(requests.Session):
    """
    Class for requesting PMC full texts from NCBI E-utilities.
    https://www.ncbi.nlm.nih.gov/books/NBK25499/
    Gives full text XML of open access articles and author manuscripts. Some publishers don't allow it.
    """
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def get_pmc_article(self, PMCID: str) -> requests.Response:
        """
        Get PMC article XML by PMC ID.
        """
        query_parameters = {
            "db": "pmc",
            "id": PMCID.removeprefix("PMC"),
            "rettype": "xml"
        }
        URL = f'{self.BASE_URL}/efetch.fcgi'
        response = self.get(URL, params=query_parameters)
        return response


class PoliteSession(requests.Session):
    """
    Session that waits HOST_REQUEST_INTERVAL seconds between requests to the same host.
    """
    def __init__(self, user_agent: str = None, host_request_interval: float = HOST_REQUEST_INTERVAL) -> None:
        super().__init__()
        if user_agent:
            self.headers.update({"User-Agent": user_agent})
        self.host_request_interval = host_request_interval
        self.last_request_times = {}

    def get_politely(self, URL: str, **kwargs) -> requests.Response:
        host = urllib.parse.urlparse(URL).netloc
        wait_time = self.last_request_times.get(host, 0) + self.host_request_interval - time.monotonic()
        if wait_time > 0:
            time.sleep(wait_time)
        try:
            return self.get(URL, timeout=60, **kwargs)
        finally:
            self.last_request_times[host] = time.monotonic()


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
    path = f'{dir_path.strip("/")}/{files_latest}'

    with open(path, encoding="utf8") as read_file:
        data = json.loads(read_file.read())

    return data


def get_open_locations(openalex_data: dict) -> list[dict]:
    """
    Gives the open access locations of an OpenAlex work: published versions first, then accepted manuscripts, then others.
    """
    version_order = PEER_REVIEWED_VERSIONS + ["submittedVersion"]
    locations = [location for location in openalex_data.get("locations") or [] if location.get("is_oa")]
    return sorted(locations, key=lambda location: version_order.index(location["version"]) if location.get("version") in version_order else len(version_order))


def decode_html(response: requests.Response) -> str:
    """
    Gives the text of an HTML response. Guesses the encoding if the server doesn't give it.
    """
    if "charset" in response.headers.get("content-type", "").lower():
        return response.text
    try:
        return response.content.decode("utf8")
    except UnicodeDecodeError:
        return response.content.decode(response.apparent_encoding or "latin-1", errors="replace")


def save_fulltext(GUID: str, content: bytes | str, extension: str, min_text_length: int, page_URL: str = None) -> tuple[str, str, int] | None:
    """
    Saves full text content to the full text directory and converts it to text.
    Gives the file path, text file path and text length. Gives None and removes the files if the text is too short.
    """
    file_path = f'{FULLTEXT_DIRECTORY_PATH.rstrip("/")}/{GUID}.{extension}'
    mode = "wb" if isinstance(content, bytes) else "w"
    with open(file_path, mode, **({} if mode == "wb" else {"encoding": "utf8"})) as save_file:
        save_file.write(content)

    text_file_path = None
    try:
        text_file_path = fulltext_conversion.convert_file(file_path, page_URL)
        with open(text_file_path, encoding="utf8") as read_file:
            n_characters = len(read_file.read())
    except Exception:
        n_characters = 0

    if n_characters < min_text_length:
        for path in (file_path, text_file_path):
            if path and os.path.exists(path):
                os.remove(path)
        return None
    return file_path, text_file_path, n_characters


def get_fulltext_attempts(publication: dict, open_data_candidate: dict, openalex_data: dict) -> list[dict]:
    """
    Gives the full text sources to try for an article, best first:
    PMC, open PDFs and pages of published versions and author manuscripts, OpenAlex cached copy, open preprint PDFs.
    """
    attempts = []
    if open_data_candidate.get("PMCID"):
        version = "acceptedVersion" if open_data_candidate.get("EUROPEPMC_IS_AUTHOR_MANUSCRIPT") else "publishedVersion"
        attempts += [{"SOURCE": "pmc", "URL": open_data_candidate["PMCID"], "VERSION": version, "HOST_TYPE": "repository"}]

    open_locations = get_open_locations(openalex_data)
    for location in open_locations:
        if location.get("version") in PEER_REVIEWED_VERSIONS and location.get("pdf_url"):
            attempts += [{"SOURCE": "oa_pdf", "URL": location["pdf_url"], "VERSION": location["version"], "HOST_TYPE": (location.get("source") or {}).get("type")}]
    for location in open_locations:
        # Repository landing pages are metadata pages - only journal pages can have the full text in HTML
        host_type = (location.get("source") or {}).get("type")
        if location.get("version") in PEER_REVIEWED_VERSIONS and location.get("landing_page_url") and host_type != "repository":
            attempts += [{"SOURCE": "oa_html", "URL": location["landing_page_url"], "VERSION": location["version"], "HOST_TYPE": host_type}]

    content_URLs = openalex_data.get("content_urls") or {}
    if OPENALEX_API_KEY and content_URLs:
        content_URL = content_URLs.get("grobid_xml") or content_URLs.get("pdf")
        attempts += [{"SOURCE": "openalex_content", "URL": content_URL, "VERSION": None, "HOST_TYPE": None}]

    for location in open_locations:
        if location.get("version") not in PEER_REVIEWED_VERSIONS and location.get("pdf_url"):
            attempts += [{"SOURCE": "oa_pdf", "URL": location["pdf_url"], "VERSION": location.get("version"), "HOST_TYPE": (location.get("source") or {}).get("type")}]

    # Same URL can be in several locations
    unique_attempts = []
    for attempt in attempts:
        if attempt["URL"] not in [unique_attempt["URL"] for unique_attempt in unique_attempts]:
            unique_attempts += [attempt]
    return unique_attempts


#####################
# Environment setup #
#####################

# Create directories
if not os.path.exists(FULLTEXT_DIRECTORY_PATH):
    os.makedirs(FULLTEXT_DIRECTORY_PATH)

# Logger
logger = logging.getLogger()
logger.setLevel("INFO")
logger.addHandler(logging.StreamHandler(sys.stdout))

# Secrets
OPENALEX_API_KEY = read_secret(SECRETS_DIRECTORY_PATH, OPENALEX_API_KEY_SECRET_NAME)
if not OPENALEX_API_KEY:
    logger.info(f'No OpenAlex API key in {SECRETS_DIRECTORY_PATH} - skipping OpenAlex cached full texts')


##################
# Get full texts #
##################

# Full texts are saved to data/fulltext/<GUID>.<pdf|xml|html> with a plain text copy <GUID>.txt
# and a <GUID>.json file that tells where the full text came from. Articles that already have a full text are skipped

# Reload data from save files
open_access_data = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_access_data")
open_data_candidates = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_data_candidates")
openalex_responses = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openalex_responses")

open_data_candidates_index = {item["GUID"]: item for item in open_data_candidates}
openalex_responses_index = {item["GUID"]: item for item in openalex_responses}

ncbi_session = NcbiSession()
download_session = PoliteSession(BROWSER_USER_AGENT)
openalex_session = PoliteSession()
if OPENALEX_API_KEY:
    openalex_session.headers.update({"Authorization": f'Bearer {OPENALEX_API_KEY}'})

n_skipped = 0
for publication in tqdm.tqdm(open_access_data, desc="Getting full texts"):
    GUID = publication["GUID"]
    info_file_path = f'{FULLTEXT_DIRECTORY_PATH.rstrip("/")}/{GUID}.json'
    if os.path.exists(info_file_path):
        with open(info_file_path, encoding="utf8") as read_file:
            fulltext_info = json.loads(read_file.read())
        if fulltext_info["TEXT_FILE"] or not RETRY_FAILED:
            n_skipped += 1
            continue

    open_data_candidate = open_data_candidates_index.get(GUID) or {}
    openalex_data = (openalex_responses_index.get(GUID) or {}).get("DATA") or {}
    fulltext_info = {
        "GUID": GUID,
        "DOI": publication["DOI"] or publication["OPENALEX_DOI"] or None,
        "FILE": None,
        "TEXT_FILE": None,
        "N_CHARACTERS": None,
        "SOURCE": None,
        "URL": None,
        "VERSION": None,
        "HOST_TYPE": None,
        "RETRIEVED_AT": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "ATTEMPTS": []
    }

    for attempt in get_fulltext_attempts(publication, open_data_candidate, openalex_data):
        saved = None
        try:
            if attempt["SOURCE"] == "pmc":
                response = ncbi_session.get_pmc_article(attempt["URL"])
                time.sleep(0.4)     # NCBI allows 3 requests per second without an API key
                if not response:
                    attempt["RESULT"] = f'http {response.status_code}'
                elif "<body" not in response.text:
                    attempt["RESULT"] = "no body (publisher doesn't allow full text XML)"
                else:
                    if re.search(r"<meta-name>pmc-prop-preprint</meta-name>\s*<meta-value>yes", response.text):
                        attempt["VERSION"] = "submittedVersion"
                    attempt["URL"] = f'https://pmc.ncbi.nlm.nih.gov/articles/{attempt["URL"]}/'
                    saved = save_fulltext(GUID, response.text, "xml", MIN_TEXT_LENGTH)
                    attempt["RESULT"] = "ok" if saved else "text too short"

            elif attempt["SOURCE"] in ("oa_pdf", "openalex_content"):
                session = openalex_session if attempt["SOURCE"] == "openalex_content" else download_session
                response = session.get_politely(attempt["URL"])
                if not response:
                    attempt["RESULT"] = f'http {response.status_code}'
                elif response.content.lstrip()[:5] == b"%PDF-":
                    saved = save_fulltext(GUID, response.content, "pdf", MIN_TEXT_LENGTH)
                    attempt["RESULT"] = "ok" if saved else "text too short"
                elif response.content.lstrip()[:5] in (b"<?xml", b"<TEI ", b"<TEI>"):
                    saved = save_fulltext(GUID, response.content.decode("utf8", errors="replace"), "xml", MIN_TEXT_LENGTH)
                    attempt["RESULT"] = "ok" if saved else "text too short"
                else:
                    attempt["RESULT"] = f'not a pdf ({response.headers.get("content-type", "")})'

            elif attempt["SOURCE"] == "oa_html":
                response = download_session.get_politely(attempt["URL"])
                if not response:
                    attempt["RESULT"] = f'http {response.status_code}'
                elif "html" not in response.headers.get("content-type", ""):
                    attempt["RESULT"] = f'not html ({response.headers.get("content-type", "")})'
                else:
                    attempt["URL"] = response.url
                    saved = save_fulltext(GUID, decode_html(response), "html", MIN_HTML_TEXT_LENGTH, response.url)
                    attempt["RESULT"] = "ok" if saved else "text too short"
        except Exception as exception:
            attempt["RESULT"] = f'error: {type(exception).__name__}'

        fulltext_info["ATTEMPTS"] += [attempt]
        if saved:
            fulltext_info["FILE"], fulltext_info["TEXT_FILE"], fulltext_info["N_CHARACTERS"] = saved
            for key in ("SOURCE", "URL", "VERSION", "HOST_TYPE"):
                fulltext_info[key] = attempt[key]
            break

    with open(info_file_path, "w", encoding="utf8") as save_file:
        save_file.write(json.dumps(fulltext_info, indent=2, ensure_ascii=False))

info_string = f'Got full texts. Skipped {n_skipped} articles that had a full text from an earlier run'
logger.info(info_string)


########################
# Save full text index #
########################

# Reload data from save file
open_access_data = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_access_data")

fulltext_index = []
for publication in open_access_data:
    info_file_path = f'{FULLTEXT_DIRECTORY_PATH.rstrip("/")}/{publication["GUID"]}.json'
    if not os.path.exists(info_file_path):
        continue
    with open(info_file_path, encoding="utf8") as read_file:
        fulltext_index += [json.loads(read_file.read())]

fulltext_index_save_path = f'{RESULTS_DATA_DIRECTORY_PATH.strip("/")}/fulltext_index_{get_timestamp_string()}.json'
with open(fulltext_index_save_path, "w", encoding="utf8") as save_file:
    save_file.write(json.dumps(fulltext_index, indent=2, ensure_ascii=False))

n_found = len([item for item in fulltext_index if item["TEXT_FILE"]])
n_by_source = {}
for item in fulltext_index:
    if item["TEXT_FILE"]:
        n_by_source[item["SOURCE"]] = n_by_source.get(item["SOURCE"], 0) + 1
n_peer_reviewed = len([item for item in fulltext_index if item["TEXT_FILE"] and item["VERSION"] in PEER_REVIEWED_VERSIONS])
info_string1 = f'{n_found} of the {len(open_access_data)} articles have a full text ({n_peer_reviewed} published version or author manuscript). By source: {n_by_source}'
info_string2 = f'Saved full text index to {fulltext_index_save_path}'
logger.info(info_string1)
logger.info(info_string2)
