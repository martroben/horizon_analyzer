# standard
import datetime
import json
import logging
import os
import re
import sys
# external
from thefuzz import fuzz


##########
# Inputs #
##########

RAW_DATA_DIRECTORY_PATH = "./data/raw/"

ETIS_HORIZON_PROGRAM_CODES = [
    "136",      # Horizon 2020 EIT support
    "137",      # Horisont 2020 ERA \u00f5ppetoolide toetus
    "442",      # Horizon 2020
    "443",      # ERA-NET (Horizon 2020)
    "450",      # Horizon Europe Programme
    "451"       # ERA-NET (Horizon Europe)
]


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


##############################
# Load ETIS Horizon projects #
##############################

ETIS_projects = read_latest_file(RAW_DATA_DIRECTORY_PATH, "etis_projects")

ETIS_horizon_projects = []
for project in ETIS_projects:
    programme_codes = [program["ProgrammeCode"] for program in project["Programmes"]]
    if set(programme_codes) & set(ETIS_HORIZON_PROGRAM_CODES):
        ETIS_horizon_projects += [project]


##################################################
# Get Horizon IDs by OpenAire search API results #
##################################################

openaire_search_project_results = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openaire_search_project_results")
openaire_search_project_results_index = {project["Guid"]["input"]: project for project in openaire_search_project_results}

etis_project_horizon_IDs = []
no_match_by_search_API = []
for project in ETIS_horizon_projects:

    search_result = openaire_search_project_results_index.get(project["Guid"])
    if not search_result:
        no_match_by_search_API += [project]
        continue

    match = {
        "GUID": project["Guid"],
        "TITLE": project["TitleEng"]
    }

    # Financier project number has a single match
    financier_project_number_input = search_result["FinancierProjectNr"]["input"]
    financier_project_number_matches = search_result["FinancierProjectNr"].get("result", [])
    if len(financier_project_number_matches) == 1:
        match["HORIZON_ID"] = financier_project_number_matches[0]
        match["MATCHED_BY"] = "OpenAire search API"
        match_description = f'Search API FinancierProjectNr {financier_project_number_input}: {financier_project_number_matches}'
        match["MATCH_DESCRIPTION"] = match_description
        etis_project_horizon_IDs += [match]
        continue

    # Acronym has a single match
    acronym_input = search_result["Acronym"]["input"]
    acronym_matches = search_result["Acronym"].get("result", [])
    if len(acronym_matches) == 1:
        match["HORIZON_ID"] = acronym_matches[0]
        match["MATCHED_BY"] = "OpenAire search API"
        match_description = f'Search API Acronym {acronym_input}: {acronym_matches}'
        match["MATCH_DESCRIPTION"] = match_description
        etis_project_horizon_IDs += [match]
        continue

    # Title has a single match
    title_input = search_result["TitleEng"]["input"]
    title_matches = search_result["TitleEng"].get("result", [])
    if len(title_matches) == 1:
        match["HORIZON_ID"] = title_matches[0]
        match["MATCHED_BY"] = "OpenAire search API"
        match_description = f'Search API Title {title_input}: {title_matches}'
        match["MATCH_DESCRIPTION"] = match_description
        etis_project_horizon_IDs += [match]
        continue

    # Acronym has several matches and there is a financier project number from ETIS data
    if acronym_matches and len(financier_project_number_input) >= 5:
        for acronym_match in acronym_matches:
            if fuzz.partial_token_sort_ratio(acronym_match, financier_project_number_input) == 100:
                match["HORIZON_ID"] = acronym_match
                match["MATCHED_BY"] = "OpenAire search API"
                match_description = f'Search API Acronym {acronym_input}: {acronym_matches} and ETIS financier project number: {financier_project_number_input}'
                match["MATCH_DESCRIPTION"] = match_description
                break
        continue

    no_match_by_search_API += [project]

info_string = f'Found project Horizon IDs for {len(etis_project_horizon_IDs)} of {len(ETIS_horizon_projects)} ETIS projects by OpenAire search API'
logger.info(info_string)


#################################################
# Get Horizon IDs by OpenAire graph API records #
#################################################

openaire_graph_projects = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openaire_graph_projects")

# len(ETIS_horizon_projects)
# len(etis_project_horizon_IDs)
# len(no_match_by_search_API)

# https://github.com/seatgeek/thefuzz
# fuzz.partial_token_sort_ratio("random random text see on pealkiri", "on pealkisi")

