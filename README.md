# Horizon analyser

## How it works
How often are the scientific articles of Estonian Horizon 2020 and Horizon Europe projects open access, and how often are their research data open, as the Horizon grants require?

1. **Articles**: ETIS (Estonian Research Information System) has the Estonian Horizon projects and the publications they report. The project uses the published scientific articles (ETIS classifications 1.1.-1.3.) of finished projects. ETIS records with the same DOI are one article. OpenAlex (by DOI, or by title if there is no DOI) gives the published author lists with affiliations.
2. **Grants and mandates**: ETIS often lacks the Horizon grant number, so ETIS projects are matched to Horizon grants in OpenAIRE: by the OpenAIRE search API (financier project number, acronym, title), by the grants that the project's articles link to (OpenAIRE, OpenAlex), or by fuzzy title matching. All Horizon grants require open access to publications. OpenAIRE tells which grants also require open research data.
3. **Open access**: ETIS and OpenAlex say whether an article is free to read. Open access follows the Horizon definition: the published version or the peer-reviewed accepted manuscript is free to read (preprints don't count). OpenAIRE adds repository copies that OpenAlex doesn't know. When the sources disagree, the full text check decides.
4. **Open data**: no metadata source reliably says whether an article's data are shared, so every article is read. Full texts come from PMC, open copies in OpenAlex and OpenAIRE (e.g. Zenodo), the full text links in ETIS and OpenAlex cached copies. Candidate data links come from ScholeXplorer, DataCite, Europe PMC and the OpenAIRE datasets of the grant. Claude Code reads each article and labels its data (e.g. repository, supplement, on request, not available) with quotes and links that a validator checks. Articles are checked in random order, so the checked ones are a random sample.
5. **Analysis**: one record per article with its projects, grants and mandates. Only articles with an Estonian author count, because researchers are accountable only for the articles they wrote. Open data rates are compared by data mandate.

## API Documentation
- ETIS API: https://avaandmed.eesti.ee/datasets/eesti-teadusinfosusteemi-avaandmed
- OpenAlex API: https://docs.openalex.org
- OpenAIRE Graph API: https://graph.openaire.eu/docs/apis/graph-api/
- OpenAIRE search API: https://graph.openaire.eu/docs/apis/search-api/projects
- ScholeXplorer API: https://api.scholexplorer.openaire.eu/swagger-ui/index.html
- DataCite REST API: https://support.datacite.org/docs/api
- Europe PMC APIs: https://europepmc.org/RestfulWebService, https://europepmc.org/AnnotationsApi
- NCBI E-utilities (PMC full texts): https://www.ncbi.nlm.nih.gov/books/NBK25499/
- Zenodo REST API: https://developers.zenodo.org/

## Setup
Dependencies are managed with [uv](https://docs.astral.sh/uv/). `uv sync` installs the locked dependencies into `.venv`. Add or upgrade dependencies with `uv add <package>` / `uv lock --upgrade-package <package>` and commit `pyproject.toml` and `uv.lock` together.

Secrets are files in `secrets/` (not committed), one file per secret, named by the secret (like secrets mounted in Kubernetes). Optional OpenAlex API key (free, https://openalex.org/settings/api): `secrets/openalex_api_key`. It raises the OpenAlex daily budget from $0.10 to $1 and enables downloads of OpenAlex cached full texts ($0.01 each). Title searches for articles without a DOI cost $0.001 each.

## Running
Run the scripts from the repository root with `uv run src/<script>.py`, in this order (result files in brackets):
1. `get_data` - ETIS projects and scientific articles, OpenAlex data of the articles (`articles`)
2. `get_openaire_graph_projects` - OpenAIRE projects with Estonian partners
3. `get_openaire_search_project_results` - OpenAIRE search API matches of the ETIS projects
4. `get_openaire_research_products` - OpenAIRE grant links of the articles
5. `get_etis_project_horizon_ids` - Horizon grants and mandates of the ETIS projects (`projects`)
6. `get_open_data_candidates` - candidate data links of the articles, OpenAIRE datasets of the grants (`open_data_candidates`, `grant_datasets`)
7. `get_fulltext` - full texts to `data/fulltext/` (not committed). Resumes where an earlier run stopped (`fulltext_index`)
8. `get_manual_fulltexts` - full texts saved by hand: lists the articles without a full text with links to try (`data/fulltext/inbox/fetch_list.html`). Save the files into `data/fulltext/inbox/open/` (free on the publisher site or in a repository), `other/` (other free copies) or `library/` (library access) and run it again (`fulltext_index`)
9. `make_open_data_queue` - everything known automatically about each article, in check order (`open_data_queue`)
10. Open data checks: ask Claude Code to run the `check-open-data` skill. It appends records to `data/assessments/open_data_assessments.jsonl` and checks them with `validate_open_data_assessments`
11. `analyse_data` - final open access and open data status of each article (`article_analysis`) and summary tables

Data files, fields and codes: [doc/data_schema.md](doc/data_schema.md). Decisions, findings and run results: [doc/dev_notes.md](doc/dev_notes.md).
