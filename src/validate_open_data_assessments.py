# standard
import argparse
import glob
import json
import os
import re
import sys
import unicodedata
# external
import requests
from thefuzz import fuzz


##########
# Inputs #
##########

ASSESSMENTS_PATH = "./data/assessments/open_data_assessments.jsonl"
FULLTEXT_DIRECTORY_PATH = "./data/fulltext/"
RESULTS_DATA_DIRECTORY_PATH = "./data/results/"

DATA_LABELS = [
    "repository",       # Underlying data deposited in a public repository or database, openly downloadable
    "supplement",       # Supplementary files with actual data, openly downloadable
    "public_source",    # Only existing data that are openly downloadable from a cited public source
    "restricted",       # Controlled access (application, data use agreement, registration)
    "on_request",       # Available from the authors on request
    "in_article",       # Statement that all data are in the article (tables, figures), no data files
    "not_available",    # Data not shared, or no statement and no data found
    "no_data",          # No underlying research data (review, essay, theory)
    "no_fulltext"       # Full text not accessible and no data record that verifiably belongs to the article
]
LABELS_NEEDING_QUOTES = ["repository", "supplement", "public_source", "restricted", "on_request", "in_article"]
LABELS_NEEDING_COVERAGE = ["repository", "supplement", "public_source", "restricted"]
PEER_REVIEWED_VERSIONS = ["publishedVersion", "acceptedVersion"]
    # Open access needs the published version or the peer-reviewed author manuscript (Horizon open access mandate)
VERSIONS = PEER_REVIEWED_VERSIONS + ["submittedVersion", "unknown"]
DATA_COVERAGE_VALUES = ["full", "partial"]
DATA_LEVEL_VALUES = ["raw", "processed"]
OPEN_ACCESS_VERDICTS = ["open", "not_open", "unclear"]
CODE_VALUES = ["repository", "on_request", "not_shared", "not_mentioned", "not_applicable"]
CONFIDENCE_VALUES = ["high", "medium", "low"]
REQUIRED_FIELDS = {
    "GUID": str,
    "ASSESSED_AT": str,
    "ASSESSOR": str,
    "SOURCES": list,
    "FULLTEXT_VERSION": (str, type(None)),
    "OPEN_ACCESS": dict,
    "DATA_LABEL": str,
    "DATA_COVERAGE": (str, type(None)),
    "DATA_LEVEL": (str, type(None)),
    "DATA_LINKS": list,
    "QUOTES": list,
    "CODE": str,
    "HORIZON_GRANT_ACKNOWLEDGED": (bool, type(None)),
    "PROJECT_DATASETS_NOTE": (str, type(None)),
    "CONFIDENCE": str,
    "RATIONALE": str,
    "SIDE_NOTES": (str, type(None))
}
QUOTE_MIN_FUZZY_SCORE = 95      # Quotes that don't match exactly must match at least this well (PDF text extraction artefacts)
BLOCKING_STATUS_CODES = [401, 403, 405, 429]
    # Sites that refuse scripts. A link with these codes is reported as a warning, not an error
BROWSER_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"


#########################
# Classes and functions #
#########################

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


def normalise_text(text: str) -> str:
    """
    Normalises text for quote matching: ligatures, dashes, quote marks, hyphenated line breaks, link targets, whitespace, case.
    """
    text = unicodedata.normalize("NFKC", text).replace("­", "")
    text = re.sub(r"[‐-―−]", "-", text)
    text = re.sub(r"[‘’‚′`]", "'", text)
    text = re.sub(r"[“”„″]", '"', text)
    # Link targets that the full text conversion adds in brackets
    text = re.sub(r" ?\[(https?://|10\.)[^\]]*\]", "", text)
    # Words split by a hyphen at a line break in PDFs
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)
    text = " ".join(text.split())
    return text.lower()


def check_link(session: requests.Session, URL: str, cache: dict) -> tuple[str, str]:
    """
    Gives (level, message) for a link: level is ok, warning or error.
    DOIs without a resolver are sent to doi.org.
    """
    if re.match(r"^10\.\d{4,}/", URL):
        URL = f'https://doi.org/{URL}'
    if not URL.startswith("http"):
        return "error", f'not a URL: {URL}'
    if URL in cache:
        return cache[URL]
    try:
        response = session.get(URL, timeout=30, stream=True, allow_redirects=True)
        response.close()
        if response.ok:
            result = ("ok", f'{response.status_code} {URL}')
        elif response.status_code in BLOCKING_STATUS_CODES:
            result = ("warning", f'site refuses scripts ({response.status_code}), check by hand: {URL}')
        else:
            result = ("error", f'link doesn\'t resolve ({response.status_code}): {URL}')
    except requests.RequestException as exception:
        result = ("error", f'link doesn\'t resolve ({type(exception).__name__}): {URL}')
    cache[URL] = result
    return result


def validate_assessment(assessment: dict, queue_index: dict, check_links: bool, session: requests.Session, link_cache: dict) -> tuple[list, list]:
    """
    Gives lists of errors and warnings of an assessment.
    """
    errors = []
    warnings = []

    for field, field_type in REQUIRED_FIELDS.items():
        if field not in assessment:
            errors += [f'missing field {field}']
        elif not isinstance(assessment[field], field_type):
            errors += [f'{field} has wrong type {type(assessment[field]).__name__}']
    for field in assessment:
        if field not in REQUIRED_FIELDS:
            warnings += [f'unknown field {field}']
    if errors:
        return errors, warnings

    GUID = assessment["GUID"]
    label = assessment["DATA_LABEL"]
    if GUID not in queue_index:
        errors += ["GUID is not in the open data queue"]

    # Allowed values
    if label not in DATA_LABELS:
        errors += [f'unknown DATA_LABEL {label}']
    if assessment["FULLTEXT_VERSION"] not in VERSIONS + [None]:
        errors += [f'unknown FULLTEXT_VERSION {assessment["FULLTEXT_VERSION"]}']
    if assessment["DATA_COVERAGE"] not in DATA_COVERAGE_VALUES + [None]:
        errors += [f'unknown DATA_COVERAGE {assessment["DATA_COVERAGE"]}']
    if assessment["DATA_LEVEL"] not in DATA_LEVEL_VALUES + [None]:
        errors += [f'unknown DATA_LEVEL {assessment["DATA_LEVEL"]}']
    if assessment["CODE"] not in CODE_VALUES:
        errors += [f'unknown CODE {assessment["CODE"]}']
    if assessment["CONFIDENCE"] not in CONFIDENCE_VALUES:
        errors += [f'unknown CONFIDENCE {assessment["CONFIDENCE"]}']

    # Open access
    open_access = assessment["OPEN_ACCESS"]
    if open_access.get("VERDICT") not in OPEN_ACCESS_VERDICTS:
        errors += [f'unknown OPEN_ACCESS.VERDICT {open_access.get("VERDICT")}']
    if open_access.get("VERSION") not in VERSIONS + [None]:
        errors += [f'unknown OPEN_ACCESS.VERSION {open_access.get("VERSION")}']
    if open_access.get("VERDICT") == "open":
        if open_access.get("VERSION") not in PEER_REVIEWED_VERSIONS:
            errors += ["open access verdict open needs the published version or the accepted manuscript"]
        if not open_access.get("URL"):
            errors += ["open access verdict open needs the URL of the free copy"]
    if not open_access.get("EVIDENCE"):
        errors += ["OPEN_ACCESS.EVIDENCE is empty"]

    # Data label consistency
    if label in LABELS_NEEDING_COVERAGE and not (assessment["DATA_COVERAGE"] and assessment["DATA_LEVEL"]):
        errors += [f'{label} needs DATA_COVERAGE and DATA_LEVEL']
    if label in LABELS_NEEDING_QUOTES and not assessment["QUOTES"]:
        errors += [f'{label} needs at least one quote']
    if label in ("repository", "supplement"):
        if not any(link.get("OWN_DATA") and link.get("OPENLY_DOWNLOADABLE") for link in assessment["DATA_LINKS"]):
            errors += [f'{label} needs a link to the article\'s own data that is openly downloadable']
    if label == "public_source":
        if not any(link.get("OPENLY_DOWNLOADABLE") for link in assessment["DATA_LINKS"]):
            errors += ["public_source needs a link to the openly downloadable source data"]
    if label == "no_fulltext" and assessment["FULLTEXT_VERSION"]:
        errors += ["no_fulltext but FULLTEXT_VERSION is given"]
    if label != "no_fulltext" and not assessment["FULLTEXT_VERSION"]:
        warnings += [f'{label} without a full text - check that the evidence is enough']
    if not assessment["RATIONALE"].strip():
        errors += ["RATIONALE is empty"]

    # Quotes must be in the cached texts (full text and files saved during the check)
    text_files = sorted(glob.glob(f'{FULLTEXT_DIRECTORY_PATH.rstrip("/")}/{GUID}*.txt'))
    for source in assessment["SOURCES"]:
        if not os.path.exists(source):
            errors += [f'source file doesn\'t exist: {source}']
        elif os.path.abspath(source) not in [os.path.abspath(path) for path in text_files]:
            warnings += [f'source file is not a cached text of the article: {source}']
    texts = []
    for path in text_files:
        with open(path, encoding="utf8") as read_file:
            texts += [normalise_text(read_file.read())]
    for quote in assessment["QUOTES"]:
        normalised_quote = normalise_text(quote)
        if not texts:
            errors += [f'no cached text to check quote: "{quote[:80]}"']
        elif any(normalised_quote in text for text in texts):
            continue
        else:
            best_score = max(fuzz.partial_ratio(normalised_quote, text) for text in texts)
            if best_score >= QUOTE_MIN_FUZZY_SCORE:
                warnings += [f'quote matches only approximately ({best_score}): "{quote[:80]}"']
            else:
                errors += [f'quote not found in the cached texts (best match {best_score}): "{quote[:80]}"']

    # Links
    for link in assessment["DATA_LINKS"]:
        for key in ("URL", "DESCRIPTION", "OWN_DATA", "OPENLY_DOWNLOADABLE"):
            if key not in link:
                errors += [f'data link without {key}: {link}']
        if check_links and link.get("URL"):
            level, message = check_link(session, link["URL"], link_cache)
            if level == "error":
                errors += [message]
            elif level == "warning":
                warnings += [message]
    if check_links and open_access.get("VERDICT") == "open" and open_access.get("URL"):
        level, message = check_link(session, open_access["URL"], link_cache)
        if level != "ok":
            warnings += [f'open access URL: {message}']

    return errors, warnings


########
# Main #
########

# Usage: uv run src/validate_open_data_assessments.py [<GUID> ...] [--skip-links]
# Validates the latest assessment of the given articles (default: all assessed articles)
if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser(description="Validate the open data assessments")
    argument_parser.add_argument("guids", nargs="*")
    argument_parser.add_argument("--skip-links", action="store_true")
    arguments = argument_parser.parse_args()

    queue = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_data_queue")
    queue_index = {item["GUID"]: item for item in queue}

    if not os.path.exists(ASSESSMENTS_PATH):
        sys.exit(f'No assessments yet in {ASSESSMENTS_PATH}')

    # Later records of the same article replace earlier ones
    assessments = {}
    n_lines = 0
    n_bad_lines = 0
    n_replaced = 0
    with open(ASSESSMENTS_PATH, encoding="utf8") as read_file:
        for i_line, line in enumerate(read_file, start=1):
            if not line.strip():
                continue
            n_lines += 1
            try:
                assessment = json.loads(line)
            except json.JSONDecodeError as exception:
                print(f'Line {i_line}: not valid JSON ({exception})')
                n_bad_lines += 1
                continue
            if assessment.get("GUID") in assessments:
                n_replaced += 1
            assessments[assessment.get("GUID")] = assessment

    selected_GUIDs = arguments.guids or list(assessments)
    session = requests.Session()
    session.headers.update({"User-Agent": BROWSER_USER_AGENT})
    link_cache = {}
    n_errors = n_bad_lines
    n_warnings = 0
    for GUID in selected_GUIDs:
        if GUID not in assessments:
            print(f'\n{GUID}\n  ERROR no assessment')
            n_errors += 1
            continue
        errors, warnings = validate_assessment(assessments[GUID], queue_index, not arguments.skip_links, session, link_cache)
        n_errors += len(errors)
        n_warnings += len(warnings)
        if errors or warnings:
            print(f'\n{GUID} ({assessments[GUID].get("DATA_LABEL")})')
            for error in errors:
                print(f'  ERROR {error}')
            for warning in warnings:
                print(f'  WARNING {warning}')

    n_open_access_checks = len([GUID for GUID, item in queue_index.items() if item["OPEN_ACCESS"]["CHECK_NEEDED_REASON"]])
    n_open_access_checked = len([GUID for GUID in assessments if GUID in queue_index and queue_index[GUID]["OPEN_ACCESS"]["CHECK_NEEDED_REASON"]])
    print(f'\nValidated {len(selected_GUIDs)} assessments: {n_errors} errors, {n_warnings} warnings')
    print(f'{len(assessments)} of {len(queue)} articles assessed ({n_lines} records, {n_replaced} replaced by a later record). {n_open_access_checked} of {n_open_access_checks} open access checks done')
    sys.exit(1 if n_errors else 0)
