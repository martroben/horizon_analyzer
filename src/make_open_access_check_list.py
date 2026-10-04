# standard
import collections
import datetime
import html
import json
import logging
import os
import re
import sys


##########
# Inputs #
##########

ASSESSMENTS_PATH = "./data/assessments/open_data_assessments.jsonl"
OPEN_ACCESS_CHECKS_PATH = "./data/assessments/open_access_checks.jsonl"
HAND_CHECKS_PATH = "./data/assessments/open_access_hand_checks.txt"
CHECK_LIST_PATH = "./data/fulltext/inbox/open_access_check_list.html"
RAW_DATA_DIRECTORY_PATH = "./data/raw/"
RESULTS_DATA_DIRECTORY_PATH = "./data/results/"

HAND_CHECK_VERDICTS = ["open", "not_open"]
GUID_PREFIX_LENGTH = 8
HAND_CHECKS_HEADER = """# Open access checks by hand, one article per line: <GUID prefix> <open|not_open> [comment]
# open: free to read without login on the publisher site (DOI) or through a link on the ETIS page (any version, preprints included)
# not_open: nothing free on the publisher site and no ETIS link to a free copy
# The list of articles to check: data/fulltext/inbox/open_access_check_list.html (uv run src/make_open_access_check_list.py)
"""
DOI_URL = "https://doi.org/{}"


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


def read_records(path: str) -> dict:
    """
    Reads JSON lines records (assessments, open access checks). Later records of the same article replace earlier ones.
    Gives records by GUID.
    """
    if not os.path.exists(path):
        return {}
    records = {}
    with open(path, encoding="utf8") as read_file:
        for line in read_file:
            if line.strip():
                record = json.loads(line)
                records[record["GUID"]] = record
    return records


def read_hand_checks(path: str, GUIDs: list[str]) -> tuple[dict, list[str]]:
    """
    Reads the open access checks by hand: lines "<GUID prefix> <open|not_open> [comment]", # starts a comment line.
    Gives checks by GUID ({"VERDICT", "COMMENT"}) and messages about lines that couldn't be read. A later line of the same article wins.
    """
    if not os.path.exists(path):
        return {}, []
    hand_checks = {}
    problems = []
    with open(path, encoding="utf8") as read_file:
        for i_line, line in enumerate(read_file, start=1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split(maxsplit=2)
            prefix = parts[0].lower()
            matches = [GUID for GUID in GUIDs if GUID.startswith(prefix)] if len(prefix) >= GUID_PREFIX_LENGTH else []
            if len(matches) != 1:
                problems += [f'line {i_line}: "{prefix}" is not the GUID prefix of an article ({GUID_PREFIX_LENGTH}+ characters)']
            elif len(parts) < 2 or parts[1] not in HAND_CHECK_VERDICTS:
                problems += [f'line {i_line}: verdict must be {" or ".join(HAND_CHECK_VERDICTS)}']
            else:
                hand_checks[matches[0]] = {"VERDICT": parts[1], "COMMENT": parts[2].strip() if len(parts) > 2 else None}
    return hand_checks, problems


def get_latest_check(*records: dict | None) -> dict | None:
    """
    Gives the latest of Claude's records of an article (open data assessment, open access check) by ASSESSED_AT.
    """
    records = [record for record in records if record and record.get("OPEN_ACCESS")]
    return max(records, key=lambda record: record["ASSESSED_AT"]) if records else None


def get_check_links(item: dict) -> list[tuple[str, str]]:
    """
    Gives the links (name, URL) to open for an article: DOI, ETIS links, ETIS page.
    """
    ETIS = item["OPEN_ACCESS"]["ETIS"]
    links = [("DOI", DOI_URL.format(item["DOI"]))] if item["DOI"] else []
    links += [("ETIS link", ETIS["URL"])] if ETIS["URL"] else []
    links += [("ETIS full text link", ETIS["FULLTEXT_URL"])] if ETIS["FULLTEXT_URL"] and ETIS["FULLTEXT_URL"] != ETIS["URL"] else []
    links += [("ETIS page", item["ETIS_PAGE_URL"])]
    return links


def make_check_list_table(items: list[dict]) -> str:
    """
    Gives an HTML table of articles to check, one section per publisher (biggest first).
    """
    publisher_counts = collections.Counter(item["PUBLISHER"] for item in items)
    sections = []
    for publisher, n_items in sorted(publisher_counts.items(), key=lambda x: (-x[1], x[0])):
        rows = []
        for item in sorted((item for item in items if item["PUBLISHER"] == publisher), key=lambda item: item["TITLE"] or ""):
            links = " ".join(f'<a href="{html.escape(URL)}" target="_blank" rel="noreferrer">{html.escape(name)}</a>' for name, URL in item["LINKS"])
            note = f'<div class="note">{html.escape(item["NOTE"])}</div>' if item["NOTE"] else ""
            rows += [
                f'<tr><td><code>{item["GUID"][:GUID_PREFIX_LENGTH]}</code></td>'
                f'<td>{html.escape(item["TITLE"] or "")}<div class="periodical">{html.escape(item["PERIODICAL"] or "")}</div>{note}</td>'
                f'<td class="links">{links}</td></tr>'
            ]
        sections += [f'<h3>{html.escape(publisher)} ({n_items})</h3>\n<table>\n' + "\n".join(rows) + '\n</table>']
    return "\n".join(sections)


def make_check_list_html(items: list[dict], n_hand_checks: int) -> str:
    """
    Gives the open access check list page.
    """
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Open access checks</title>
<style>
:root {{ color-scheme: light dark; font-family: system-ui, sans-serif; line-height: 1.4; }}
body {{ max-width: 75rem; margin: 2rem auto; padding: 0 1rem; }}
table {{ border-collapse: collapse; width: 100%; }}
td {{ border-top: 1px solid #8886; padding: 0.4rem 0.5rem; vertical-align: top; }}
code {{ font-size: 1rem; user-select: all; }}
.periodical {{ opacity: 0.65; font-size: 0.9rem; }}
.note {{ opacity: 0.65; font-size: 0.8rem; margin-top: 0.2rem; }}
.links a {{ margin-right: 0.7rem; white-space: nowrap; }}
</style>
</head>
<body>
<h1>Open access checks by hand ({len(items)})</h1>
<p>Made {datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} by <code>src/make_open_access_check_list.py</code>. {n_hand_checks} articles are checked by hand already.
Articles whose open access Claude couldn't settle, mostly because the publisher site refuses scripts. The grey note says what was tried.</p>
<p>From home in a private window, not logged in to any library. For each article open the DOI link and the ETIS links (the ETIS page shows the links too).
Write one line per article into <code>{HAND_CHECKS_PATH.removeprefix("./")}</code>: the GUID prefix (first column), then</p>
<ul>
<li><code>open</code> - the full text is free to read on the publisher site (DOI link), or through an ETIS link (any version, preprints and ResearchGate copies included),</li>
<li><code>not_open</code> - nothing free there (abstract, preview, purchase or login only).</li>
</ul>
<p>A comment can follow, e.g. <code>0815dfbf open etis preprint</code>. Run <code>uv run src/make_open_access_check_list.py</code> again: the list keeps only the articles that are left.</p>
{make_check_list_table(items)}
</body>
</html>
'''


#####################
# Environment setup #
#####################

# Logger
logger = logging.getLogger()
logger.setLevel("INFO")
logger.addHandler(logging.StreamHandler(sys.stdout))


###############################
# Make open access check list #
###############################

# Articles to check by hand: open access check needed (queue) or Claude's latest verdict unclear,
# and no open or not_open verdict from Claude's latest record or a hand check. Articles without an Estonian author are left out

queue = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_data_queue")
openalex_works = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openalex_works")
openalex_works_index = {item["GUID"]: item for item in openalex_works}
assessments = read_records(ASSESSMENTS_PATH)
open_access_checks = read_records(OPEN_ACCESS_CHECKS_PATH)

if not os.path.exists(HAND_CHECKS_PATH):
    with open(HAND_CHECKS_PATH, "w", encoding="utf8") as write_file:
        write_file.write(HAND_CHECKS_HEADER)
hand_checks, problems = read_hand_checks(HAND_CHECKS_PATH, [item["GUID"] for item in queue])
for problem in problems:
    logger.warning(f'{HAND_CHECKS_PATH}: {problem}')

check_list = []
n_settled_by_claude = 0
for item in queue:
    if item["HAS_ESTONIAN_AUTHOR"] is False or item["GUID"] in hand_checks:
        continue
    latest_check = get_latest_check(assessments.get(item["GUID"]), open_access_checks.get(item["GUID"]))
    verdict = latest_check["OPEN_ACCESS"]["VERDICT"] if latest_check else None
    if verdict in HAND_CHECK_VERDICTS:
        n_settled_by_claude += bool(item["OPEN_ACCESS"]["CHECK_NEEDED_REASON"])
        continue
    if not (item["OPEN_ACCESS"]["CHECK_NEEDED_REASON"] or verdict == "unclear"):
        continue

    openalex_source = (((openalex_works_index.get(item["GUID"]) or {}).get("DATA") or {}).get("primary_location") or {}).get("source") or {}
    check_list += [{
        "GUID": item["GUID"],
        "TITLE": item["TITLE"],
        "PERIODICAL": item["PERIODICAL"],
        "PUBLISHER": openalex_source.get("host_organization_name") or (f'DOI prefix {item["DOI"].split("/")[0]}' if item["DOI"] else "No DOI"),
        "LINKS": get_check_links(item),
        "NOTE": latest_check["OPEN_ACCESS"]["EVIDENCE"] if latest_check else None
    }]

with open(CHECK_LIST_PATH, "w", encoding="utf8") as save_file:
    save_file.write(make_check_list_html(check_list, len(hand_checks)))

check_needed_GUIDs = {item["GUID"] for item in queue if item["OPEN_ACCESS"]["CHECK_NEEDED_REASON"] and item["HAS_ESTONIAN_AUTHOR"] is not False}
info_string1 = f'Saved open access check list of {len(check_list)} articles to {CHECK_LIST_PATH}'
info_string2 = f'{len(check_needed_GUIDs)} open access checks needed: {n_settled_by_claude} settled by Claude, {len(check_needed_GUIDs & set(hand_checks))} by hand ({len(hand_checks)} hand checks in {HAND_CHECKS_PATH})'
logger.info(info_string1)
logger.info(info_string2)
