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

ETIS_HORIZON_PROGRAMMES = {
    # ETIS programme code: framework programme
    "136": "h2020",             # Horizon 2020 EIT support
    "137": "h2020",             # Horisont 2020 ERA \u00f5ppetoolide toetus
    "442": "h2020",             # Horizon 2020
    "443": "h2020",             # ERA-NET (Horizon 2020)
    "450": "horizon_europe",    # Horizon Europe Programme
    "451": "horizon_europe"     # ERA-NET (Horizon Europe)
}
EIT_PROGRAMME_CODE = "136"
    # EIT grants are not OpenAIRE projects. EIT projects can't be matched by article grant links or titles
OPENAIRE_GRANT_ID_PREFIXES = {
    # OpenAIRE ID prefix of the grants of each framework programme
    "h2020": "corda__h2020::",
    "horizon_europe": "corda_____he::"
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
    path = f'{dir_path.rstrip("/")}/{files_latest}'

    with open(path, encoding="utf8") as read_file:
        data = json.loads(read_file.read())

    return data


def get_framework_programme(project: dict, OpenAIRE_ID: str | None) -> str | None:
    """
    Gives the framework programme of an ETIS project: the framework programme of its grant (OpenAIRE ID), or of its ETIS programme codes if it has no grant.
    ETIS programme codes can be wrong (e.g. Horizon Europe grants under the Horizon 2020 programme).
    Gives None if the ETIS programme codes are of several framework programmes.
    """
    for framework_programme, prefix in OPENAIRE_GRANT_ID_PREFIXES.items():
        if OpenAIRE_ID and OpenAIRE_ID.startswith(prefix):
            return framework_programme
    framework_programmes = {ETIS_HORIZON_PROGRAMMES[programme["ProgrammeCode"]] for programme in project["Programmes"] if programme["ProgrammeCode"] in ETIS_HORIZON_PROGRAMMES}
    return framework_programmes.pop() if len(framework_programmes) == 1 else None


def get_grant_ID_prefixes(project: dict) -> tuple[str]:
    """
    Gives the OpenAIRE grant ID prefixes of the framework programmes of an ETIS project.
    Only a grant from the same framework programme as the ETIS project can be its own grant.
    """
    return tuple(OPENAIRE_GRANT_ID_PREFIXES[ETIS_HORIZON_PROGRAMMES[programme["ProgrammeCode"]]] for programme in project["Programmes"] if programme["ProgrammeCode"] in ETIS_HORIZON_PROGRAMMES and programme["ProgrammeCode"] != EIT_PROGRAMME_CODE)


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
    programme_codes = [programme["ProgrammeCode"] for programme in project["Programmes"]]
    if set(programme_codes) & set(ETIS_HORIZON_PROGRAMMES):
        ETIS_horizon_projects += [project]


##################################################
# Get Horizon IDs by OpenAire search API results #
##################################################

project_searches = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openaire_project_searches")
project_searches_index = {item["GUID"]: item["SEARCHES"] for item in project_searches}

# ETIS fields that were searched, in the order of preference, with their names in the match descriptions
search_fields = {
    "FINANCIER_PROJECT_NUMBER": "financier project number",
    "ACRONYM": "acronym",
    "TITLE": "title"
}

search_API_matches = []
no_match_by_search_API = []
for project in ETIS_horizon_projects:

    searches = project_searches_index.get(project["Guid"])
    if not searches:
        no_match_by_search_API += [project]
        continue

    match = {
        "GUID": project["Guid"],
        "TITLE": project["TitleEng"],
        "MATCHED_BY": "search_api"
    }

    # Financier project number, acronym or title has a single match
    for field, field_name in search_fields.items():
        field_matches = searches[field]["HORIZON_IDS"]
        if len(field_matches) == 1:
            match["HORIZON_ID"] = field_matches[0]
            match["MATCH_DESCRIPTION"] = f'Search API {field_name} {searches[field]["QUERY"]}: {field_matches}'
            break

    # Acronym has several matches and there is a financier project number from ETIS data
    financier_project_number = searches["FINANCIER_PROJECT_NUMBER"]["QUERY"] or ""
    acronym_matches = searches["ACRONYM"]["HORIZON_IDS"]
    if "HORIZON_ID" not in match and acronym_matches and len(financier_project_number) >= 5:
        for acronym_match in acronym_matches:
            if fuzz.partial_token_sort_ratio(acronym_match, financier_project_number) == 100:
                match["HORIZON_ID"] = acronym_match
                match["MATCH_DESCRIPTION"] = f'Search API acronym {searches["ACRONYM"]["QUERY"]}: {acronym_matches} and ETIS financier project number: {financier_project_number}'
                break

    if "HORIZON_ID" in match:
        search_API_matches += [match]
    else:
        no_match_by_search_API += [project]

info_string = f'Found project Horizon IDs for {len(search_API_matches)} of {len(ETIS_horizon_projects)} ETIS projects by OpenAire search API'
logger.info(info_string)


##########################################
# Get Horizon IDs by article grant links #
##########################################

# Articles link to the grants that funded them: OpenAIRE research product project links and OpenAlex awards
# Only a grant with an Estonian partner (in OpenAIRE graph EE projects) can be the ETIS project's own grant
# The ETIS project's Horizon ID is the grant that most of its articles link to

openaire_projects = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openaire_projects")
openaire_research_products = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openaire_research_products")
openalex_works = read_latest_file(RAW_DATA_DIRECTORY_PATH, "openalex_works")
ETIS_articles = read_latest_file(RAW_DATA_DIRECTORY_PATH, "etis_articles")

grant_ID_prefixes = tuple(OPENAIRE_GRANT_ID_PREFIXES.values())
openaire_grants_index = {project["id"]: project for project in openaire_projects if project["id"].startswith(grant_ID_prefixes)}
openaire_grant_codes_index = {grant["code"]: grant for grant in openaire_grants_index.values()}

# Horizon IDs that each article links to
article_grant_links = {}
for research_products in openaire_research_products:
    for research_product in research_products["DATA"]:
        for project_link in research_product["projects"] or []:
            if project_link["id"] in openaire_grants_index:
                horizon_ID = openaire_grants_index[project_link["id"]]["code"]
                article_grant_links.setdefault(research_products["GUID"], set()).add(horizon_ID)

for openalex_work in openalex_works:
    openalex_awards = (openalex_work["DATA"] or {}).get("awards") or []
    for award in openalex_awards:
        # Award IDs are free text, e.g. "ePerMed (grant no. 692145)"
        for horizon_ID in re.findall(r"\b\d{6,9}\b", award["funder_award_id"] or ""):
            if horizon_ID in openaire_grant_codes_index:
                article_grant_links.setdefault(openalex_work["GUID"], set()).add(horizon_ID)

# Count links over the articles of each ETIS project
# Sorted, because set order changes between runs and the counts are saved in this order
grant_link_counts = {}
project_article_counts = collections.Counter()
for article in ETIS_articles:
    for project_GUID in article["PROJECT_GUIDS"]:
        project_article_counts[project_GUID] += 1
        grant_link_counts.setdefault(project_GUID, collections.Counter()).update(sorted(article_grant_links.get(article["GUID"], set())))

title_similarity_threshold = 85     # Linked grant title counts as the same as ETIS project title from this fuzz score

article_grant_link_matches = []
no_match_by_article_grant_links = []
for project in no_match_by_search_API:
    project_grant_ID_prefixes = get_grant_ID_prefixes(project)
    link_counts = grant_link_counts.get(project["Guid"]) or collections.Counter()
    candidates = [(horizon_ID, n_links) for horizon_ID, n_links in link_counts.most_common() if openaire_grant_codes_index[horizon_ID]["id"].startswith(project_grant_ID_prefixes)]

    # Articles can link more often to another grant of the same research group than to the project's own grant
    # Prefer a single linked grant with the same title as the ETIS project, otherwise a single most linked grant
    ETIS_title = (project["TitleEng"] or "").lower()
    title_candidates = []
    for candidate in candidates:
        candidate_title = (openaire_grant_codes_index[candidate[0]]["title"] or "").lower()
        if fuzz.token_set_ratio(ETIS_title, candidate_title) >= title_similarity_threshold:
            title_candidates += [candidate]

    if len(title_candidates) == 1:
        horizon_ID, n_links = title_candidates[0]
    elif candidates and (len(candidates) == 1 or candidates[0][1] > candidates[1][1]):
        horizon_ID, n_links = candidates[0]
    else:
        no_match_by_article_grant_links += [project]
        continue

    match = {
        "GUID": project["Guid"],
        "TITLE": project["TitleEng"],
        "HORIZON_ID": horizon_ID,
        "MATCHED_BY": "article_grant_links"
    }
    match_description = f'Linked by {n_links} of the {project_article_counts[project["Guid"]]} project articles. All links: {dict(candidates)}'
    match["MATCH_DESCRIPTION"] = match_description
    article_grant_link_matches += [match]

info_string = f'Found project Horizon IDs for {len(article_grant_link_matches)} of the remaining {len(no_match_by_search_API)} ETIS projects by article grant links'
logger.info(info_string)


#################################################
# Get Horizon IDs by OpenAire graph API records #
#################################################

# Remove leading/trailing parenthesised words
leading_parenthesis_pattern = r'^\([^\(\)]+\)\s*'
trailing_parenthesis_pattern = r'\s*\([^\(\)]+\)$'

# Remove leading/trailing words separated by hyphen or colon
leading_hyphen_pattern = r'^[\w\d]+\s*[-–:]\s*'
trailing_hyphen_pattern = r'\s*[-–]\s*[\w\d]+$'

remove_pattern = fr'{leading_parenthesis_pattern}|{trailing_parenthesis_pattern}|{leading_hyphen_pattern}|{trailing_hyphen_pattern}'

exact_title_matches = []
exact_title_match_fails = []
for project in tqdm.tqdm(no_match_by_article_grant_links, desc="Fuzzy matching project titles"):
    if not project["TitleEng"]:
        continue

    project_grant_ID_prefixes = get_grant_ID_prefixes(project)
    if not project_grant_ID_prefixes:
        continue

    ETIS_compare_string = re.sub(remove_pattern, "", project["TitleEng"].lower().strip())
    fuzz_scores = []
    for openaire_project in openaire_projects:
        if not openaire_project["title"]:
            continue
        if not openaire_project["id"].startswith(project_grant_ID_prefixes):
            continue

        openaire_compare_string = re.sub(remove_pattern, "", openaire_project["title"].lower().strip())

        # Lower the score for matches that are much shorter than input            
        length_coefficient = 1
        length_ratio = len(openaire_compare_string) / len(ETIS_compare_string)
        if length_ratio < 0.7:
            length_coefficient = length_ratio

        fuzz_score = {
            "GUID": project["Guid"],
            "TITLE": project["TitleEng"],
            "HORIZON_ID": openaire_project["code"],
            "OPENAIRE_ID": openaire_project["id"],
            "OPENAIRE_TITLE": openaire_project["title"],
            "FUZZ_SCORE": fuzz.partial_token_sort_ratio(ETIS_compare_string, openaire_compare_string) * length_coefficient,
        }
        fuzz_scores += [fuzz_score]

    fuzz_scores_sorted = sorted(fuzz_scores, key=lambda x: x["FUZZ_SCORE"], reverse=True)

    if fuzz_scores_sorted[0]["FUZZ_SCORE"] == 100 and fuzz_scores_sorted[1]["FUZZ_SCORE"] <= 85:
        exact_title_matches += [fuzz_scores_sorted[0]]
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

# Two best candidates of the projects without a title match, for manual checks
title_match_fails_string = "\n\n".join(
    f'{fuzz_scores[0]["TITLE"]} - {fuzz_scores[0]["OPENAIRE_TITLE"]} ({fuzz_scores[0]["FUZZ_SCORE"]})\n{fuzz_scores[1]["TITLE"]} - {fuzz_scores[1]["OPENAIRE_TITLE"]} ({fuzz_scores[1]["FUZZ_SCORE"]})'
    for fuzz_scores in approximate_title_match_fails)

info_string1 = f'Found project Horizon IDs for {len(exact_title_matches) + len(approximate_title_matches)} of the remaining {len(no_match_by_article_grant_links)} ETIS projects by title matching ({len(exact_title_matches)} exact, {len(approximate_title_matches)} approximate)'
info_string2 = f'Two best OpenAIRE graph title candidates (fuzz score) of the {len(approximate_title_match_fails)} projects without a title match:\n\n{title_match_fails_string}\n'
logger.info(info_string1)
logger.info(info_string2)


########################################################
# Summarise ETIS project Horizon IDs and data mandates #
########################################################

# One record per ETIS Horizon project. See doc/data_schema.md
# OpenAIRE graph project mandates:
# openAccessMandateForPublications - project has to give open access to its publications
# openAccessMandateForDataset - project has to give open access to its research data
#   (H2020 projects in the Open Research Data Pilot, i.e. Article 29.3 of the grant agreement; all Horizon Europe projects)

horizon_ID_matches = search_API_matches + article_grant_link_matches
for matched_by, title_matches in (("exact_title", exact_title_matches), ("approximate_title", approximate_title_matches)):
    for match in title_matches:
        match_description = f'OpenAire graph title {match["OPENAIRE_TITLE"]} (fuzz score {match["FUZZ_SCORE"]})'
        horizon_ID_matches += [match | {"MATCHED_BY": matched_by, "MATCH_DESCRIPTION": match_description}]

horizon_ID_matches_index = {match["GUID"]: match for match in horizon_ID_matches}
openaire_projects_index = {project["id"]: project for project in openaire_projects}

projects_summary = []
for project in ETIS_horizon_projects:
    match = horizon_ID_matches_index.get(project["Guid"]) or {}
    # Title matches give the OpenAIRE ID, other matches give only the Horizon ID
    openaire_project = openaire_projects_index.get(match.get("OPENAIRE_ID")) or openaire_grant_codes_index.get(match.get("HORIZON_ID")) or {}
    fundings = openaire_project.get("fundings") or []

    projects_summary += [{
        "GUID": project["Guid"],
        "TITLE": project["TitleEng"],
        "PROGRAMME_CODES": [programme["ProgrammeCode"] for programme in project["Programmes"]],
        "FRAMEWORK_PROGRAMME": get_framework_programme(project, openaire_project.get("id")),
        "HORIZON_ID": match.get("HORIZON_ID"),
        "OPENAIRE_ID": openaire_project.get("id"),
        "ACRONYM": openaire_project.get("acronym"),
        "MATCHED_BY": match.get("MATCHED_BY"),
        "MATCH_DESCRIPTION": match.get("MATCH_DESCRIPTION"),
        "ARTICLE_GRANT_LINK_COUNTS": dict(grant_link_counts.get(project["Guid"]) or {}),
        "FUNDING_STREAMS": [(funding.get("fundingStream") or {}).get("id") for funding in fundings],
        "CALL_IDENTIFIER": openaire_project.get("callIdentifier"),
        # All Horizon programmes (incl. ERA-NET and EIT) require open access to publications. OpenAIRE has the flag only for matched projects
        "HAS_PUBLICATION_MANDATE": True,
        "HAS_DATA_MANDATE": openaire_project.get("openAccessMandateForDataset")
    }]

projects_summary_save_path = f'{RESULTS_DATA_DIRECTORY_PATH.rstrip("/")}/projects_{get_timestamp_string()}.json'
with open(projects_summary_save_path, "w", encoding="utf8") as save_file:
    save_file.write(json.dumps(projects_summary, indent=2, ensure_ascii=False))

# Search API matches that the project's articles don't link to, although they link to other grants
search_API_link_conflicts = [item for item in projects_summary if item["MATCHED_BY"] == "search_api" and item["ARTICLE_GRANT_LINK_COUNTS"] and item["HORIZON_ID"] not in item["ARTICLE_GRANT_LINK_COUNTS"]]
n_matched = len([item for item in projects_summary if item["HORIZON_ID"]])
n_with_mandates = len([item for item in projects_summary if item["HAS_DATA_MANDATE"] is not None])
info_string1 = f'Found Horizon IDs for {n_matched} of the {len(projects_summary)} ETIS Horizon projects. {n_with_mandates} have OpenAIRE data mandate info. Saved to {projects_summary_save_path}'
info_string2 = f'Articles of {len(search_API_link_conflicts)} projects matched by OpenAire search API link to other grants but not to the matched one'
logger.info(info_string1)
logger.info(info_string2)
