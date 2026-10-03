# Data schema

## Conventions
- Files are JSON lists of records, named `<name>_<UTC timestamp>.json`. Scripts read the file with the latest timestamp. `data/raw/` has API data (not committed), `data/results/` has derived data.
- Field names are upper snake case. Raw API records inside `DATA` keep the API's own field names.
- Boolean fields start with a verb: `IS_`, `HAS_`.
- Fields with a list value have a plural name. Counts start with `N_`. Timestamps end with `_AT` (ISO 8601, UTC). Paths to files end with `_FILE`.
- Missing values are `null`, never `""`.
- `GUID` is the record's own ETIS GUID. Other records are referred to by `<ENTITY>_GUID(S)`. `HORIZON_ID` is the grant number of a Horizon grant. `OPENAIRE_ID` is the OpenAIRE ID of the grant.
- Project = ETIS project. Grant = Horizon grant (an OpenAIRE / CORDIS project). Several ETIS projects can be the same grant (e.g. separate Estonian partners).
- Top-level fields are the values that the analysis uses. A block named after a source (`ETIS`, `OPENALEX`, `OPENAIRE`, `EUROPEPMC`, `SCHOLEXPLORER`, `DATACITE`, `MANUAL_CHECK`) has what that source says - the inputs that the values are decided from. Values in source blocks are as the source gives them (e.g. OpenAlex versions `publishedVersion`).
- Categorical values that this project defines are lower snake case codes. All codes are listed in [Codes](#codes).

## Files

| File | Script | One record |
|---|---|---|
| `raw/etis_projects` | `get_data` | ETIS project (API item) |
| `raw/etis_publications` | `get_data` | ETIS publication of the projects |
| `raw/etis_publications_without_data` | `get_data` | publication that ETIS API gave no data for |
| `raw/etis_articles` | `get_data` | published scientific article (ETIS classification 1.1.-1.3.) |
| `raw/openalex_works` | `get_data` | OpenAlex work of an article |
| `raw/openaire_projects` | `get_openaire_graph_projects` | OpenAIRE project with an Estonian partner (API item) |
| `raw/openaire_project_searches` | `get_openaire_search_project_results` | OpenAIRE search API results of an ETIS project |
| `raw/openaire_research_products` | `get_openaire_research_products` | OpenAIRE research products of an article |
| `raw/scholexplorer_links` | `get_open_data_candidates` | ScholeXplorer links of an article |
| `raw/datacite_records` | `get_open_data_candidates` | DataCite records related to an article |
| `raw/europepmc_records` | `get_open_data_candidates` | Europe PMC records of an article |
| `raw/openaire_project_datasets` | `get_open_data_candidates` | OpenAIRE datasets of a grant |
| `results/articles` | `get_data` | article: ETIS and OpenAlex info, authors |
| `results/projects` | `get_etis_project_horizon_ids` | ETIS Horizon project: grant and mandates |
| `results/grant_datasets` | `get_open_data_candidates` | grant: OpenAIRE datasets |
| `results/open_data_candidates` | `get_open_data_candidates` | article: Europe PMC info, candidate data links |
| `results/fulltext_index` | `get_fulltext` | article: cached full text (same as `fulltext/<GUID>.json`) |
| `results/open_data_queue` | `make_open_data_queue` | article: all automatic info, in check order |
| `assessments/open_data_assessments.jsonl` | Claude (`check-open-data` skill) | open data and open access check of an article (JSON lines, latest record of a GUID wins) |
| `results/article_analysis` | `analyse_data` | article: final open access and open data status |

## Raw data
API records are in `DATA` as the API gives them (`etis_projects` and `openaire_projects` are lists of API records without a wrapper).

| File | Fields |
|---|---|
| `etis_publications`, `etis_publications_without_data`, `etis_articles` | `GUID`, `PROJECT_GUIDS` (ETIS projects that report the publication), `DATA` (ETIS publication) |
| `openalex_works` | `GUID`, `FOUND_BY` (code, null if not found), `FAILED_QUERIES` (DOI and/or title that found nothing), `DATA` (OpenAlex work or null) |
| `openaire_project_searches` | `GUID`, `SEARCHES`: `FINANCIER_PROJECT_NUMBER`, `ACRONYM`, `TITLE` (the ETIS project fields that were searched), each with `QUERY` (null if ETIS has no value; not searched), `STATUS_CODE`, `HORIZON_IDS` (grant numbers found) |
| `openaire_research_products`, `scholexplorer_links`, `europepmc_records` | `GUID`, `DOI`, `DATA` (`scholexplorer_links`: links by target type; `europepmc_records`: records with the same DOI). `europepmc_records` also has `ACCESSION_NUMBERS` (Europe PMC text-mining annotations) |
| `datacite_records` | `GUID`, `DOI`, `N_FOUND` (records that the query found), `DATA` |
| `openaire_project_datasets` | `HORIZON_ID`, `OPENAIRE_ID`, `N_FOUND`, `DATA` (first 100 datasets) |

## articles

| Field | Type | |
|---|---|---|
| `GUID` | str | ETIS publication GUID |
| `TITLE`, `PERIODICAL` | str | from ETIS |
| `DOI` | str | ETIS DOI, or the DOI of the OpenAlex work found by title search if ETIS has none. All later steps use it |
| `PROJECT_GUIDS` | list[str] | ETIS projects that report the article |
| `AUTHORS` | list | ETIS authors (Estonian researchers): `GUID`, `NAME`, `IS_IN_OPENALEX_AUTHORS` (in the published author list; null if OpenAlex has no author list) |
| `INSTITUTIONS` | list | ETIS institutions: `GUID`, `NAME`, `REGISTRY_CODE` (business registry code of the legal entity) |
| `HAS_ESTONIAN_AUTHOR` | bool | an author in the published author list has an Estonian affiliation, or an ETIS author is in the list and ETIS gives an Estonian institution. Null if unknown |
| `ETIS` | object | `DOI`, `URL` (publication URL in ETIS), `IS_OPEN_ACCESS`, `OPEN_ACCESS_TYPE` (ETIS value: gold, hybrid, green, bronze, closed), `LICENSE` (ETIS licence name) |
| `OPENALEX` | object | `ID`, `FOUND_BY`, `DOI`, `IS_OPEN_ACCESS` (any open version, incl. preprints), `OPEN_ACCESS_TYPE` (OpenAlex `oa_status`), `OPEN_ACCESS_URL`, `OPEN_VERSIONS` (versions of the open locations, `unknown` if OpenAlex doesn't say), `HAS_OPEN_PEER_REVIEWED_VERSION` (open published version or accepted manuscript - Horizon open access), `HAS_ESTONIAN_AFFILIATION` (null if OpenAlex has no affiliations). All null if OpenAlex doesn't have the article |
| `MANUAL_CHECK` | object | `IS_OPEN_ACCESS`: Jan 2025 manual check (`data/manual/manually_checked_publications.json`), counted any free version (incl. preprints). Null if not checked |

## projects
One record per ETIS Horizon project (finished projects of the ETIS Horizon programmes).

| Field | Type | |
|---|---|---|
| `GUID` | str | ETIS project GUID |
| `TITLE` | str | ETIS English title |
| `PROGRAMME_CODES` | list[str] | ETIS programme codes (136 EIT, 137 ERA chairs, 442 H2020, 443 ERA-NET H2020, 450 Horizon Europe, 451 ERA-NET Horizon Europe, MUU other) |
| `FRAMEWORK_PROGRAMME` | str | code: framework programme of the grant, or of the ETIS programme codes if the project has no grant |
| `HORIZON_ID` | str | grant number; null if not matched |
| `OPENAIRE_ID` | str | OpenAIRE ID of the grant |
| `ACRONYM` | str | grant acronym in OpenAIRE |
| `MATCHED_BY` | str | code: how the grant was found |
| `MATCH_DESCRIPTION` | str | details of the match |
| `ARTICLE_GRANT_LINK_COUNTS` | object | grant number: number of the project's articles that link to the grant (OpenAIRE research product project links, OpenAlex awards). Only grants with an Estonian partner |
| `FUNDING_STREAMS` | list[str] | OpenAIRE funding stream IDs, e.g. `EC::H2020::RIA` |
| `CALL_IDENTIFIER` | str | OpenAIRE call identifier |
| `HAS_PUBLICATION_MANDATE` | bool | open access to publications is required: true for all Horizon programmes (incl. ERA-NET and EIT) |
| `HAS_DATA_MANDATE` | bool | open access to research data is required (OpenAIRE `openAccessMandateForDataset`: H2020 Open Research Data Pilot / Art. 29.3, all Horizon Europe grants). Null if the grant is not matched or OpenAIRE has no flags for it |

## grant_datasets
One record per grant of the projects that have articles.

| Field | Type | |
|---|---|---|
| `HORIZON_ID`, `OPENAIRE_ID` | str | |
| `N_DATASETS` | int | datasets that OpenAIRE links to the grant |
| `DATASETS` | list | first 100: `TITLE`, `DATE`, `PIDS` (`scheme:value`), `URL`, `HOST`, `ACCESS_RIGHT` (OpenAIRE value) |

## open_data_candidates

| Field | Type | |
|---|---|---|
| `GUID`, `DOI` | str | |
| `EUROPEPMC` | object | `PMID`, `PMCID`, `IS_OPEN_ACCESS`, `IS_AUTHOR_MANUSCRIPT`, `HAS_SUPPLEMENTARY_FILES`, `LICENSE` (null if Europe PMC doesn't have the article), `ACCESSION_NUMBERS`: database accession numbers that Europe PMC text mining found in the full text: `ID`, `DATABASE`, `SECTION` |
| `SCHOLEXPLORER` | object | `LINKS`: dataset and software links: `RELATION`, `TYPE`, `TITLE`, `IDENTIFIERS`, `PUBLISHERS`, `LINK_PROVIDERS` (ScholeXplorer values) |
| `DATACITE` | object | `RECORDS`: DataCite records that relate to the article as a supplement, source etc.: `DOI`, `TITLE`, `TYPE`, `PUBLISHER`, `YEAR`, `RELATIONS` (DataCite relation types), `URL` |

## fulltext_index
Same records as the sidecar files `data/fulltext/<GUID>.json`. The full text is `data/fulltext/<GUID>.<pdf|xml|html|docx>` with a plain text copy `<GUID>.txt`. Files saved during the open data check have a suffix, e.g. `<GUID>.supplement.pdf`.

| Field | Type | |
|---|---|---|
| `GUID`, `DOI` | str | |
| `FILE`, `TEXT_FILE` | str | full text file and its text copy; null if no full text |
| `N_CHARACTERS` | int | length of the text |
| `SOURCE`, `URL`, `VERSION`, `HOST_TYPE` | str | of the successful attempt |
| `RETRIEVED_AT` | str | |
| `ATTEMPTS` | list | full text sources tried, best first: `SOURCE` (code), `URL`, `VERSION` (code, null if unknown), `HOST_TYPE` (code), `RESULT` (code), `RESULT_DETAIL` (HTTP status, content type or error name) |

## open_data_queue
Everything known automatically about an article, in check order: the 20 articles of the Jan 2025 random sample first, then the rest by GUID. ETIS GUIDs are random, so any number of checked articles is a random sample.

| Field | Type | |
|---|---|---|
| `QUEUE_POSITION` | int | |
| `IS_PILOT` | bool | in the Jan 2025 random sample |
| `GUID`, `TITLE`, `PERIODICAL`, `DOI`, `HAS_ESTONIAN_AUTHOR`, `AUTHORS`, `INSTITUTIONS` | | from `articles` |
| `ETIS_PAGE_URL` | str | the article's page in the ETIS portal |
| `PROJECTS` | list | the article's ETIS projects: `GUID`, `TITLE`, `PROGRAMME_CODES`, `FRAMEWORK_PROGRAMME`, `HORIZON_ID`, `ACRONYM`, `HAS_PUBLICATION_MANDATE`, `HAS_DATA_MANDATE` (from `projects`), `IS_GRANT_LINKED` (OpenAIRE or OpenAlex links the article to the project's grant; null if the project has no grant or neither source has the article), `N_GRANT_DATASETS` (from `grant_datasets`) |
| `OPEN_ACCESS` | object | `AUTOMATIC_VERDICT` (code: status by ETIS, OpenAlex and the Jan 2025 manual check; null if the full text check has to settle it), `CHECK_NEEDED_REASON` (code), `ETIS` (`IS_OPEN_ACCESS`, `OPEN_ACCESS_TYPE`, `LICENSE`, `URL`), `OPENALEX` (`IS_OPEN_ACCESS`, `OPEN_ACCESS_TYPE`, `HAS_OPEN_PEER_REVIEWED_VERSION`, `OPEN_LOCATIONS`: `VERSION`, `URL`, `HOST`, `HOST_TYPE`, `LICENSE`), `OPENAIRE` (`OPEN_INSTANCES`: open copies that OpenAlex doesn't list: `URL`, `HOST`, `TYPE`), `MANUAL_CHECK` (`IS_OPEN_ACCESS`) |
| `CANDIDATES` | object | `EUROPEPMC`, `SCHOLEXPLORER`, `DATACITE` from `open_data_candidates` |
| `FULLTEXT` | object | from `fulltext_index` |

## open_data_assessments
One JSON object per line, written by Claude with the `check-open-data` skill (`.claude/skills/check-open-data/SKILL.md` explains the labels). Records are only appended; the latest record of a GUID wins.

| Field | Type | |
|---|---|---|
| `GUID` | str | |
| `ASSESSED_AT` | str | |
| `ASSESSOR` | str | model ID |
| `TEXT_FILES` | list[str] | cached text files that the quotes come from (`./data/fulltext/<GUID>*.txt`) |
| `FULLTEXT_VERSION` | str | version code of the full text that was read; null if none |
| `OPEN_ACCESS` | object | `VERDICT` (code), `VERSION` (version code of the free copy), `URL` (of the free copy), `EVIDENCE` |
| `DATA_LABEL` | str | code |
| `DATA_COVERAGE`, `DATA_LEVEL` | str | codes; null for labels that aren't open or restricted data |
| `DATA_LINKS` | list | links that were checked: `URL`, `DESCRIPTION`, `IS_OWN_DATA` (the article's own data), `IS_OPENLY_DOWNLOADABLE` |
| `QUOTES` | list[str] | verbatim passages from the text files |
| `CODE_AVAILABILITY` | str | code |
| `IS_GRANT_ACKNOWLEDGED` | bool | the article names the ETIS project's grant (Horizon ID, acronym or name). Null without a full text |
| `GRANT_DATASETS_NOTE` | str | relevant OpenAIRE datasets of the grant that don't decide the label |
| `CONFIDENCE` | str | code |
| `RATIONALE` | str | |
| `SIDE_NOTES` | list[str] | things the user should know (metadata errors, tangents) |

## article_analysis
One record per article, for the analysis by article, project, author or institution. Article-level mandates and grant links are true if they hold for any of the article's projects.

| Field | Type | |
|---|---|---|
| `GUID`, `TITLE`, `PERIODICAL`, `DOI`, `AUTHORS`, `INSTITUTIONS`, `HAS_ESTONIAN_AUTHOR` | | |
| `PROJECTS` | list | as in the queue, without `N_GRANT_DATASETS` |
| `HAS_PUBLICATION_MANDATE`, `HAS_DATA_MANDATE`, `IS_GRANT_LINKED` | bool | any of the projects |
| `IS_GRANT_ACKNOWLEDGED` | bool | from the assessment |
| `IS_OPEN_ACCESS` | bool | final status; null if pending a full text check |
| `OPEN_ACCESS_SETTLED_BY` | str | code |
| `OPEN_ACCESS_AUTOMATIC_VERDICT` | str | code (from the queue) |
| `OPEN_ACCESS_FULLTEXT_VERDICT` | str | code (from the assessment); null if not assessed |
| `OPEN_ACCESS_CHECK_NEEDED_REASON` | str | code |
| `DATA_LABEL`, `DATA_COVERAGE`, `DATA_LEVEL`, `CODE_AVAILABILITY`, `CONFIDENCE` | str | from the assessment |
| `IS_OPEN_DATA` | bool | data label is `repository`, `supplement` or `public_source`; null for `no_data`, `no_fulltext` or not assessed |

## Codes

**`FRAMEWORK_PROGRAMME`** (projects)
- `h2020` - Horizon 2020 (OpenAIRE grant ID prefix `corda__h2020::`, ETIS programmes 136, 137, 442, 443)
- `horizon_europe` - Horizon Europe (`corda_____he::`, ETIS programmes 450, 451)

**`MATCHED_BY`** (projects) - how the project's grant was found, in this order:
- `search_api` - OpenAIRE search API has a single EC grant with the ETIS financier project number, acronym or title
- `article_grant_links` - the project's articles link to the grant (the grant with the project's title, otherwise the most linked one)
- `exact_title` - fuzzy title match score 100 and the next best at most 85
- `approximate_title` - fuzzy title match score at least 85 and the next best below 70

**`FOUND_BY`** (raw openalex_works, articles `OPENALEX`)
- `doi` - DOI lookup
- `title_search` - the single work with the same title and publication year (±1)

**`AUTOMATIC_VERDICT`**, **`OPEN_ACCESS_AUTOMATIC_VERDICT`**
- `open` - the published version or the accepted manuscript is free to read
- `not_open`

**`CHECK_NEEDED_REASON`** (queue), **`OPEN_ACCESS_CHECK_NEEDED_REASON`** - why the full text check has to settle open access:
- `etis_openalex_disagree` - ETIS and OpenAlex (open published version or accepted manuscript) disagree
- `manual_check_any_version` - the Jan 2025 manual check counted any free version, and OpenAlex has no open published version or accepted manuscript
- `openaire_copy_not_in_openalex` - not open by ETIS and OpenAlex, but OpenAIRE has an open copy (not a preprint) that OpenAlex doesn't list

**`OPEN_ACCESS_SETTLED_BY`** (article_analysis)
- `fulltext_check` - open data assessment verdict (`open` or `not_open`)
- `manual_check` - Jan 2025 manual check
- `etis_and_openalex` - ETIS and OpenAlex agree

**Versions** (`VERSION` and `FULLTEXT_VERSION` outside source blocks)
- `published_version` - version of record
- `accepted_version` - peer-reviewed author manuscript
- `submitted_version` - preprint
- `unknown` - (assessments only) a full text whose version can't be told

**`HOST_TYPE`** (fulltext_index): OpenAlex source type in snake case (`journal`, `repository`, `conference`, `book_series`, ...). PMC and Zenodo are `repository`.

**Full text `SOURCE`** (fulltext_index), in the order they are tried:
- `pmc` - PMC full text XML (NCBI E-utilities)
- `openalex_pdf` - PDF of an open OpenAlex location (published versions and accepted manuscripts first, preprints last)
- `openalex_html` - journal page of an open OpenAlex location
- `zenodo` - article file of a Zenodo record that OpenAIRE lists as an open copy
- `openaire_pdf` - other PDF link that OpenAIRE lists as an open copy
- `openalex_content` - OpenAlex cached copy (needs an API key, $0.01 each)

**Full text attempt `RESULT`** (fulltext_index)
- `ok`
- `http_error` - detail: HTTP status code
- `exception` - detail: error name (e.g. timeout)
- `wrong_content_type` - not a PDF, XML, Word file or HTML page. Detail: content type
- `text_too_short` - text shorter than a full text (5000 characters, HTML 20000), e.g. a scanned PDF or an abstract page
- `no_fulltext_xml` - PMC XML without a body (the publisher doesn't allow full text XML)
- `no_fulltext_file` - Zenodo record without an open PDF or Word file
- `title_not_found` - Word file without the article title near its beginning (e.g. a cover letter)

**Open access `VERDICT`** (assessments), **`OPEN_ACCESS_FULLTEXT_VERDICT`**
- `open` - the published version or the accepted manuscript is free to read
- `not_open` - only a preprint or nothing is free
- `unclear` - the copies couldn't be checked

**`DATA_LABEL`** (assessments)
- `repository` - underlying data in a public repository or database, openly downloadable. Open data
- `supplement` - supplementary files with actual data, openly downloadable. Open data
- `public_source` - only existing data from a cited public source that anyone can download. Open data
- `restricted` - controlled access (application, data use agreement, reviewed registration)
- `on_request` - from the authors on request
- `in_article` - the article says all data are in the article, no data files
- `not_available` - data not shared, or no statement and no data found
- `no_data` - no underlying research data (review, essay, theory). Left out of the open data rates
- `no_fulltext` - full text not accessible and no data record that verifiably belongs to the article. Left out of the open data rates

**`DATA_COVERAGE`**: `full` (data behind all main results), `partial`

**`DATA_LEVEL`**: `raw` (primary measurements or records), `processed` (aggregated or derived data)

**`CODE_AVAILABILITY`**: `repository`, `on_request`, `not_shared` (mentioned but not shared), `not_mentioned`, `not_applicable` (no custom code)

**`CONFIDENCE`**: `high` (explicit statement or verified data record), `medium` (some inference), `low` (key evidence missing)
