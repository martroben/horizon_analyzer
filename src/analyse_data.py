# standard
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
    # Articles without underlying data or without a readable full text are left out of the open data rates
DATA_LABELS = ["repository", "supplement", "public_source", "restricted", "on_request", "in_article", "not_available", "no_data", "no_fulltext"]
MAIN_DATA_MANDATE_GROUPS = ["H2020 mandate", "H2020 no mandate", "HE"]


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
    path = f'{dir_path.strip("/")}/{files_latest}'

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

# Open data queue and assessments exist after the open data checks have started
open_data_queue_index = {}
if any(file.startswith("open_data_queue_") for file in os.listdir(RESULTS_DATA_DIRECTORY_PATH)):
    open_data_queue_index = {item["GUID"]: item for item in read_latest_file(RESULTS_DATA_DIRECTORY_PATH, "open_data_queue")}
assessments = read_assessments(ASSESSMENTS_PATH)


#######################
# Analyse open access #
#######################

publications_open = []
publications_not_open = []
publications_settled_by_fulltext_check = []
for publication in open_access_data:
    # The full text check settles publications whose open access status needed checking (see make_open_data_queue)
    queue_item = open_data_queue_index.get(publication["GUID"]) or {}
    open_access_check_needed = bool((queue_item.get("OPEN_ACCESS") or {}).get("CHECK_NEEDED_REASON"))
    fulltext_verdict = ((assessments.get(publication["GUID"]) or {}).get("OPEN_ACCESS") or {}).get("VERDICT")
    if open_access_check_needed and fulltext_verdict in ("open", "not_open"):
        publications_settled_by_fulltext_check += [publication]
        if fulltext_verdict == "open":
            publications_open += [publication]
        else:
            publications_not_open += [publication]
        continue

    # Publication is open if it is manually verified that it's open
    if publication["IS_AVAILABLE_MANUALLY_CHECKED"]:
        publications_open += [publication]
        continue

    # Publication is open if ETIS and OpenAlex both say that it's open and there is no manually checked info
    # OpenAlex counts only open published versions and peer-reviewed manuscripts (Horizon open access mandate)
    if publication["IS_AVAILABLE_MANUALLY_CHECKED"] is None and publication["OPENALEX_HAS_OPEN_PEER_REVIEWED_VERSION"] and publication["IS_OPEN_ACCESS"]:
        publications_open += [publication]
        continue

    publications_not_open += [publication]

settled_GUIDs = {publication["GUID"] for publication in publications_settled_by_fulltext_check}

# Not open publications that are pending a full text check because ETIS and OpenAlex disagree
publications_ambiguous = []
for publication in publications_not_open:
    if publication["GUID"] in settled_GUIDs:
        continue
    if publication["IS_AVAILABLE_MANUALLY_CHECKED"] is None and bool(publication["IS_OPEN_ACCESS"]) != bool(publication["OPENALEX_HAS_OPEN_PEER_REVIEWED_VERSION"]):
        publications_ambiguous += [publication]

# Not open publications that OpenAlex has only as an open preprint or open copy of unknown version
publications_preprint_only = []
for publication in publications_not_open:
    if publication["GUID"] in settled_GUIDs:
        continue
    if publication["OPENALEX_IS_OPEN_ACCESS"] and not publication["OPENALEX_HAS_OPEN_PEER_REVIEWED_VERSION"]:
        publications_preprint_only += [publication]

n_open_access_checks = len([item for item in open_data_queue_index.values() if item["OPEN_ACCESS"]["CHECK_NEEDED_REASON"]])
info_string1 = f'{len(publications_open)} of {len(open_access_data)} publications ({round(len(publications_open) / len(open_access_data) * 100)}%) are open to read'
info_string2 = f'{len(publications_ambiguous)} of the not open publications have ambiguous open access status. These are settled when the full text is checked'
info_string3 = f'{len(publications_preprint_only)} of the not open publications have only an open preprint or an open copy of unknown version in OpenAlex'
info_string4 = f'{len(publications_settled_by_fulltext_check)} of the {n_open_access_checks} publications that need an open access check are settled by the full text check'
logger.info(info_string1)
logger.info(info_string2)
logger.info(info_string3)
logger.info(info_string4)


#####################
# Analyse open data #
#####################

publications_open_GUIDs = {publication["GUID"] for publication in publications_open}
open_data_rows = []
for GUID, assessment in assessments.items():
    if GUID not in open_data_queue_index:
        continue
    group = open_data_queue_index[GUID]["DATA_MANDATE_GROUP"]
    open_data_rows += [{
        "GUID": GUID,
        "GROUP": group if group in MAIN_DATA_MANDATE_GROUPS else "mixed or unknown",
        "DATA_LABEL": assessment["DATA_LABEL"],
        "IS_OPEN_ACCESS": GUID in publications_open_GUIDs
    }]

if open_data_rows:
    open_data = polars.DataFrame(open_data_rows).with_columns(
        IS_INCLUDED=~polars.col("DATA_LABEL").is_in(EXCLUDED_DATA_LABELS),
        IS_OPEN_DATA=polars.col("DATA_LABEL").is_in(OPEN_DATA_LABELS))

    # Label counts by data mandate group
    label_counts = (open_data
        .pivot(on="DATA_LABEL", index="GROUP", values="GUID", aggregate_function="len")
        .fill_null(0))
    label_counts = label_counts.select(["GROUP"] + [label for label in DATA_LABELS if label in label_counts.columns])

    # Open data rates among articles with underlying data and a readable full text
    group_rates = []
    for group, group_data in [("all", open_data)] + sorted(open_data.group_by("GROUP"), key=lambda item: str(item[0])):
        group_name = group if isinstance(group, str) else group[0]
        included = group_data.filter(polars.col("IS_INCLUDED"))
        n = included.height
        n_open_data = included.filter(polars.col("IS_OPEN_DATA")).height
        n_open_both = included.filter(polars.col("IS_OPEN_DATA") & polars.col("IS_OPEN_ACCESS")).height
        low, high = wilson_interval(n_open_data, n)
        group_rates += [{
            "GROUP": group_name,
            "ASSESSED": group_data.height,
            "WITH_DATA": n,
            "OPEN_DATA": n_open_data,
            "OPEN_DATA_%": round(n_open_data / n * 100) if n else None,
            "95%_CI": f'{round(low * 100)}-{round(high * 100)}%' if n else None,
            "OPEN_ACCESS_AND_OPEN_DATA": n_open_both
        }]

    with polars.Config(tbl_rows=-1, tbl_cols=-1, tbl_width_chars=200, tbl_hide_dataframe_shape=True, tbl_hide_column_data_types=True):
        logger.info(f'\nOpen data labels of {open_data.height} assessed articles by data mandate group:\n{label_counts}')
        logger.info(f'\nOpen data rates ({", ".join(OPEN_DATA_LABELS)}) of articles with underlying data and a readable full text:\n{polars.DataFrame(group_rates)}')
else:
    logger.info("No open data assessments yet")
