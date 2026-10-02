# Horizon analyser

## API Documentation
- ETIS API: https://avaandmed.eesti.ee/datasets/eesti-teadusinfosusteemi-avaandmed
- OpenAlex API: https://docs.openalex.org
- OpenAIRE Graph API: https://graph.openaire.eu/docs/apis/graph-api/
- OpenAIRE search API: https://graph.openaire.eu/docs/apis/search-api/projects

## Running
Run the scripts from the repository root, in this order:
1. `src/get_data.py` - ETIS projects, publications and scientific articles; open access info from OpenAlex
2. `src/get_openaire_graph_projects.py` - OpenAIRE projects with Estonian partners
3. `src/get_openaire_search_project_results.py` - OpenAIRE search API matches of ETIS projects
4. `src/get_openaire_research_products.py` - OpenAIRE project links of the scientific articles
5. `src/get_etis_project_horizon_ids.py` - Horizon IDs and data mandates of ETIS projects
6. `src/analyse_data.py`

OpenAlex title searches (for articles without a DOI) cost $0.001 each against a $0.10 daily budget. Set an `OPENALEX_API_KEY` environment variable to use a free API key with a $1 daily budget: https://openalex.org/settings/api
