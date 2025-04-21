# standard
import datetime
import json
import logging
import os
import re
import sys
# external
from thefuzz import fuzz
import tqdm


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


# Remove leading/trailing parenthesised words
# Remove leading/trailing words separated by hyphen or colon
remove_pattern = r"^[\w\d]+\s*[-–:]\s*|^\([^\(\)]+\)\s*|\s*[-–]\s*[\w\d]+$|\s*\([^\(\)]+\)$"

exact_title_matches = []
fuzzy_title_matches = []
for project in tqdm.tqdm(no_match_by_search_API, desc="Fuzzy matching project titles"):
    fuzz_scores = []
    if not project["TitleEng"]:
        print("ETIS jama!")
        continue
    for openaire_graph_project in openaire_graph_projects:
        if not openaire_graph_project["title"]:
            continue

        ETIS_compare_string = re.sub(remove_pattern, "", project["TitleEng"].lower().strip())
        openaire_graph_compare_string = re.sub(remove_pattern, "", openaire_graph_project["title"].lower().strip())

        # Lower the score for matches that are too short            
        length_coefficient = 1
        length_ratio = len(openaire_graph_compare_string) / len(ETIS_compare_string)
        if length_ratio < 0.7:
            length_coefficient = length_ratio

        fuzz_score = {
            "GUID": project["Guid"],
            "TITLE": project["TitleEng"],
            "HORIZON_ID": openaire_graph_project["code"],
            "OPENAIRE_GRAPH_TITLE": openaire_graph_project["title"],
            "FUZZ_SCORE": fuzz.partial_token_sort_ratio(ETIS_compare_string, openaire_graph_compare_string) * length_coefficient,
        }
        fuzz_scores += [fuzz_score]

    fuzz_scores_sorted = sorted(fuzz_scores, key=lambda x: x["FUZZ_SCORE"], reverse=True)
    if fuzz_scores_sorted[0]["FUZZ_SCORE"] == 100 and fuzz_scores_sorted[1]["FUZZ_SCORE"] <= 85:
        exact_title_matches += [fuzz_scores_sorted[0]]
    else:
        fuzzy_title_matches += [fuzz_scores_sorted]


for fuzzy_scores in fuzzy_title_matches:
    print(f'{fuzzy_scores[0]["TITLE"]} - {fuzzy_scores[0]["OPENAIRE_GRAPH_TITLE"]} ({fuzzy_scores[0]["FUZZ_SCORE"]})\n{fuzzy_scores[1]["TITLE"]} - {fuzzy_scores[1]["OPENAIRE_GRAPH_TITLE"]} ({fuzzy_scores[1]["FUZZ_SCORE"]})\n{fuzzy_scores[2]["TITLE"]} - {fuzzy_scores[2]["OPENAIRE_GRAPH_TITLE"]} ({fuzzy_scores[2]["FUZZ_SCORE"]})\n\n')


# TODO: remove exact matches from comparison (2 cysles)
# TODO: separate setup for patterns

len(exact_title_matches)

> 85, < 70

remove_pattern = r'\b(on|the|a|and|of|for|in|to|with|by|as|at|an|is|are|that|which|what)\b'
title_cleaned = re.sub(remove_pattern, '', text, flags=re.IGNORECASE)


r"^{^-^\s} *- *"

re.sub(r"^[\w\d]+\s*-\s*|^\([^\(\)]+\)\s*|\s*-\s*[\w\d]+$|\s*\([^\(\)]+\)$", "", "Phosphoprocessors - Biological signal processing via multisite phosphorylation networks", flags=re.IGNORECASE)

"Mutated neo-antigens in hepatocellular carcinoma (HEPAMUT)"

len("EIT- Manufacturing Mobilitas 2019")
len("MOBILITY+")

weird = []
for openaire_graph_project in openaire_graph_projects:
    if not openaire_graph_project["title"]:
        weird += [openaire_graph_project]

# len(ETIS_horizon_projects)
# len(etis_project_horizon_IDs)
# len(no_match_by_search_API)

# https://github.com/seatgeek/thefuzz
# fuzz.partial_token_sort_ratio("random random text see on pealkiri", "on pealkisi")

