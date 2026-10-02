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
    if publication["IS_AVAILABLE_MANUALLY_CHECKED"] is None and publication["OPENALEX_IS_OPEN_ACCESS"] and publication["IS_OPEN_ACCESS"]:
        publications_open += [publication]
        continue

    publications_not_open += [publication]

info_string = f'{len(publications_open)} of {len(open_access_data)} publications ({round(len(publications_open) / len(open_access_data) * 100)}%) are open to read'
logger.info(info_string)
