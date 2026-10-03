# standard
import json
import logging
import os
import re
import sys


##########
# Inputs #
##########

RESULTS_DATA_DIRECTORY_PATH = "./data/results/"


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


################
# Analyse data #
################

publications_open = []
publications_not_open = []
for publication in open_access_data:
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

# Not open publications that are pending a full text check because ETIS and OpenAlex disagree
publications_ambiguous = []
for publication in publications_not_open:
    if publication["IS_AVAILABLE_MANUALLY_CHECKED"] is None and bool(publication["IS_OPEN_ACCESS"]) != bool(publication["OPENALEX_HAS_OPEN_PEER_REVIEWED_VERSION"]):
        publications_ambiguous += [publication]

# Not open publications that OpenAlex has only as an open preprint or open copy of unknown version
publications_preprint_only = []
for publication in publications_not_open:
    if publication["OPENALEX_IS_OPEN_ACCESS"] and not publication["OPENALEX_HAS_OPEN_PEER_REVIEWED_VERSION"]:
        publications_preprint_only += [publication]

info_string1 = f'{len(publications_open)} of {len(open_access_data)} publications ({round(len(publications_open) / len(open_access_data) * 100)}%) are open to read'
info_string2 = f'{len(publications_ambiguous)} of the not open publications have ambiguous open access status. These are settled when the full text is checked'
info_string3 = f'{len(publications_preprint_only)} of the not open publications have only an open preprint or an open copy of unknown version in OpenAlex'
logger.info(info_string1)
logger.info(info_string2)
logger.info(info_string3)
