# standard
import collections
import datetime
import html
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import urllib.parse
# external
from thefuzz import fuzz
# local
import fulltext_conversion


##########
# Inputs #
##########

MANUAL_SOURCES = {
    "open": "manual_open",          # Free to read without login on the publisher site (DOI) or through an ETIS link
    "other": "manual_other",        # Other free copies (e.g. repository or ResearchGate copies that ETIS doesn't link to)
    "library": "manual_library"     # Library access
}
    # Inbox folders and the full text source codes of the files saved into them
NOT_FOUND_FILE_NAME = "not_found.txt"
    # GUID prefixes of articles that were looked for without result (open: no free copy, library: no access), one per line, comment after the prefix
FETCH_LIST_FILE_NAME = "fetch_list.html"
FULLTEXT_EXTENSIONS = [".pdf", ".docx", ".xml", ".html", ".htm"]
MIN_TEXT_LENGTH = 5000          # Shorter PDF, Word or XML text is not a full text (e.g. scanned PDF without text layer)
MIN_HTML_TEXT_LENGTH = 20000    # Shorter HTML text is not a full text (e.g. abstract page)
TITLE_SIMILARITY_THRESHOLD = 90 # Fuzzy match score (0-100) of the article title in a file
IDENTIFIER_SEARCH_CHARACTERS = [2000, 10000]
    # How far from the beginning of a file to look for the article's DOI and title: the title page first, then further (cover pages, page menus)
GUID_PREFIX_LENGTH = 8
SOURCE_LABELS = {
    "pmc": "PMC",
    "openalex_pdf": "OpenAlex",
    "openalex_html": "OpenAlex",
    "zenodo": "Zenodo",
    "openaire_pdf": "OpenAIRE",
    "openaire_html": "OpenAIRE",
    "etis": "ETIS link"
}
    # Link names of the automatic full text sources in the fetch list
VERSION_LABELS = {
    "published_version": "published",
    "accepted_version": "accepted",
    "submitted_version": "preprint"
}
DOI_URL = "https://doi.org/{}"
ETIS_PAGE_URL = "https://www.etis.ee/Portal/Publications/Display/{}"
GOOGLE_SCHOLAR_SEARCH_URL = "https://scholar.google.com/scholar?q={}"

FULLTEXT_DIRECTORY_PATH = "./data/fulltext/"
INBOX_DIRECTORY_PATH = "./data/fulltext/inbox/"
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


def normalise_words(text: str) -> str:
    """
    Gives lowercase text with only words, for fuzzy comparison.
    """
    return " ".join(re.sub(r"\W", " ", text.lower()).split())


def get_info_file_path(GUID: str) -> str:
    """
    Gives the path of the full text info file (sidecar) of an article.
    """
    return f'{FULLTEXT_DIRECTORY_PATH.rstrip("/")}/{GUID}.json'


def read_fulltext_info(article: dict) -> dict:
    """
    Reads the full text info file of an article. Gives an empty record if get_fulltext hasn't made one.
    """
    info_file_path = get_info_file_path(article["GUID"])
    if os.path.exists(info_file_path):
        with open(info_file_path, encoding="utf8") as read_file:
            return json.loads(read_file.read())
    return {
        "GUID": article["GUID"],
        "DOI": article["DOI"],
        "FILE": None,
        "TEXT_FILE": None,
        "N_CHARACTERS": None,
        "SOURCE": None,
        "URL": None,
        "VERSION": None,
        "HOST_TYPE": None,
        "RETRIEVED_AT": None,
        "ATTEMPTS": []
    }


def write_fulltext_info(fulltext_info: dict) -> None:
    """
    Writes the full text info file of an article.
    """
    with open(get_info_file_path(fulltext_info["GUID"]), "w", encoding="utf8") as save_file:
        save_file.write(json.dumps(fulltext_info, indent=2, ensure_ascii=False))


def get_articles_by_GUID_prefix(text: str, articles: list[dict]) -> list[dict]:
    """
    Gives the articles whose GUID starts with the GUID prefix at the beginning of text (e.g. a file name). Gives [] if text doesn't start with a GUID prefix.
    """
    prefix_match = re.match(f'[0-9a-f]{{{GUID_PREFIX_LENGTH}}}', text.lower())
    if not prefix_match:
        return []
    return [article for article in articles if article["GUID"].startswith(prefix_match.group())]


def identify_article(file_name: str, text: str, articles: list[dict]) -> tuple[dict | None, str]:
    """
    Finds the article of a full text file that was saved by hand: by the GUID prefix that the file name starts with,
    else by the article's DOI and title near the beginning of the text (the text can cite other articles further on).
    Gives the article and how it was found (guid_prefix, guid_prefix_only, doi_and_title, doi_or_title),
    or None and why not (ambiguous, no_match). guid_prefix_only: neither the DOI nor the title is in the text.
    """
    articles_index = {article["GUID"]: article for article in articles}
    prefix_articles = get_articles_by_GUID_prefix(file_name, articles)
    for n_characters in IDENTIFIER_SEARCH_CHARACTERS:
        beginning = text[:n_characters]
        words = normalise_words(beginning)
        no_spaces = re.sub(r"\s", "", beginning.lower())    # PDF text can break a DOI over lines
        DOI_matches = {article["GUID"] for article in articles if article["DOI"] and article["DOI"].lower() in no_spaces}
        title_matches = {article["GUID"] for article in articles if fuzz.partial_ratio(normalise_words(article["TITLE"] or ""), words) >= TITLE_SIMILARITY_THRESHOLD}

        if len(prefix_articles) == 1 and prefix_articles[0]["GUID"] in DOI_matches | title_matches:
            return prefix_articles[0], "guid_prefix"
        if len(prefix_articles) != 1:
            for matches, matched_by in ((DOI_matches & title_matches, "doi_and_title"), (DOI_matches | title_matches, "doi_or_title")):
                if len(matches) == 1:
                    return articles_index[matches.pop()], matched_by

    if len(prefix_articles) == 1:
        return prefix_articles[0], "guid_prefix_only"
    return None, "ambiguous" if DOI_matches | title_matches else "no_match"


def has_open_copy_sign(article: dict, fulltext_info: dict) -> bool:
    """
    Tells whether a source says that the article is free to read: ETIS, OpenAlex, the Jan 2025 manual check or an open copy in OpenAIRE.
    """
    is_open_by_metadata = article["ETIS"]["IS_OPEN_ACCESS"] or article["OPENALEX"]["IS_OPEN_ACCESS"] or article["MANUAL_CHECK"]["IS_OPEN_ACCESS"]
    has_openaire_copy = any(attempt["SOURCE"] in ("zenodo", "openaire_pdf", "openaire_html") for attempt in fulltext_info["ATTEMPTS"])
    return bool(is_open_by_metadata or has_openaire_copy)


def has_manual_attempt(fulltext_info: dict, source: str) -> bool:
    """
    Tells whether the article was already looked for by hand in the given manual source.
    """
    return any(attempt["SOURCE"] == source for attempt in fulltext_info["ATTEMPTS"])


def get_fetch_links(article: dict, fulltext_info: dict, has_copy_links: bool) -> list[tuple[str, str]]:
    """
    Gives the links (name, URL) to try for an article: DOI, the copies that get_fulltext tried (if has_copy_links), ETIS page, Google Scholar search.
    """
    links = [("DOI", DOI_URL.format(article["DOI"]))] if article["DOI"] else []
    if has_copy_links:
        for attempt in fulltext_info["ATTEMPTS"]:
            if attempt["SOURCE"] in SOURCE_LABELS and attempt["URL"]:
                version = VERSION_LABELS.get(attempt["VERSION"])
                links += [(f'{SOURCE_LABELS[attempt["SOURCE"]]}{f" ({version})" if version else ""}', attempt["URL"])]
    links += [
        ("ETIS", ETIS_PAGE_URL.format(article["GUID"])),
        ("Scholar", GOOGLE_SCHOLAR_SEARCH_URL.format(urllib.parse.quote_plus(f'"{article["TITLE"]}"')))
    ]
    # Same URL can be in several sources (http and https, dx.doi.org and doi.org)
    unique_links = {}
    for name, URL in links:
        URL_key = re.sub(r"^https?://(dx\.)?", "", URL.strip().lower()).rstrip("/")
        unique_links.setdefault(URL_key, (name, URL))
    return list(unique_links.values())


def make_fetch_list_table(items: list[dict]) -> str:
    """
    Gives an HTML table of articles to fetch, one section per publisher (biggest first).
    """
    publisher_counts = collections.Counter(item["PUBLISHER"] for item in items)
    sections = []
    for publisher, n_items in sorted(publisher_counts.items(), key=lambda x: (-x[1], x[0])):
        rows = []
        for item in sorted((item for item in items if item["PUBLISHER"] == publisher), key=lambda item: item["TITLE"] or ""):
            links = " ".join(f'<a href="{html.escape(URL)}" target="_blank" rel="noreferrer">{html.escape(name)}</a>' for name, URL in item["LINKS"])
            rows += [
                f'<tr><td><code>{item["GUID"][:GUID_PREFIX_LENGTH]}</code></td>'
                f'<td>{html.escape(item["TITLE"] or "")}<div class="periodical">{html.escape(item["PERIODICAL"] or "")}</div></td>'
                f'<td class="links">{links}</td></tr>'
            ]
        sections += [f'<h3>{html.escape(publisher)} ({n_items})</h3>\n<table>\n' + "\n".join(rows) + '\n</table>']
    return "\n".join(sections)


def make_fetch_list_html(open_round: list[dict], library_round: list[dict]) -> str:
    """
    Gives the fetch list page: the articles of the open round and the library round with links to try.
    """
    inbox = INBOX_DIRECTORY_PATH.rstrip("/")
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Full text fetch list</title>
<style>
:root {{ color-scheme: light dark; font-family: system-ui, sans-serif; line-height: 1.4; }}
body {{ max-width: 75rem; margin: 2rem auto; padding: 0 1rem; }}
table {{ border-collapse: collapse; width: 100%; }}
td {{ border-top: 1px solid #8886; padding: 0.4rem 0.5rem; vertical-align: top; }}
code {{ font-size: 1rem; user-select: all; }}
.periodical {{ opacity: 0.65; font-size: 0.9rem; }}
.links a {{ margin-right: 0.7rem; white-space: nowrap; }}
</style>
</head>
<body>
<h1>Full texts to fetch by hand</h1>
<p>Made {datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} by <code>src/get_manual_fulltexts.py</code>.
Save files (PDF if possible, else Word or the page as "Web Page, HTML only") into the inbox folders and run <code>uv run src/get_manual_fulltexts.py</code>.
Files are matched to articles by the DOI and title in them. If a file isn't matched, start its name with the GUID prefix of the article (first column).
After a run, this list has only the articles that are left.</p>

<h2>Open round ({len(open_round)})</h2>
<p>From home, not logged in to any library. Try the links of each article (DOI = publisher page).</p>
<ul>
<li>Free to read on the publisher site (DOI link) or through a link on the ETIS page (any version): save it into <code>{inbox}/open/</code>.</li>
<li>Free copy only elsewhere (e.g. a repository or ResearchGate copy that ETIS doesn't link to): save it into <code>{inbox}/other/</code>.</li>
<li>Nothing free: add the GUID prefix to <code>{inbox}/open/{NOT_FOUND_FILE_NAME}</code> (one per line, a comment can follow the prefix). The article moves to the library round.</li>
</ul>
{make_fetch_list_table(open_round)}

<h2>Library round ({len(library_round)})</h2>
<p>Articles with no sign of a free copy, and the articles that weren't found in the open round.
TalTech licensed full texts open in the TalTech network. National Library of Estonia: Taylor &amp; Francis, Oxford Academic and Emerald remotely for registered readers.</p>
<ul>
<li>Save the full text into <code>{inbox}/library/</code>.</li>
<li>No access: add the GUID prefix to <code>{inbox}/library/{NOT_FOUND_FILE_NAME}</code>.</li>
</ul>
{make_fetch_list_table(library_round)}
</body>
</html>
'''


#####################
# Environment setup #
#####################

# Create directories
for folder in MANUAL_SOURCES:
    os.makedirs(f'{INBOX_DIRECTORY_PATH.rstrip("/")}/{folder}', exist_ok=True)

# Logger
logger = logging.getLogger()
logger.setLevel("INFO")
logger.addHandler(logging.StreamHandler(sys.stdout))


###################################
# Ingest full texts saved by hand #
###################################

# Files that were saved into data/fulltext/inbox/<open|other|library>/ are moved to data/fulltext/<GUID>.<pdf|docx|xml|html>
# with a plain text copy, and the article's full text info file gets the manual source (see doc/data_schema.md).
# Files that can't be matched to an article without a full text stay in the inbox

# Reload data from save files
articles = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "articles")

n_ingested = collections.Counter()
n_not_found = collections.Counter()
for folder, source in MANUAL_SOURCES.items():
    folder_path = f'{INBOX_DIRECTORY_PATH.rstrip("/")}/{folder}'
    for file_name in sorted(os.listdir(folder_path)):
        path = f'{folder_path}/{file_name}'
        extension = os.path.splitext(file_name)[1].lower()
        if file_name == NOT_FOUND_FILE_NAME or not os.path.isfile(path):
            continue
        if extension not in FULLTEXT_EXTENSIONS:
            logger.warning(f'{folder}/{file_name}: not a full text file ({", ".join(FULLTEXT_EXTENSIONS)}) - left in the inbox')
            continue
        extension = ".html" if extension == ".htm" else extension

        # Convert a copy, so that nothing is written into the inbox
        with tempfile.TemporaryDirectory() as temporary_directory_path:
            temporary_file_path = f'{temporary_directory_path}/fulltext{extension}'
            shutil.copyfile(path, temporary_file_path)
            try:
                with open(fulltext_conversion.convert_file(temporary_file_path), encoding="utf8") as read_file:
                    text = read_file.read()
            except Exception as exception:
                logger.warning(f'{folder}/{file_name}: conversion failed ({type(exception).__name__}) - left in the inbox')
                continue
        if len(text) < (MIN_HTML_TEXT_LENGTH if extension == ".html" else MIN_TEXT_LENGTH):
            logger.warning(f'{folder}/{file_name}: text too short ({len(text)} characters, e.g. a scanned PDF or an abstract page) - left in the inbox')
            continue

        article, matched_by = identify_article(file_name, text, articles)
        if not article:
            reason = "several articles match" if matched_by == "ambiguous" else "no article matches"
            logger.warning(f'{folder}/{file_name}: {reason} - start the file name with the GUID prefix of the article (left in the inbox)')
            continue
        fulltext_info = read_fulltext_info(article)
        if fulltext_info["TEXT_FILE"]:
            logger.warning(f'{folder}/{file_name}: {article["GUID"][:GUID_PREFIX_LENGTH]} already has a full text ({fulltext_info["SOURCE"]}) - left in the inbox')
            continue
        if matched_by == "guid_prefix_only":
            logger.warning(f'{folder}/{file_name}: neither the DOI nor the title of {article["GUID"][:GUID_PREFIX_LENGTH]} is in the text - check that it\'s the article: {article["TITLE"]}')

        retrieved_at = datetime.datetime.fromtimestamp(os.path.getmtime(path), datetime.timezone.utc).isoformat(timespec="seconds")
        file_path = f'{FULLTEXT_DIRECTORY_PATH.rstrip("/")}/{article["GUID"]}{extension}'
        shutil.move(path, file_path)
        text_file_path = fulltext_conversion.convert_file(file_path)
        with open(text_file_path, encoding="utf8") as read_file:
            n_characters = len(read_file.read())

        fulltext_info |= {
            "FILE": file_path,
            "TEXT_FILE": text_file_path,
            "N_CHARACTERS": n_characters,
            "SOURCE": source,
            "URL": None,
            "VERSION": None,
            "HOST_TYPE": None,
            "RETRIEVED_AT": retrieved_at    # When the file was saved
        }
        fulltext_info["ATTEMPTS"] += [{"SOURCE": source, "URL": None, "VERSION": None, "HOST_TYPE": None, "RESULT": "ok", "RESULT_DETAIL": file_name}]
        write_fulltext_info(fulltext_info)
        n_ingested[source] += 1
        logger.info(f'{folder}/{file_name} -> {file_path} ({matched_by}): {article["TITLE"]}')

    # Articles that were looked for without result
    not_found_path = f'{folder_path}/{NOT_FOUND_FILE_NAME}'
    if not os.path.exists(not_found_path):
        continue
    with open(not_found_path, encoding="utf8") as read_file:
        lines = [line.strip() for line in read_file if line.strip() and not line.strip().startswith("#")]
    for line in lines:
        prefix, comment = (line.split(maxsplit=1) + [""])[:2]
        prefix_articles = get_articles_by_GUID_prefix(prefix, articles)
        if len(prefix_articles) != 1:
            logger.warning(f'{folder}/{NOT_FOUND_FILE_NAME}: "{prefix}" is not the GUID prefix of an article')
            continue
        fulltext_info = read_fulltext_info(prefix_articles[0])
        if any(attempt["SOURCE"] == source and attempt["RESULT"] == "not_found" for attempt in fulltext_info["ATTEMPTS"]):
            continue
        fulltext_info["ATTEMPTS"] += [{"SOURCE": source, "URL": None, "VERSION": None, "HOST_TYPE": None, "RESULT": "not_found", "RESULT_DETAIL": comment.strip(" -#:\t") or None}]
        write_fulltext_info(fulltext_info)
        n_not_found[source] += 1

info_string = f'Ingested {sum(n_ingested.values())} full texts {dict(n_ingested)}. Recorded {sum(n_not_found.values())} articles that were not found {dict(n_not_found)}'
logger.info(info_string)


########################
# Save full text index #
########################

# Only if something changed. Same index as get_fulltext saves

fulltext_index = [read_fulltext_info(article) for article in articles if os.path.exists(get_info_file_path(article["GUID"]))]

if n_ingested or n_not_found:
    fulltext_index_save_path = f'{RESULTS_DATA_DIRECTORY_PATH.rstrip("/")}/fulltext_index_{get_timestamp_string()}.json'
    with open(fulltext_index_save_path, "w", encoding="utf8") as save_file:
        save_file.write(json.dumps(fulltext_index, indent=2, ensure_ascii=False))

    n_found = len([item for item in fulltext_index if item["TEXT_FILE"]])
    n_by_source = dict(collections.Counter(item["SOURCE"] for item in fulltext_index if item["TEXT_FILE"]))
    info_string1 = f'{n_found} of the {len(articles)} articles have a full text. By source: {n_by_source}'
    info_string2 = f'Saved full text index to {fulltext_index_save_path}'
    logger.info(info_string1)
    logger.info(info_string2)


###################
# Save fetch list #
###################

# Articles without a full text: open round (some source says it's free to read) and library round (the rest and the ones not found in the open round).
# Articles that weren't found in the library round and articles without an Estonian author (not checked) are left out

openalex_works = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openalex_works")
openalex_works_index = {item["GUID"]: item for item in openalex_works}

open_round = []
library_round = []
for article in articles:
    fulltext_info = read_fulltext_info(article)
    if fulltext_info["TEXT_FILE"] or not article["HAS_ESTONIAN_AUTHOR"] or has_manual_attempt(fulltext_info, MANUAL_SOURCES["library"]):
        continue

    openalex_source = (((openalex_works_index.get(article["GUID"]) or {}).get("DATA") or {}).get("primary_location") or {}).get("source") or {}
    publisher = openalex_source.get("host_organization_name") or (f'DOI prefix {article["DOI"].split("/")[0]}' if article["DOI"] else "No DOI")
    is_open_round = has_open_copy_sign(article, fulltext_info) and not has_manual_attempt(fulltext_info, MANUAL_SOURCES["open"])
    item = {
        "GUID": article["GUID"],
        "TITLE": article["TITLE"],
        "PERIODICAL": article["PERIODICAL"],
        "PUBLISHER": publisher,
        "LINKS": get_fetch_links(article, fulltext_info, is_open_round)
    }
    if is_open_round:
        open_round += [item]
    else:
        library_round += [item]

fetch_list_save_path = f'{INBOX_DIRECTORY_PATH.rstrip("/")}/{FETCH_LIST_FILE_NAME}'
with open(fetch_list_save_path, "w", encoding="utf8") as save_file:
    save_file.write(make_fetch_list_html(open_round, library_round))

info_string = f'Saved fetch list to {fetch_list_save_path}: open round {len(open_round)} articles, library round {len(library_round)} articles'
logger.info(info_string)
