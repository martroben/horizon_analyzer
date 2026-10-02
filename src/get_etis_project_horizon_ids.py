# standard
import collections
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
RESULTS_DATA_DIRECTORY_PATH = "./data/results/"

ETIS_HORIZON_PROGRAM_CODES = [
    "136",      # Horizon 2020 EIT support
    "137",      # Horisont 2020 ERA \u00f5ppetoolide toetus
    "442",      # Horizon 2020
    "443",      # ERA-NET (Horizon 2020)
    "450",      # Horizon Europe Programme
    "451"       # ERA-NET (Horizon Europe)
]
OPENAIRE_PROJECT_ID_PREFIXES = {
    # OpenAIRE project ID prefix of the framework programme of each ETIS programme
    # 136 (Horizon 2020 EIT support) is missing, because EIT grants are not OpenAIRE projects
    "137": "corda__h2020::",    # Horizon 2020
    "442": "corda__h2020::",
    "443": "corda__h2020::",
    "450": "corda_____he::",    # Horizon Europe
    "451": "corda_____he::"
}


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
        if "HORIZON_ID" in match:
            etis_project_horizon_IDs += [match]
            continue

    no_match_by_search_API += [project]

info_string = f'Found project Horizon IDs for {len(etis_project_horizon_IDs)} of {len(ETIS_horizon_projects)} ETIS projects by OpenAire search API'
logger.info(info_string)


################################################
# Get Horizon IDs by publication project links #
################################################

# Articles link to the projects that funded them: OpenAIRE research product project links and OpenAlex awards
# Only a Horizon project with an Estonian partner (in OpenAIRE graph EE projects) can be the ETIS project's own grant
# The ETIS project's Horizon ID is the project that most of its articles link to

openaire_graph_projects = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openaire_graph_projects")
openaire_research_products = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openaire_research_products")
openalex_responses = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openalex_responses")
scientific_articles = read_latest_file(RAW_DATA_DIRECTORY_PATH, "scientific_articles")

horizon_ID_prefixes = tuple(set(OPENAIRE_PROJECT_ID_PREFIXES.values()))
openaire_horizon_projects_index = {project["id"]: project for project in openaire_graph_projects if project["id"].startswith(horizon_ID_prefixes)}
openaire_horizon_project_codes_index = {project["code"]: project for project in openaire_horizon_projects_index.values()}

# Horizon IDs that each article links to
article_project_links = {}
for research_product_response in openaire_research_products:
    for research_product in research_product_response["DATA"]:
        for project_link in research_product["projects"] or []:
            if project_link["id"] in openaire_horizon_projects_index:
                horizon_ID = openaire_horizon_projects_index[project_link["id"]]["code"]
                article_project_links.setdefault(research_product_response["GUID"], set()).add(horizon_ID)

for openalex_response in openalex_responses:
    openalex_awards = (openalex_response["DATA"] or {}).get("awards") or []
    for award in openalex_awards:
        # Award IDs are free text, e.g. "ePerMed (grant no. 692145)"
        for horizon_ID in re.findall(r"\b\d{6,9}\b", award["funder_award_id"] or ""):
            if horizon_ID in openaire_horizon_project_codes_index:
                article_project_links.setdefault(openalex_response["GUID"], set()).add(horizon_ID)

# Count links over the articles of each ETIS project
project_link_counts = {}
project_article_counts = collections.Counter()
for article in scientific_articles:
    for project_GUID in article["PROJECT_GUIDS"]:
        project_article_counts[project_GUID] += 1
        project_link_counts.setdefault(project_GUID, collections.Counter()).update(article_project_links.get(article["GUID"], set()))

title_similarity_threshold = 85     # Linked project title counts as the same as ETIS project title from this fuzz score

publication_link_matches = []
no_match_by_publication_links = []
for project in no_match_by_search_API:
    # Only a project from the same framework programme as the ETIS project can be its own grant
    project_ID_prefixes = tuple(OPENAIRE_PROJECT_ID_PREFIXES[program["ProgrammeCode"]] for program in project["Programmes"] if program["ProgrammeCode"] in OPENAIRE_PROJECT_ID_PREFIXES)
    link_counts = project_link_counts.get(project["Guid"]) or collections.Counter()
    candidates = [(horizon_ID, n_links) for horizon_ID, n_links in link_counts.most_common() if openaire_horizon_project_codes_index[horizon_ID]["id"].startswith(project_ID_prefixes)]

    # Articles can link more often to another grant of the same research group than to the project's own grant
    # Prefer a single linked project with the same title as the ETIS project, otherwise a single most linked project
    ETIS_title = (project["TitleEng"] or "").lower()
    title_candidates = []
    for candidate in candidates:
        candidate_title = (openaire_horizon_project_codes_index[candidate[0]]["title"] or "").lower()
        if fuzz.token_set_ratio(ETIS_title, candidate_title) >= title_similarity_threshold:
            title_candidates += [candidate]

    if len(title_candidates) == 1:
        horizon_ID, n_links = title_candidates[0]
    elif candidates and (len(candidates) == 1 or candidates[0][1] > candidates[1][1]):
        horizon_ID, n_links = candidates[0]
    else:
        no_match_by_publication_links += [project]
        continue

    match = {
        "GUID": project["Guid"],
        "TITLE": project["TitleEng"],
        "HORIZON_ID": horizon_ID,
        "MATCHED_BY": "Publication project links"
    }
    match_description = f'Linked by {n_links} of the {project_article_counts[project["Guid"]]} project articles. All links: {dict(candidates)}'
    match["MATCH_DESCRIPTION"] = match_description
    publication_link_matches += [match]

info_string = f'Found project Horizon IDs for {len(publication_link_matches)} of the remaining {len(no_match_by_search_API)} ETIS projects by publication project links'
logger.info(info_string)


#################################################
# Get Horizon IDs by OpenAire graph API records #
#################################################

openaire_graph_projects = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openaire_graph_projects")

# Remove leading/trailing parenthesised words
leading_parenthesis_pattern = r'^\([^\(\)]+\)\s*'
trailing_parenthesis_pattern = r'\s*\([^\(\)]+\)$'

# Remove leading/trailing words separated by hyphen or colon
leading_hyphen_pattern = r'^[\w\d]+\s*[-–:]\s*'
trailing_hyphen_pattern = r'\s*[-–]\s*[\w\d]+$'

remove_pattern = fr'{leading_parenthesis_pattern}|{trailing_parenthesis_pattern}|{leading_hyphen_pattern}|{trailing_hyphen_pattern}'

exact_title_matches = []
exact_title_match_fails = []
for project in tqdm.tqdm(no_match_by_publication_links, desc="Fuzzy matching project titles"):
    fuzz_scores = []
    if not project["TitleEng"]:
        continue

    # Only a project from the same framework programme as the ETIS project can be its own grant
    project_ID_prefixes = tuple(OPENAIRE_PROJECT_ID_PREFIXES[program["ProgrammeCode"]] for program in project["Programmes"] if program["ProgrammeCode"] in OPENAIRE_PROJECT_ID_PREFIXES)
    if not project_ID_prefixes:
        continue

    for openaire_graph_project in openaire_graph_projects:
        if not openaire_graph_project["title"]:
            continue
        if not openaire_graph_project["id"].startswith(project_ID_prefixes):
            continue

        ETIS_compare_string = re.sub(remove_pattern, "", project["TitleEng"].lower().strip())
        openaire_graph_compare_string = re.sub(remove_pattern, "", openaire_graph_project["title"].lower().strip())

        # Lower the score for matches that are much shorter than input            
        length_coefficient = 1
        length_ratio = len(openaire_graph_compare_string) / len(ETIS_compare_string)
        if length_ratio < 0.7:
            length_coefficient = length_ratio

        fuzz_score = {
            "GUID": project["Guid"],
            "TITLE": project["TitleEng"],
            "HORIZON_ID": openaire_graph_project["code"],
            "OPENAIRE_ID": openaire_graph_project["id"],
            "OPENAIRE_GRAPH_TITLE": openaire_graph_project["title"],
            "FUZZ_SCORE": fuzz.partial_token_sort_ratio(ETIS_compare_string, openaire_graph_compare_string) * length_coefficient,
        }
        fuzz_scores += [fuzz_score]

    fuzz_scores_sorted = sorted(fuzz_scores, key=lambda x: x["FUZZ_SCORE"], reverse=True)

    if fuzz_scores_sorted[0]["FUZZ_SCORE"] == 100 and fuzz_scores_sorted[1]["FUZZ_SCORE"] <= 85:
        exact_match = fuzz_scores_sorted[0]
        exact_title_matches += [exact_match]
        # Matched OpenAIRE projects stay in the candidate pool - several ETIS records can be the same Horizon project
    else:
        exact_title_match_fails += [fuzz_scores_sorted]


approximate_title_matches = []
approximate_title_match_fails = []
for fuzz_scores in exact_title_match_fails:
    if fuzz_scores[0]["FUZZ_SCORE"] >= 85 and fuzz_scores[1]["FUZZ_SCORE"] < 70:
        approximate_title_matches += [fuzz_scores[0]]
    else:
        approximate_title_match_fails += [fuzz_scores]

for fuzz_scores in approximate_title_match_fails:
    print(f'{fuzz_scores[0]["TITLE"]} - {fuzz_scores[0]["OPENAIRE_GRAPH_TITLE"]} ({fuzz_scores[0]["FUZZ_SCORE"]})\n{fuzz_scores[1]["TITLE"]} - {fuzz_scores[1]["OPENAIRE_GRAPH_TITLE"]} ({fuzz_scores[1]["FUZZ_SCORE"]})\n\n')


# Manual checks:
# 0b60c91e-4bce-4afc-a5de-6cca642e82ec Universities for Deep Tech and Entrepreneurship ? https://eit-hei.eu/projects/united/
# EIT-Health Mobilitas 06ddba63-b2b3-438d-86fe-a5574dacfe81 ?
# Exploitation of extracellular vesicles for precision diagnostics of prostate cancer fac0ede3-fca1-47e5-b5b3-85510f930a5c: 643638
# Multi-centre study on Echinococcus multilocularis and Echinococcus granulosus s.l. in Europe: development and harmonization of diagnostic methods in the food chain 5a326ac0-b2ea-4955-8766-0e01bb918909: 773830


########################################################
# Summarise ETIS project Horizon IDs and data mandates #
########################################################

# OpenAIRE graph project mandates:
# openAccessMandateForPublications - project has to give open access to its publications
# openAccessMandateForDataset - project has to give open access to its research data
#   (H2020 projects in the Open Research Data Pilot, i.e. Article 29.3 of the grant agreement; all Horizon Europe projects)

horizon_ID_matches = etis_project_horizon_IDs + publication_link_matches
for match in exact_title_matches:
    match_description = f'OpenAire graph title {match["OPENAIRE_GRAPH_TITLE"]} (fuzz score {match["FUZZ_SCORE"]})'
    horizon_ID_matches += [match | {"MATCHED_BY": "Exact title match", "MATCH_DESCRIPTION": match_description}]
for match in approximate_title_matches:
    match_description = f'OpenAire graph title {match["OPENAIRE_GRAPH_TITLE"]} (fuzz score {match["FUZZ_SCORE"]})'
    horizon_ID_matches += [match | {"MATCHED_BY": "Approximate title match", "MATCH_DESCRIPTION": match_description}]

horizon_ID_matches_index = {match["GUID"]: match for match in horizon_ID_matches}
openaire_graph_projects_index = {project["id"]: project for project in openaire_graph_projects}

ETIS_project_horizon_IDs_summary = []
for project in ETIS_horizon_projects:
    match = horizon_ID_matches_index.get(project["Guid"]) or {}
    # Title matches give the OpenAIRE graph project ID, other matches give only the Horizon ID
    openaire_project = openaire_graph_projects_index.get(match.get("OPENAIRE_ID")) or openaire_horizon_project_codes_index.get(match.get("HORIZON_ID")) or {}
    fundings = openaire_project.get("fundings") or []

    project_summary = {
        "GUID": project["Guid"],
        "TITLE": project["TitleEng"],
        "PROGRAMME_CODES": [program["ProgrammeCode"] for program in project["Programmes"]],
        "HORIZON_ID": match.get("HORIZON_ID"),
        "OPENAIRE_ID": openaire_project.get("id"),
        "MATCHED_BY": match.get("MATCHED_BY"),
        "MATCH_DESCRIPTION": match.get("MATCH_DESCRIPTION"),
        "PUBLICATION_PROJECT_LINKS": dict(project_link_counts.get(project["Guid"]) or {}),
        "FUNDING_STREAMS": [(funding.get("fundingStream") or {}).get("id") for funding in fundings],
        "CALL_IDENTIFIER": openaire_project.get("callIdentifier"),
        "OPEN_ACCESS_MANDATE_FOR_PUBLICATIONS": openaire_project.get("openAccessMandateForPublications"),
        "OPEN_ACCESS_MANDATE_FOR_DATASET": openaire_project.get("openAccessMandateForDataset")
    }
    ETIS_project_horizon_IDs_summary += [project_summary]

ETIS_project_horizon_IDs_summary_save_path = f'{RESULTS_DATA_DIRECTORY_PATH.strip("/")}/etis_project_horizon_ids_{get_timestamp_string()}.json'
with open(ETIS_project_horizon_IDs_summary_save_path, "w", encoding="utf8") as save_file:
    save_file.write(json.dumps(ETIS_project_horizon_IDs_summary, indent=2, ensure_ascii=False))

# Search API matches that the project's articles don't link to, although they link to other Horizon projects
search_API_link_conflicts = [item for item in ETIS_project_horizon_IDs_summary if item["MATCHED_BY"] == "OpenAire search API" and item["PUBLICATION_PROJECT_LINKS"] and item["HORIZON_ID"] not in item["PUBLICATION_PROJECT_LINKS"]]
n_matched = len([item for item in ETIS_project_horizon_IDs_summary if item["HORIZON_ID"]])
n_with_mandates = len([item for item in ETIS_project_horizon_IDs_summary if item["OPEN_ACCESS_MANDATE_FOR_DATASET"] is not None])
info_string1 = f'Found Horizon IDs for {n_matched} of the {len(ETIS_project_horizon_IDs_summary)} ETIS Horizon projects. {n_with_mandates} have OpenAIRE data mandate info. Saved to {ETIS_project_horizon_IDs_summary_save_path}'
info_string2 = f'Articles of {len(search_API_link_conflicts)} projects matched by OpenAire search API link to other Horizon projects but not to the matched one'
logger.info(info_string1)
logger.info(info_string2)
