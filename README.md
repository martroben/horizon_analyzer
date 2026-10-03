# Horizon analyser

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
8. `make_open_data_queue` - everything known automatically about each article, in check order (`open_data_queue`)
9. Open data checks: ask Claude Code to run the `check-open-data` skill. It appends records to `data/assessments/open_data_assessments.jsonl` and checks them with `validate_open_data_assessments`
10. `analyse_data` - final open access and open data status of each article (`article_analysis`) and summary tables

Data files, fields and codes: [doc/data_schema.md](doc/data_schema.md). Decisions, findings and run results: [doc/dev_notes.md](doc/dev_notes.md).
