# standard
import datetime
import json
import logging
import math
import os
import re
import sys
# external
import polars


##########
# Inputs #
##########

RESULTS_DATA_DIRECTORY_PATH = "./data/results/"
ASSESSMENTS_PATH = "./data/assessments/open_data_assessments.jsonl"

OPEN_DATA_LABELS = ["repository", "supplement", "public_source"]
    # Underlying data are freely downloadable (H2020 Art. 29.3 / Horizon Europe bar)
EXCLUDED_DATA_LABELS = ["no_data", "no_fulltext"]
    # Articles without underlying data or without a readable full text have no open data status
DATA_LABELS = ["repository", "supplement", "public_source", "restricted", "on_request", "in_article", "not_available", "no_data", "no_fulltext"]
PROJECT_FIELDS = [
    "GUID",
    "TITLE",
    "PROGRAMME_CODES",
    "HORIZON_ID",
    "ACRONYM",
    "FRAMEWORK_PROGRAMME",
    "OPEN_ACCESS_MANDATE_FOR_PUBLICATIONS",
    "OPEN_ACCESS_MANDATE_FOR_DATASET",
    "HORIZON_GRANT_LINKED"
]
    # Project info of the open data queue that the article analysis data has for each project of an article
TABLE_PRINT_OPTIONS = {
    "tbl_rows": -1,
    "tbl_cols": -1,
    "tbl_width_chars": 200,
    "tbl_hide_dataframe_shape": True,
    "tbl_hide_column_data_types": True,
    "fmt_str_lengths": 50
}
    # polars options for printing the summary tables: all rows and columns, no shape and data types


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


def read_assessments(path: str) -> dict:
    """
    Reads the open data assessments (one JSON object per line). Later records of the same article replace earlier ones.
    Gives assessments by GUID.
    """
    if not os.path.exists(path):
        return {}
    assessments = {}
    with open(path, encoding="utf8") as read_file:
        for line in read_file:
            if line.strip():
                assessment = json.loads(line)
                assessments[assessment["GUID"]] = assessment
    return assessments


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """
    Gives the Wilson score interval (95% by default) of a proportion k / n.
    """
    if not n:
        return (math.nan, math.nan)
    p = k / n
    centre = (p + z**2 / (2 * n)) / (1 + z**2 / n)
    half_width = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / (1 + z**2 / n)
    return (centre - half_width, centre + half_width)


def get_any(values: list[bool | None]) -> bool | None:
    """
    Gives True if any value is True, False if all values are False, otherwise None (unknown).
    """
    if any(values):
        return True
    if values and all(value is False for value in values):
        return False
    return None


def get_automatic_open_access(publication: dict, check_needed_reason: str | None) -> bool | None:
    """
    Gives the open access status of an article by ETIS, OpenAlex and the Jan 2025 manual checks.
    Gives None if the full text check has to settle it (see make_open_data_queue).
    """
    if check_needed_reason:
        return None
    if publication["IS_AVAILABLE_MANUALLY_CHECKED"] is not None:
        return publication["IS_AVAILABLE_MANUALLY_CHECKED"]
    # Without a check needed reason ETIS and OpenAlex agree
    # OpenAlex counts only open published versions and peer-reviewed manuscripts (Horizon open access mandate)
    return bool(publication["IS_OPEN_ACCESS"])


def summarise_rate(data: polars.DataFrame, value_column: str, group_column: str) -> polars.DataFrame:
    """
    Gives the number of articles with value_column True, False and unknown (null) by group_column,
    and the share of True among the known values with a 95% Wilson interval. The first row is all articles.
    """
    groups = [("all", data)] + sorted(data.group_by(group_column), key=lambda item: str(item[0]))
    rows = []
    for group, group_data in groups:
        group_value = group if isinstance(group, str) else group[0]
        group_name = "unknown" if group_value is None else str(group_value).lower()
        n_yes = group_data.filter(polars.col(value_column)).height
        n_no = group_data.filter(~polars.col(value_column)).height
        n_known = n_yes + n_no
        low, high = wilson_interval(n_yes, n_known)
        rows += [{
            group_column: group_name,
            "ARTICLES": group_data.height,
            "YES": n_yes,
            "NO": n_no,
            "UNKNOWN": group_data.height - n_known,
            "YES_%": round(n_yes / n_known * 100) if n_known else None,
            "95%_CI": f'{round(low * 100)}-{round(high * 100)}%' if n_known else None
        }]
    return polars.DataFrame(rows)


#####################
# Environment setup #
#####################

# Logger
logger = logging.getLogger()
logger.setLevel("INFO")
logger.addHandler(logging.StreamHandler(sys.stdout))


#############
# Load data #
#############

open_access_data = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_access_data")
open_data_queue = read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_data_queue")
assessments = read_assessments(ASSESSMENTS_PATH)

open_data_queue_index = {item["GUID"]: item for item in open_data_queue}


##############################
# Make article analysis data #
##############################

# One record per article: Estonian authors and institutions, ETIS projects with their Horizon grants and open access mandates,
# open access (publications) and open data verdicts.
# Article-level mandates and grant links are True if they hold for any of the article's projects

articles = []
for publication in open_access_data:
    queue_item = open_data_queue_index[publication["GUID"]]
    assessment = assessments.get(publication["GUID"]) or {}
    projects = [{field: project[field] for field in PROJECT_FIELDS} for project in queue_item["PROJECTS"]]

    # Full text check settles open access whenever it finds the status, also when ETIS and OpenAlex agree
    check_needed_reason = queue_item["OPEN_ACCESS"]["CHECK_NEEDED_REASON"]
    automatic_open_access = get_automatic_open_access(publication, check_needed_reason)
    fulltext_check_verdict = (assessment.get("OPEN_ACCESS") or {}).get("VERDICT")
    if fulltext_check_verdict in ("open", "not_open"):
        is_open_access = fulltext_check_verdict == "open"
        open_access_settled_by = "fulltext_check"
    elif automatic_open_access is not None:
        is_open_access = automatic_open_access
        open_access_settled_by = "manual_check" if publication["IS_AVAILABLE_MANUALLY_CHECKED"] is not None else "etis_and_openalex"
    else:
        is_open_access = None
        open_access_settled_by = None

    data_label = assessment.get("DATA_LABEL")
    is_open_data = None
    if data_label in OPEN_DATA_LABELS:
        is_open_data = True
    elif data_label and data_label not in EXCLUDED_DATA_LABELS:
        is_open_data = False

    articles += [{
        "GUID": publication["GUID"],
        "TITLE": publication["TITLE"],
        "PERIODICAL": publication["PERIODICAL"],
        "DOI": queue_item["DOI"],
        "AUTHORS": publication["AUTHORS"],
        "INSTITUTIONS": publication["INSTITUTIONS"],
        "HAS_ESTONIAN_AUTHOR": publication["HAS_ESTONIAN_AUTHOR"],
        "PROJECTS": projects,
        "OPEN_ACCESS_MANDATE_FOR_PUBLICATIONS": get_any([project["OPEN_ACCESS_MANDATE_FOR_PUBLICATIONS"] for project in projects]),
        "OPEN_ACCESS_MANDATE_FOR_DATASET": get_any([project["OPEN_ACCESS_MANDATE_FOR_DATASET"] for project in projects]),
        "HORIZON_GRANT_LINKED": get_any([project["HORIZON_GRANT_LINKED"] for project in projects]),
        "HORIZON_GRANT_ACKNOWLEDGED": assessment.get("HORIZON_GRANT_ACKNOWLEDGED"),
        "IS_OPEN_ACCESS": is_open_access,
        "OPEN_ACCESS_SETTLED_BY": open_access_settled_by,
        "OPEN_ACCESS_AUTOMATIC": automatic_open_access,
        "OPEN_ACCESS_FULLTEXT_CHECK": fulltext_check_verdict,
        "OPEN_ACCESS_CHECK_NEEDED_REASON": check_needed_reason,
        "DATA_LABEL": data_label,
        "DATA_COVERAGE": assessment.get("DATA_COVERAGE"),
        "IS_OPEN_DATA": is_open_data
    }]

articles_save_path = f'{RESULTS_DATA_DIRECTORY_PATH.rstrip("/")}/articles_{get_timestamp_string()}.json'
with open(articles_save_path, "w", encoding="utf8") as save_file:
    save_file.write(json.dumps(articles, indent=2, ensure_ascii=False))

# Researchers are accountable only for the articles they wrote - articles without an Estonian author are left out
analysis_columns = [
    "GUID", "HAS_ESTONIAN_AUTHOR", "OPEN_ACCESS_MANDATE_FOR_DATASET", "HORIZON_GRANT_LINKED", "HORIZON_GRANT_ACKNOWLEDGED", "IS_OPEN_ACCESS",
    "OPEN_ACCESS_SETTLED_BY", "OPEN_ACCESS_AUTOMATIC", "OPEN_ACCESS_FULLTEXT_CHECK", "DATA_LABEL", "IS_OPEN_DATA"
]
articles_data = polars.DataFrame([{column: article[column] for column in analysis_columns} for article in articles], infer_schema_length=None)
articles_in_scope = articles_data.filter(polars.col("HAS_ESTONIAN_AUTHOR").fill_null(True))

info_string1 = f'Saved analysis data of {len(articles)} articles to {articles_save_path}'
info_string2 = f'{articles_in_scope.height} of the {len(articles)} articles have an Estonian author (or it is unknown) and are analysed'
logger.info(info_string1)
logger.info(info_string2)


#######################
# Analyse open access #
#######################

# Open access = the published version or the peer-reviewed author manuscript is free to read (Horizon open access mandate)

open_access_rates = summarise_rate(articles_in_scope, "IS_OPEN_ACCESS", "HORIZON_GRANT_LINKED")
settled_by_counts = articles_in_scope.group_by("OPEN_ACCESS_SETTLED_BY").len().sort("OPEN_ACCESS_SETTLED_BY")

# Full text check verdicts compared to the automatic status - tells how reliable the automatic status is
open_access_agreement = (articles_in_scope
    .filter(polars.col("OPEN_ACCESS_AUTOMATIC").is_not_null() & polars.col("OPEN_ACCESS_FULLTEXT_CHECK").is_in(["open", "not_open"]))
    .group_by("OPEN_ACCESS_AUTOMATIC", "OPEN_ACCESS_FULLTEXT_CHECK").len()
    .sort("OPEN_ACCESS_AUTOMATIC", "OPEN_ACCESS_FULLTEXT_CHECK"))

with polars.Config(**TABLE_PRINT_OPTIONS):
    logger.info(f'\nOpen access of the articles by whether OpenAIRE or OpenAlex links the article to its ETIS project\'s Horizon grant:\n{open_access_rates}')
    logger.info(f'\nHow the open access status was settled (null = pending a full text check):\n{settled_by_counts}')
    if open_access_agreement.height:
        logger.info(f'\nAutomatic open access status (ETIS, OpenAlex, Jan 2025 manual checks) vs full text check:\n{open_access_agreement}')


#####################
# Analyse open data #
#####################

# Compliance with the data mandate can be derived by comparing the open data status with OPEN_ACCESS_MANDATE_FOR_DATASET

articles_assessed = articles_in_scope.filter(polars.col("DATA_LABEL").is_not_null())
if articles_assessed.height:
    # Label counts by data mandate
    label_counts = (articles_assessed
        .with_columns(polars.col("OPEN_ACCESS_MANDATE_FOR_DATASET").cast(polars.String).fill_null("unknown"))
        .pivot(on="DATA_LABEL", index="OPEN_ACCESS_MANDATE_FOR_DATASET", values="GUID", aggregate_function="len")
        .fill_null(0)
        .sort("OPEN_ACCESS_MANDATE_FOR_DATASET"))
    label_counts = label_counts.select(["OPEN_ACCESS_MANDATE_FOR_DATASET"] + [label for label in DATA_LABELS if label in label_counts.columns])

    # Unknown = no underlying data or no readable full text
    open_data_rates = summarise_rate(articles_assessed, "IS_OPEN_DATA", "OPEN_ACCESS_MANDATE_FOR_DATASET")

    with polars.Config(**TABLE_PRINT_OPTIONS):
        logger.info(f'\nOpen data labels of {articles_assessed.height} assessed articles by the data mandate of their projects:\n{label_counts}')
        logger.info(f'\nOpen data ({", ".join(OPEN_DATA_LABELS)}) of the assessed articles by the data mandate of their projects (unknown = {", ".join(EXCLUDED_DATA_LABELS)}):\n{open_data_rates}')
else:
    logger.info("No open data assessments yet")
