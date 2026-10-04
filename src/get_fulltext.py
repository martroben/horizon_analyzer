# standard
import collections
import datetime
import html
import io
import json
import logging
import os
import re
import sys
import time
import urllib.parse
import zipfile
# external
import requests
from thefuzz import fuzz
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
VERSION_CODES = {
    "publishedVersion": "published_version",    # Version of record
    "acceptedVersion": "accepted_version",      # Peer-reviewed author manuscript
    "submittedVersion": "submitted_version"     # Preprint
}
    # Version codes of OpenAlex location versions
PEER_REVIEWED_VERSIONS = ["published_version", "accepted_version"]
MIN_TEXT_LENGTH = 5000          # Shorter PDF or XML text is not a full text (e.g. scanned PDF without text layer)
MIN_HTML_TEXT_LENGTH = 20000    # Shorter HTML text is not a full text (e.g. abstract page of a paywalled article)
REFERENCES_HEADING_PATTERN = r"\b(References|REFERENCES|Bibliography|Literature cited|Kasutatud kirjandus|Kirjandus|Viited)\b"
    # HTML text is counted up to the last of these: a landing page with a long reference list isn't a full text
TITLE_SIMILARITY_THRESHOLD = 90
    # Word files and files from ETIS links count as the article only if they have the article title (fuzzy match score, 0-100)
    # Word files on Zenodo can be other documents, e.g. a cover letter or a response to reviewers. ETIS links are typed in by hand
TITLE_SEARCH_CHARACTERS = 5000
    # How far from the beginning of a Word file to look for the title. Files from ETIS links are searched whole (can be a whole journal issue)
HOST_REQUEST_INTERVAL = 1       # Seconds between requests to the same host
RETRY_FAILED = True             # Retry articles that had no full text in an earlier run
ZENODO_RECORD_PATTERN = r"zenodo\.org/records?/(\d+)|10\.5281/zenodo\.(\d+)"
ZENODO_RECORD_URL = "https://zenodo.org/records/{}"
PMC_ARTICLE_URL = "https://pmc.ncbi.nlm.nih.gov/articles/{}/"
PDF_URL_PATTERN = r"\.pdf($|\?)|/bitstream/|/download/|/files/"
    # OpenAIRE open instance URLs that can be PDF files. The rest are pages (landing pages, journal pages)
PREPRINT_URL_PATTERN = r"arxiv\.org|biorxiv\.org|medrxiv\.org|chemrxiv\.org|techrxiv\.org|10\.36227/techrxiv|ssrn\.com|preprints\.org|researchsquare\.com|mpra\.ub\.uni-muenchen\.de"
    # Preprint servers and working paper archives. OpenAIRE doesn't always give them the instance type Preprint

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
        """
        Get URL after waiting until host_request_interval seconds have passed since the last request to the same host.
        """
        host = urllib.parse.urlparse(URL).netloc
        wait_time = self.last_request_times.get(host, 0) + self.host_request_interval - time.monotonic()
        if wait_time > 0:
            time.sleep(wait_time)
        try:
            return self.get(URL, timeout=60, **kwargs)
        finally:
            self.last_request_times[host] = time.monotonic()


class ZenodoSession(PoliteSession):
    """
    Class for requesting records and files from Zenodo REST API.
    https://developers.zenodo.org/
    Guest limit is 133 requests per minute.
    """
    BASE_URL = "https://zenodo.org/api"

    def get_record(self, record_ID: str) -> requests.Response:
        """
        Get Zenodo record by record ID. Concept record IDs redirect to the latest version.
        """
        URL = f'{self.BASE_URL}/records/{record_ID}'
        response = self.get_politely(URL)
        return response


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


def get_version_code(location: dict) -> str | None:
    """
    Gives the version code of an OpenAlex location (published_version, accepted_version, submitted_version). Gives None if OpenAlex doesn't say.
    """
    return VERSION_CODES.get(location.get("version"))


def get_host_type(location: dict) -> str | None:
    """
    Gives the type of the host of an OpenAlex location in snake case (journal, repository, book_series etc.).
    """
    host_type = (location.get("source") or {}).get("type")
    return host_type.replace(" ", "_") if host_type else None


def get_open_locations(openalex_data: dict) -> list[dict]:
    """
    Gives the open access locations of an OpenAlex work: published versions first, then accepted manuscripts, then others.
    """
    version_order = PEER_REVIEWED_VERSIONS + ["submitted_version"]
    locations = [location for location in openalex_data.get("locations") or [] if location.get("is_oa")]
    return sorted(locations, key=lambda location: version_order.index(get_version_code(location)) if get_version_code(location) in version_order else len(version_order))


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
    Gives the file path, text file path and text length. Gives None and removes the files if the text is too short
    (HTML: the text before the last references heading).
    """
    file_path = f'{FULLTEXT_DIRECTORY_PATH.rstrip("/")}/{GUID}.{extension}'
    if isinstance(content, str):
        content = content.encode("utf8")
    with open(file_path, "wb") as save_file:
        save_file.write(content)

    text_file_path = None
    try:
        text_file_path = fulltext_conversion.convert_file(file_path, page_URL)
        with open(text_file_path, encoding="utf8") as read_file:
            text = read_file.read()
        n_characters = len(text)
        references_headings = list(re.finditer(REFERENCES_HEADING_PATTERN, text)) if extension == "html" else []
        n_body_characters = references_headings[-1].start() if references_headings else n_characters
    except Exception:
        n_characters = n_body_characters = 0

    if n_body_characters < min_text_length:
        for path in (file_path, text_file_path):
            if path and os.path.exists(path):
                os.remove(path)
        return None
    return file_path, text_file_path, n_characters


def is_word_document(content: bytes) -> bool:
    """
    Tells whether downloaded content is a Word document (a .docx file is a zip file with word/document.xml).
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zip_file:
            return "word/document.xml" in zip_file.namelist()
    except zipfile.BadZipFile:
        return False


def normalise_words(text: str) -> str:
    """
    Gives lowercase text with only words, for fuzzy comparison.
    """
    return " ".join(re.sub(r"\W", " ", text.lower()).split())


def text_has_title(text_file_path: str, title: str, n_characters: int | None = TITLE_SEARCH_CHARACTERS) -> bool:
    """
    Tells whether the article title is in the first n_characters of a text file (in the whole text if n_characters is None).
    Fuzzy, because ETIS titles can differ a little from the article.
    """
    with open(text_file_path, encoding="utf8") as read_file:
        text = read_file.read(n_characters)
    return fuzz.partial_ratio(normalise_words(title or ""), normalise_words(text)) >= TITLE_SIMILARITY_THRESHOLD


def save_downloaded_fulltext(GUID: str, response: requests.Response, title: str) -> tuple[tuple[str, str, int] | None, str, str | None]:
    """
    Saves a downloaded PDF, XML (GROBID TEI) or Word full text.
    Gives the result of save_fulltext, the result code of the attempt and its detail (see doc/data_schema.md).
    Word files have to have the article title near the beginning.
    """
    if not response:
        return None, "http_error", str(response.status_code)
    if response.content.lstrip()[:5] == b"%PDF-":
        saved = save_fulltext(GUID, response.content, "pdf", MIN_TEXT_LENGTH)
    elif response.content.lstrip()[:5] in (b"<?xml", b"<TEI ", b"<TEI>"):
        saved = save_fulltext(GUID, response.content.decode("utf8", errors="replace"), "xml", MIN_TEXT_LENGTH)
    elif is_word_document(response.content):
        saved = save_fulltext(GUID, response.content, "docx", MIN_TEXT_LENGTH)
        if saved and not text_has_title(saved[1], title):
            for path in saved[:2]:
                os.remove(path)
            return None, "title_not_found", None
    else:
        return None, "wrong_content_type", response.headers.get("content-type") or None
    return saved, "ok" if saved else "text_too_short", None


def get_citation_pdf_URL(page: str, page_URL: str) -> str | None:
    """
    Gives the PDF link in the citation_pdf_url meta tag of a page (journal and repository pages have it for Google Scholar).
    Gives None if the page doesn't have the tag.
    """
    for tag in re.findall(r"<meta\b[^>]*>", page, flags=re.IGNORECASE):
        if not re.search(r"""name\s*=\s*["']citation_pdf_url["']""", tag, flags=re.IGNORECASE):
            continue
        content = re.search(r"""content\s*=\s*["']([^"']+)["']""", tag, flags=re.IGNORECASE)
        if content:
            return urllib.parse.urljoin(page_URL, html.unescape(content.group(1).strip()))
    return None


def save_linked_fulltext(GUID: str, session: PoliteSession, URL: str, title: str, is_page_accepted: bool) -> tuple[tuple[str, str, int] | None, str, str | None, str]:
    """
    Downloads the full text behind a link: a PDF, XML or Word file, or a page.
    A page is the full text if is_page_accepted and its text is long enough (journal pages).
    Otherwise the PDF that the page links in its citation_pdf_url meta tag is downloaded.
    Gives the result of save_fulltext, the result code of the attempt, its detail (see doc/data_schema.md) and the URL that was tried last.
    """
    response = session.get_politely(URL)
    is_page = bool(response) and "html" in response.headers.get("content-type", "").lower() and response.content.lstrip()[:5] != b"%PDF-"
    if not is_page:
        saved, result, result_detail = save_downloaded_fulltext(GUID, response, title)
        return saved, result, result_detail, URL

    page = decode_html(response)
    if is_page_accepted:
        saved = save_fulltext(GUID, page, "html", MIN_HTML_TEXT_LENGTH, response.url)
        if saved:
            return saved, "ok", None, response.url
    PDF_URL = get_citation_pdf_URL(page, response.url)
    if not PDF_URL:
        return None, "text_too_short" if is_page_accepted else "no_pdf_link", None, response.url
    saved, result, result_detail = save_downloaded_fulltext(GUID, session.get_politely(PDF_URL), title)
    return saved, result, result_detail, PDF_URL


def get_zenodo_fulltext_URL(record: dict) -> str | None:
    """
    Gives the download URL of the article file in an open Zenodo record: a PDF or, if there is none, a Word file.
    Gives None if the record isn't open or has neither.
    Supplements are named "supplementary" etc. or like the article file with a suffix (e.g. RSC d4mr00006d.pdf and d4mr00006d1.pdf),
    so the file with the shortest name that isn't named as a supplement comes first.
    """
    if (record.get("metadata") or {}).get("access_right") != "open":
        return None
    files = [file for file in record.get("files") or [] if file["key"].lower().endswith((".pdf", ".docx"))]
    files.sort(key=lambda file: (
        bool(re.search(r"suppl|supporting", file["key"], flags=re.IGNORECASE)),
        not file["key"].lower().endswith(".pdf"),
        len(file["key"])
    ))
    return files[0]["links"]["self"] if files else None


def get_openaire_attempts(research_products: list[dict]) -> list[dict]:
    """
    Gives the full text sources in the open instances of an article's OpenAIRE research products: Zenodo records, links to PDF files and other links (pages).
    Zenodo records come first, because Horizon projects upload published versions and accepted manuscripts there.
    The version is unknown, except for preprints (instance type Preprint or a preprint server).
    """
    attempts = []
    for research_product in research_products:
        for instance in research_product.get("instances") or []:
            if (instance.get("accessRight") or {}).get("label") != "OPEN":
                continue
            for URL in instance.get("urls") or []:
                is_preprint = instance.get("type") == "Preprint" or re.search(PREPRINT_URL_PATTERN, URL, flags=re.IGNORECASE)
                version = "submitted_version" if is_preprint else None
                zenodo_match = re.search(ZENODO_RECORD_PATTERN, URL, flags=re.IGNORECASE)
                if zenodo_match:
                    record_URL = ZENODO_RECORD_URL.format(zenodo_match.group(1) or zenodo_match.group(2))
                    attempts += [{"SOURCE": "zenodo", "URL": record_URL, "VERSION": version, "HOST_TYPE": "repository"}]
                elif re.search(PDF_URL_PATTERN, URL, flags=re.IGNORECASE):
                    attempts += [{"SOURCE": "openaire_pdf", "URL": URL, "VERSION": version, "HOST_TYPE": None}]
                else:
                    attempts += [{"SOURCE": "openaire_html", "URL": URL, "VERSION": version, "HOST_TYPE": None}]
    source_order = ["zenodo", "openaire_pdf", "openaire_html"]
    return sorted(attempts, key=lambda attempt: source_order.index(attempt["SOURCE"]))


def get_etis_attempts(ETIS_data: dict) -> list[dict]:
    """
    Gives the full text sources in the ETIS links of an article: the full text location and the publication URL.
    The links can be files or pages. The version is unknown, except for preprints (preprint server).
    """
    attempts = []
    for URL in (ETIS_data.get("FULLTEXT_URL"), ETIS_data.get("URL")):
        if URL:
            version = "submitted_version" if re.search(PREPRINT_URL_PATTERN, URL, flags=re.IGNORECASE) else None
            attempts += [{"SOURCE": "etis", "URL": URL, "VERSION": version, "HOST_TYPE": None}]
    return attempts


def get_URL_key(URL: str) -> str:
    """
    Gives a URL without the scheme in lowercase, for finding the same link in several sources (e.g. http and https, dx.doi.org and doi.org).
    """
    URL_key = re.sub(r"^https?://", "", URL.strip().lower())
    return re.sub(r"^dx\.doi\.org/", "doi.org/", URL_key).rstrip("/")


def get_fulltext_attempts(open_data_candidate: dict, openalex_data: dict, research_products: list[dict], ETIS_data: dict) -> list[dict]:
    """
    Gives the full text sources to try for an article, best first:
    PMC, open PDFs and pages of published versions and author manuscripts, Zenodo records, PDF links and pages in OpenAIRE,
    ETIS links, OpenAlex cached copy, open preprints.
    """
    attempts = []
    europepmc = open_data_candidate.get("EUROPEPMC") or {}
    if europepmc.get("PMCID"):
        version = "accepted_version" if europepmc.get("IS_AUTHOR_MANUSCRIPT") else "published_version"
        attempts += [{"SOURCE": "pmc", "URL": PMC_ARTICLE_URL.format(europepmc["PMCID"]), "VERSION": version, "HOST_TYPE": "repository"}]

    open_locations = get_open_locations(openalex_data)
    for location in open_locations:
        if get_version_code(location) in PEER_REVIEWED_VERSIONS and location.get("pdf_url"):
            attempts += [{"SOURCE": "openalex_pdf", "URL": location["pdf_url"], "VERSION": get_version_code(location), "HOST_TYPE": get_host_type(location)}]
    for location in open_locations:
        # Journal pages can have the full text in HTML. Repository landing pages can only link the PDF - tried if OpenAlex doesn't have the PDF link
        host_type = get_host_type(location)
        if get_version_code(location) in PEER_REVIEWED_VERSIONS and location.get("landing_page_url") and (host_type != "repository" or not location.get("pdf_url")):
            attempts += [{"SOURCE": "openalex_html", "URL": location["landing_page_url"], "VERSION": get_version_code(location), "HOST_TYPE": host_type}]

    # OpenAIRE copies and ETIS links are free, so they go before the OpenAlex cached copy
    openaire_attempts = get_openaire_attempts(research_products)
    etis_attempts = get_etis_attempts(ETIS_data)
    attempts += [attempt for attempt in openaire_attempts + etis_attempts if attempt["VERSION"] != "submitted_version"]

    content_URLs = openalex_data.get("content_urls") or {}
    if OPENALEX_API_KEY and content_URLs:
        content_URL = content_URLs.get("grobid_xml") or content_URLs.get("pdf")
        attempts += [{"SOURCE": "openalex_content", "URL": content_URL, "VERSION": None, "HOST_TYPE": None}]

    for location in open_locations:
        if get_version_code(location) not in PEER_REVIEWED_VERSIONS and location.get("pdf_url"):
            attempts += [{"SOURCE": "openalex_pdf", "URL": location["pdf_url"], "VERSION": get_version_code(location), "HOST_TYPE": get_host_type(location)}]
    attempts += [attempt for attempt in openaire_attempts + etis_attempts if attempt["VERSION"] == "submitted_version"]

    # Same URL can be in several locations
    unique_attempts = []
    for attempt in attempts:
        if get_URL_key(attempt["URL"]) not in [get_URL_key(unique_attempt["URL"]) for unique_attempt in unique_attempts]:
            unique_attempts += [attempt]
    return unique_attempts


#####################
# Environment setup #
#####################

# Create directories
os.makedirs(FULLTEXT_DIRECTORY_PATH, exist_ok=True)

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

# Full texts are saved to data/fulltext/<GUID>.<pdf|xml|html|docx> with a plain text copy <GUID>.txt
# and a <GUID>.json file that tells where the full text came from (see doc/data_schema.md). Articles that already have a full text are skipped

# Reload data from save files
articles = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "articles")
open_data_candidates = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_data_candidates")
openalex_works = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openalex_works")
openaire_research_products = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openaire_research_products")

open_data_candidates_index = {item["GUID"]: item for item in open_data_candidates}
openalex_works_index = {item["GUID"]: item for item in openalex_works}
openaire_research_products_index = {item["GUID"]: item["DATA"] for item in openaire_research_products}

ncbi_session = NcbiSession()
zenodo_session = ZenodoSession()
download_session = PoliteSession(BROWSER_USER_AGENT)
openalex_session = PoliteSession()
if OPENALEX_API_KEY:
    openalex_session.headers.update({"Authorization": f'Bearer {OPENALEX_API_KEY}'})

n_skipped = 0
for article in tqdm.tqdm(articles, desc="Getting full texts"):
    GUID = article["GUID"]
    info_file_path = f'{FULLTEXT_DIRECTORY_PATH.rstrip("/")}/{GUID}.json'
    manual_attempts = []
    if os.path.exists(info_file_path):
        with open(info_file_path, encoding="utf8") as read_file:
            fulltext_info = json.loads(read_file.read())
        if fulltext_info["TEXT_FILE"] or not RETRY_FAILED:
            n_skipped += 1
            continue
        # Articles that were looked for by hand without result (get_manual_fulltexts) keep that record
        manual_attempts = [attempt for attempt in fulltext_info["ATTEMPTS"] if attempt["SOURCE"].startswith("manual_")]

    open_data_candidate = open_data_candidates_index.get(GUID) or {}
    openalex_data = (openalex_works_index.get(GUID) or {}).get("DATA") or {}
    fulltext_info = {
        "GUID": GUID,
        "DOI": article["DOI"],
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

    research_products = openaire_research_products_index.get(GUID) or []
    for attempt in get_fulltext_attempts(open_data_candidate, openalex_data, research_products, article["ETIS"]):
        saved = None
        try:
            if attempt["SOURCE"] == "pmc":
                response = ncbi_session.get_pmc_article(re.search(r"PMC\d+", attempt["URL"]).group())
                time.sleep(0.4)     # NCBI allows 3 requests per second without an API key
                if not response:
                    attempt["RESULT"], attempt["RESULT_DETAIL"] = "http_error", str(response.status_code)
                elif "<body" not in response.text:
                    # Publisher doesn't allow full text XML
                    attempt["RESULT"], attempt["RESULT_DETAIL"] = "no_fulltext_xml", None
                else:
                    if re.search(r"<meta-name>pmc-prop-preprint</meta-name>\s*<meta-value>yes", response.text):
                        attempt["VERSION"] = "submitted_version"
                    saved = save_fulltext(GUID, response.text, "xml", MIN_TEXT_LENGTH)
                    attempt["RESULT"], attempt["RESULT_DETAIL"] = "ok" if saved else "text_too_short", None

            elif attempt["SOURCE"] == "zenodo":
                # Zenodo record lists its files
                zenodo_match = re.search(ZENODO_RECORD_PATTERN, attempt["URL"], flags=re.IGNORECASE)
                response = zenodo_session.get_record(zenodo_match.group(1) or zenodo_match.group(2))
                fulltext_URL = get_zenodo_fulltext_URL(response.json()) if response else None
                if not response:
                    attempt["RESULT"], attempt["RESULT_DETAIL"] = "http_error", str(response.status_code)
                elif not fulltext_URL:
                    # No open PDF or Word file in the record
                    attempt["RESULT"], attempt["RESULT_DETAIL"] = "no_fulltext_file", None
                else:
                    attempt["URL"] = fulltext_URL
                    saved, attempt["RESULT"], attempt["RESULT_DETAIL"] = save_downloaded_fulltext(GUID, zenodo_session.get_politely(fulltext_URL), article["TITLE"])

            else:
                # Journal pages and the pages that ETIS links to can have the full text in HTML. Other pages can only link the PDF
                session = openalex_session if attempt["SOURCE"] == "openalex_content" else download_session
                is_page_accepted = attempt["SOURCE"] in ("openalex_html", "etis") and attempt["HOST_TYPE"] != "repository"
                saved, attempt["RESULT"], attempt["RESULT_DETAIL"], attempt["URL"] = save_linked_fulltext(GUID, session, attempt["URL"], article["TITLE"], is_page_accepted)
                if saved and attempt["SOURCE"] == "etis" and not text_has_title(saved[1], article["TITLE"], None):
                    # ETIS links can point to another document
                    for path in saved[:2]:
                        os.remove(path)
                    saved = None
                    attempt["RESULT"], attempt["RESULT_DETAIL"] = "title_not_found", None
        except Exception as exception:
            attempt["RESULT"], attempt["RESULT_DETAIL"] = "exception", type(exception).__name__

        fulltext_info["ATTEMPTS"] += [attempt]
        if saved:
            fulltext_info["FILE"], fulltext_info["TEXT_FILE"], fulltext_info["N_CHARACTERS"] = saved
            for key in ("SOURCE", "URL", "VERSION", "HOST_TYPE"):
                fulltext_info[key] = attempt[key]
            break
    fulltext_info["ATTEMPTS"] += manual_attempts

    with open(info_file_path, "w", encoding="utf8") as save_file:
        save_file.write(json.dumps(fulltext_info, indent=2, ensure_ascii=False))

info_string = f'Got full texts. Skipped {n_skipped} articles that had a full text from an earlier run'
logger.info(info_string)


########################
# Save full text index #
########################

# Reload data from save file
articles = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "articles")

fulltext_index = []
for article in articles:
    info_file_path = f'{FULLTEXT_DIRECTORY_PATH.rstrip("/")}/{article["GUID"]}.json'
    if not os.path.exists(info_file_path):
        continue
    with open(info_file_path, encoding="utf8") as read_file:
        fulltext_index += [json.loads(read_file.read())]

fulltext_index_save_path = f'{RESULTS_DATA_DIRECTORY_PATH.rstrip("/")}/fulltext_index_{get_timestamp_string()}.json'
with open(fulltext_index_save_path, "w", encoding="utf8") as save_file:
    save_file.write(json.dumps(fulltext_index, indent=2, ensure_ascii=False))

n_found = len([item for item in fulltext_index if item["TEXT_FILE"]])
n_by_source = dict(collections.Counter(item["SOURCE"] for item in fulltext_index if item["TEXT_FILE"]))
n_peer_reviewed = len([item for item in fulltext_index if item["TEXT_FILE"] and item["VERSION"] in PEER_REVIEWED_VERSIONS])
info_string1 = f'{n_found} of the {len(articles)} articles have a full text ({n_peer_reviewed} published version or author manuscript). By source: {n_by_source}'
info_string2 = f'Saved full text index to {fulltext_index_save_path}'
logger.info(info_string1)
logger.info(info_string2)
