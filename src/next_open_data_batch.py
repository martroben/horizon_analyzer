# standard
import argparse
import json
import os
import re


##########
# Inputs #
##########

ASSESSMENTS_PATH = "./data/assessments/open_data_assessments.jsonl"
RESULTS_DATA_DIRECTORY_PATH = "./data/results/"

HINT_PATTERNS = [
    r"data (and (code|materials?|software) )?(availability|accessibility|sharing)",
    r"availability of (data|materials?)",
    r"code availability",
    r"(is|are) (publicly |freely |openly )?(available|accessible|deposited)",
    r"deposited",
    r"accession (numbers?|codes?|no\.?)",
    r"(up)?on (reasonable )?request",
    r"supplementa(ry|l) (data|materials?|information|files?|tables?|datasets?)",
    r"supporting information",
    r"source data",
    r"zenodo|figshare|dryad|osf\.io|github|gitlab|mendeley data|dataverse|pangaea|datadoi|kaggle|harvard dataverse",
    r"\b(GSE\d+|PRJ[EDN][A-Z]\d+|EGA[SD]\d+|PXD\d+|E-MTAB-\d+|SR[AXRP]\d+|ERP\d+)",
    r"arrayexpress|protein data bank|\bPDB\b|\bCCDC\b|\bENA\b|\bGEO\b",
    r"(biobank|data access committee|data use agreement|controlled access)",
    r"10\.5281/zenodo|10\.6084/m9\.figshare|10\.5061/dryad|10\.17632/"
]
FUNDING_PATTERNS = [
    r"horizon 2020|horizon europe|\bh2020\b|grant agreement|european research council|\bERC\b|marie (skłodowska|sklodowska)|european commission"
]
HINT_CONTEXT_CHARACTERS = 300   # Characters before and after a match
HINTS_MAX_CHARACTERS = 6000     # Maximum length of data hints per article
FUNDING_HINTS_MAX_CHARACTERS = 2000
GRANT_DATASETS_SHOWN = 5


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


def read_assessments(path: str) -> list[dict]:
    """
    Reads the open data assessments (one JSON object per line). Gives an empty list if there are none yet.
    """
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf8") as read_file:
        return [json.loads(line) for line in read_file if line.strip()]


def get_hints(text: str, patterns: list[str], max_characters: int) -> list[str]:
    """
    Gives text passages around the matches of patterns. Overlapping passages are joined.
    """
    spans = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            spans += [(max(0, match.start() - HINT_CONTEXT_CHARACTERS), min(len(text), match.end() + HINT_CONTEXT_CHARACTERS))]
    spans.sort()

    joined_spans = []
    for start, end in spans:
        if joined_spans and start <= joined_spans[-1][1]:
            joined_spans[-1] = (joined_spans[-1][0], max(end, joined_spans[-1][1]))
        else:
            joined_spans += [(start, end)]

    hints = []
    n_characters = 0
    for start, end in joined_spans:
        hint = " ".join(text[start:end].split())
        if n_characters + len(hint) > max_characters:
            hints += [f'... ({len(joined_spans) - len(hints)} more passages, see the full text)']
            break
        hints += [hint]
        n_characters += len(hint)
    return hints


def format_attempt(attempt: dict) -> str:
    """
    Gives a full text attempt as one line: source, version, URL and result.
    """
    result = f'{attempt.get("RESULT")} ({attempt["RESULT_DETAIL"]})' if attempt.get("RESULT_DETAIL") else attempt.get("RESULT")
    return f'{attempt["SOURCE"]} {attempt["VERSION"]} {attempt["URL"]}: {result}'


def print_dossier(item: dict, grant_datasets_index: dict) -> None:
    """
    Prints the info that is needed for the open data check of an article.
    """
    fulltext = item["FULLTEXT"]
    dossier = {key: item[key] for key in ("QUEUE_POSITION", "IS_PILOT", "GUID", "TITLE", "PERIODICAL", "DOI", "ETIS_PAGE_URL")}
    dossier["PROJECTS"] = item["PROJECTS"]
    dossier["OPEN_ACCESS"] = item["OPEN_ACCESS"]
    dossier["CANDIDATES"] = item["CANDIDATES"]
    dossier["FULLTEXT"] = {key: value for key, value in fulltext.items() if key != "ATTEMPTS"}
    dossier["FULLTEXT"]["FAILED_ATTEMPTS"] = [format_attempt(attempt) for attempt in fulltext.get("ATTEMPTS") or [] if attempt.get("RESULT") != "ok"]

    grant_datasets = {}
    for project in item["PROJECTS"]:
        datasets = (grant_datasets_index.get(project["HORIZON_ID"]) or {}).get("DATASETS") or []
        if datasets:
            grant_datasets[project["HORIZON_ID"]] = [f'{dataset["TITLE"]} ({", ".join(dataset["PIDS"]) or dataset["URL"]})' for dataset in datasets[:GRANT_DATASETS_SHOWN]]
    dossier["GRANT_DATASETS_SAMPLE"] = grant_datasets

    print(f'\n{"=" * 100}\n# {item["QUEUE_POSITION"]}. {item["GUID"]}\n{"=" * 100}')
    print(json.dumps(dossier, indent=1, ensure_ascii=False))

    text_file_path = fulltext.get("TEXT_FILE")
    if not text_file_path or not os.path.exists(text_file_path):
        print("\n## No cached full text")
        return
    with open(text_file_path, encoding="utf8") as read_file:
        text = read_file.read()
    print(f'\n## Beginning of the full text ({text_file_path})\n{" ".join(text[:800].split())}')
    print("\n## Data hints (passages around data keywords)")
    for hint in get_hints(text, HINT_PATTERNS, HINTS_MAX_CHARACTERS):
        print(f'- {hint}')
    funding_patterns = FUNDING_PATTERNS + [re.escape(project["HORIZON_ID"]) for project in item["PROJECTS"] if project["HORIZON_ID"]]
    funding_patterns += [re.escape(project["ACRONYM"]) for project in item["PROJECTS"] if project["ACRONYM"]]
    print("\n## Funding hints")
    for hint in get_hints(text, funding_patterns, FUNDING_HINTS_MAX_CHARACTERS):
        print(f'- {hint}')


########
# Main #
########

# Usage:
# uv run src/next_open_data_batch.py [n]             - next n (default 10) articles in the queue without an assessment
# uv run src/next_open_data_batch.py --guids <GUID>  - given articles
if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser(description="Print the next articles for the open data check")
    argument_parser.add_argument("n", type=int, nargs="?", default=10)
    argument_parser.add_argument("--guids", nargs="+")
    arguments = argument_parser.parse_args()

    queue = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_data_queue")
    grant_datasets = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "grant_datasets")
    grant_datasets_index = {item["HORIZON_ID"]: item for item in grant_datasets}
    assessed_GUIDs = {assessment["GUID"] for assessment in read_assessments(ASSESSMENTS_PATH)}

    # Articles without an Estonian author are left out
    n_no_estonian_author = len([item for item in queue if item["HAS_ESTONIAN_AUTHOR"] is False])
    if arguments.guids:
        batch = [item for item in queue if item["GUID"] in arguments.guids]
    else:
        batch = [item for item in queue if item["GUID"] not in assessed_GUIDs and item["HAS_ESTONIAN_AUTHOR"] is not False][:arguments.n]

    print(f'{len(assessed_GUIDs)} of {len(queue)} articles assessed ({n_no_estonian_author} without an Estonian author are skipped). Batch: {", ".join(item["GUID"] for item in batch)}')
    for item in batch:
        print_dossier(item, grant_datasets_index)
