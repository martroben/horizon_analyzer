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

## Setup
Dependencies are managed with [uv](https://docs.astral.sh/uv/). Install the locked dependencies into `.venv`:
```
uv sync
```
Add or upgrade dependencies with `uv add <package>` / `uv lock --upgrade-package <package>` and commit `pyproject.toml` and `uv.lock` together.

## Running
Run the scripts from the repository root with `uv run` (e.g. `uv run src/get_data.py`), in this order:
1. `src/get_data.py` - ETIS projects, publications and scientific articles; open access info from OpenAlex
2. `src/get_openaire_graph_projects.py` - OpenAIRE projects with Estonian partners
3. `src/get_openaire_search_project_results.py` - OpenAIRE search API matches of ETIS projects
4. `src/get_openaire_research_products.py` - OpenAIRE project links of the scientific articles
5. `src/get_etis_project_horizon_ids.py` - Horizon IDs and data mandates of ETIS projects
6. `src/get_open_data_candidates.py` - candidate data links of the articles (ScholeXplorer, DataCite, Europe PMC) and OpenAIRE datasets of their projects
7. `src/get_fulltext.py` - full texts of the articles to `data/fulltext/` (PMC, open PDFs and pages from OpenAlex locations). Resumes where an earlier run stopped
8. `src/make_open_data_queue.py` - queue of articles for the open data check, with everything that the check needs
9. Open data checks by Claude Code: ask Claude to run the `check-open-data` skill (`.claude/skills/check-open-data/SKILL.md`). Claude appends one record per article to `data/assessments/open_data_assessments.jsonl` and checks them with `src/validate_open_data_assessments.py`
10. `src/analyse_data.py`

OpenAlex title searches (for articles without a DOI) cost $0.001 each against a $0.10 daily budget. A free API key raises the daily budget to $1: https://openalex.org/settings/api.

Secrets are files in the `secrets/` folder of the repository root, one file per secret, file name is the secret name (like secrets mounted in Kubernetes). The folder is not committed (`secrets/` is in `.gitignore`). Save the OpenAlex API key (only the key) to `secrets/openalex_api_key`.

`get_fulltext.py` converts PDFs to text with `pdftotext` from poppler-utils (`sudo apt install poppler-utils`). With the OpenAlex API key it also downloads OpenAlex cached full texts ($0.01 each). Full texts are not committed (`data/fulltext/` is in `.gitignore`).
