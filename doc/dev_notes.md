# 2026-10-03
`get_fulltext` also takes Word files (.docx) when a Zenodo record has no PDF, and when an OpenAIRE PDF link gives a Word file. A Word file counts as the article only if the article title is near its beginning (Word files can be other documents, e.g. a cover letter). `fulltext_conversion` converts .docx files with the standard library (zipfile, ElementTree): body text, footnotes and endnotes, link targets in brackets, heading styles marked with #. Field codes (e.g. Zotero citations) are left out. Two articles had only a Word file on Zenodo (6f0deeb0, 143fd56f).

`get_fulltext` also gets full texts from the open copies of the articles in OpenAIRE research products (instances): Zenodo records (file list from Zenodo API, the article PDF of the record) and links to PDF files in other repositories. OpenAIRE knows many repository copies that OpenAlex doesn't, e.g. accepted manuscripts that Horizon projects uploaded to Zenodo. The version of these copies is unknown, so they go after the published versions and author manuscripts from OpenAlex, but before the paid OpenAlex cached copies. Zenodo records come before other PDF links. Preprints (OpenAIRE instance type Preprint or a preprint server, e.g. bioRxiv, MPRA) are tried last. 79 of the 422 articles without a full text had an open Zenodo copy in OpenAIRE, 32 more had other PDF links. The open data queue lists the open copies in OpenAIRE that OpenAlex doesn't have (`OPENAIRE_OPEN_INSTANCES`), so that the open access check can use them.

Fixed database names of Europe PMC accession numbers: DOI tags (`identifiers.org/doi:10.1613/...`) got names like `doi:10.1613` and tags with a database page URI got `https:`. DataCite related identifier queries also match the `https://doi.org/<DOI>` form (missed e.g. the DRUM dataset of d8ca08a8 in the pilot).

Rerun of the DataCite step and the summary of `get_open_data_candidates`, `get_fulltext` (with the OpenAlex API key and the OpenAIRE copies) and `make_open_data_queue`: DataCite records for 59 articles (58 before, records changed for 10). Full texts for 592 of 842 articles (420 before): 79 from Zenodo (2 of them Word files), 11 from other PDF links in OpenAIRE, 82 OpenAlex cached copies ($0.82). 250 articles still have no full text.

Secrets are now files in the `secrets/` folder (not committed), one file per secret, file name is the secret name (like secrets mounted in Kubernetes). `get_data` and `get_fulltext` read the OpenAlex API key from `secrets/openalex_api_key` instead of the `OPENALEX_API_KEY` environment variable.

Started open data checks (step 3). Claude Code checks the articles one by one with the `check-open-data` skill (`.claude/skills/check-open-data/SKILL.md`) and appends one record per article to `data/assessments/open_data_assessments.jsonl`. The full text check also settles open access of the articles where it's unclear.

Open data = the data needed to validate the article's results can be freely downloaded (H2020 Art. 29.3 / Horizon Europe bar). Labels: repository, supplement, public_source (count as open data), restricted, on_request, in_article, not_available, no_data, no_fulltext (left out of the rates). Records also say whether the open data are full or partial, raw or processed. Datasets of the Horizon project count only if the article itself links to them (AHEAD case). All 842 articles will be checked eventually.

Added scripts:
- `get_open_data_candidates` - candidate data links by DOI: ScholeXplorer dataset and software links, DataCite records that are supplements to the article, Europe PMC records (PMC IDs, text-mined accession numbers), OpenAIRE datasets of the Horizon projects.
- `get_fulltext` - full texts to `data/fulltext/` (not committed): PMC XML via NCBI E-utilities, open PDFs and journal pages of published versions and author manuscripts from OpenAlex locations, OpenAlex cached copies (needs an OpenAlex API key), open preprint PDFs. PDFs are converted with pdftotext (`fulltext_conversion`). Uses a browser user agent - many publishers (e.g. MDPI) refuse open access PDFs to scripts.
- `make_open_data_queue` - everything that the check needs per article. The 20 articles of the Jan 2025 random sample come first, the rest are in a fixed random order, so that any number of checked articles is a random sample.
- `next_open_data_batch` - prints the next articles to check. `validate_open_data_assessments` - checks that quotes are in the cached full texts and that links work.
- `analyse_data` uses the open access verdicts of the full text check and gives open data rates with 95% confidence intervals by data mandate group.

Open access check list: 66 articles where ETIS and OpenAlex disagree and 42 articles with a Jan 2025 manual "free to read" verdict but no open published version or author manuscript in OpenAlex (19 only preprint or unknown version, 17 not in OpenAlex, 6 closed in OpenAlex).

272 of 842 articles have candidate data links (ScholeXplorer 172, DataCite 58). Europe PMC has 297 of the articles, 207 with a PMC ID. 114 of 179 Horizon projects with articles have datasets in OpenAIRE. Full texts for 420 articles (359 published version or author manuscript). Many publishers block scripts (403, captchas, JavaScript challenges: Elsevier, Wiley, T&F, ACS, Springer, A&A, IEEE).

DataCite answers 429 after ~500 requests in 5 minutes without identification. Added retries with waits.

Pilot of the first 10 articles: 2 repository, 1 supplement, 1 public_source, 1 restricted, 1 on_request, 3 not_available, 1 no_fulltext. Same results as the Jan 2025 manual checks for 5bd15d8a and 81f611f3. 9087611f is now public_source (archival XMM-Newton and Chandra data); in Jan 2025 it counted as available because of AHEAD project data. Found an accepted manuscript of 371f55d4 in Zenodo through OpenAIRE that OpenAlex doesn't know.

Open Access Button API was shut down on 2025-11-18. Replaced it with OpenAlex API in `get_data`. Articles are looked up by DOI (free). Articles without a DOI, or with a DOI that OpenAlex doesn't know, are searched by title. A title search result is accepted only if it's the single work with the same title and publication year (±1 year). Title searches cost $0.001 against a daily budget of $0.10 without an API key or $1 with a free key (`OPENALEX_API_KEY` environment variable).

Open access summary and the ambiguous open access check now compare ETIS with OpenAlex instead of Open Access Button. `analyse_data` reads the latest open access data file instead of a fixed path.

Fixed DOI cleaning for ETIS DOIs with a double slash (http://doi.org//10...).

OpenAIRE graph API project records have the data mandate flag `openAccessMandateForDataset` (same as `ecarticle29_3` in the search API). Removed the `get_open_access_opt_outs` stub that read project.csv. The graph projects download stays on API v1: v3 has the same IDs and flags, but the records are ~20x bigger because of participant links.

Added `get_openaire_research_products`: OpenAIRE graph API v3 research products of the scientific articles by DOI. Only v3 research products have links to the projects that funded them.

`get_etis_project_horizon_ids` now matches ETIS projects to Horizon IDs in this order: OpenAire search API (ETIS financier project number, acronym, title), publication project links, fuzzy title matching. Publication project links come from OpenAIRE research products and OpenAlex awards. Only Horizon projects with an Estonian partner and from the same framework programme as the ETIS project count. The ETIS project gets the linked project with the same title, otherwise the one that most of its articles link to. Title check is needed because articles can link more often to another grant of the same group (e.g. ADOPT BBMRI-ERIC articles link more often to ePerMed). The script saves all ETIS Horizon projects with their Horizon ID, match info and OpenAIRE data mandate flags to results.

OpenAire search API requests are now limited to European Commission projects. Before, e.g. EIT project ADMA3 financier number 22015 matched a Dutch NWO project and ERA-NET projects matched national funders' projects. Fuzzy title matching now compares only with Horizon projects from the same framework programme as the ETIS project. Before, it matched e.g. French ANR projects of ERA-NET calls.

EIT (programme 136) grants are not OpenAIRE projects, so EIT projects are not matched by publication project links or fuzzy titles - their articles link to other grants of the same group.

Decisions: keep using only finished projects. An article's data mandate comes from its ETIS project's own Horizon grant; other grants acknowledged in the article don't count.

ETIS now has 512 finished Horizon projects with 842 scientific articles (592 in Jan 2025).

Open access now follows the Horizon open access mandate: an article is open if its published version or peer-reviewed author manuscript is free to read. Open submitted versions (preprints) and open copies of unknown version in OpenAlex don't count. Open access summary has new fields `OPENALEX_OPEN_VERSIONS` and `OPENALEX_HAS_OPEN_PEER_REVIEWED_VERSION`. The ambiguous open access check and `analyse_data` use the latter. Ambiguous articles will be settled when their full text is checked.

Refresh run (ETIS pull of 2026-10-02, OpenAlex step onwards on 2026-10-03): OpenAlex has data for 809 of the 842 articles (14 by title search, 47 searches). 650 of 842 articles (77%) are open to read (684, 81% if preprints count). 66 articles have ambiguous open access status: 34 ETIS open, but OpenAlex has only an open preprint or copy of unknown version; 15 ETIS closed, but OpenAlex has an open published version or author manuscript; 9 ETIS open, OpenAlex closed; 8 ETIS open, not in OpenAlex. On the 582 articles that were also in the Jan 2025 run, counting any version: 474 open to read now, 480 with Open Access Button (9 open -> closed, 3 closed -> open).

Both ETIS and OpenAlex make errors. OpenAlex marks 5 Materials Science Forum articles CC BY because of the site footer, but the articles are for sale. OpenAlex says closed for Science 10.1126/science.abd3072 (CC BY in Crossref, full text in Europe PMC) and Halduskultuur 10.32994/hk.v21i1.253 (free PDF). ETIS says gold CC BY for Nature Medicine 10.1038/s41591-025-03543-8, but Crossref has a Springer Nature licence and the article page has a price.

Jan 2025 manual checks used "free to read". 19 manually checked open articles have only an open preprint or copy of unknown version in OpenAlex. These need to be checked again with the full text.

418 of the 512 ETIS projects have a Horizon ID (368 search API, 26 publication project links, 14 exact title, 10 approximate title), 404 of them with data mandate flags. 14 matched projects have no flags because OpenAIRE lists no Estonian partner for them. Only CORBEL (654248) of these has articles (5). 199 projects have articles: 186 matched, 185 with flags.

Articles open to read by their projects' data mandate: H2020 with mandate 322 of 408 (79%), H2020 without mandate 247 of 325 (76%), Horizon Europe 53 of 67 (79%), mixed 17 of 27, unknown 11 of 15.

# 2025-04-22
Further work on fuzzy title matching between ETIS and OpenAire projects. It seems that many unmatched projects are from Horizon EIT programs. https://etag.ee/en/funding/partnership-funding/horizon-2020-eit-grant/. Maybe just smaller fundings from big umbrella projects.

# 2025-04-21
Started implementing fuzzy title matching.

# 2025-04-20
Added logic to get Horizon ID matches by OpenAire search API results. Next: match with OpenAire graph API records of EE projects by fuzzy matching titles.

# 2025-04-10
No answer from OpenAIRE support. Sent a reminder.

Problem description:
It seems that the OpenAIRE [search API](https://graph.openaire.eu/docs/apis/search-api/projects) project [result](https://www.openaire.eu/schema/1.0/doc/oaf-project-1_0_xsd.html#project) includes a parameter `ecarticle29_3` that has info about whether the project opted out of the open data pilot. Unfortunately the search API can't find projects by the parameters given in ETIS.

The OpenAIRE [graph API](https://graph.openaire.eu/docs/apis/graph-api/) has better search capabilities, but there is no good way to get from one result to the other. (Search API doesn't take graph API ID.)

# 2025-02-25
Apparently OpenAIRE API returns information about whether the project participated in the open data pilot program (and should have raw data available). Unfortunately it's hard to link it to ETIS info due to the undocumented problems in OpenAIRE API mentioned below. Still no answer from support.

# 2025-02-15
Improved OpenAIRE request data structure.

Tested getting Horizon project code by project title from OpenAIRE API. Ran into various undocumented problems. Sent a help request to the OpenAIRE graph helpdesk.

# 2025-02-14
It seems that a lot of Horizon projects in ETIS don't have Horizon project IDs. That means there is no way to join data from openAIRE.

Made a POC script to get Horizon ID from openAIRE API by project acronym or title. It also double-checks the Horizon project ID if provided. This will be included in the `get_data` script in due course.

Acronyms work well, but searching by title needs to be improved.

ETIS project endpoint some times returns projects with programme codes that are not in the request parameters. Sent an inquiry to ETIS helpdesk.

# 2025-01-19
Analysed one of the random publications.

Sent inquiry to Cordis helpdesk about the of information in the project pages.

# 2025-01-18
Selected random publication GUIDs to check for data manually.

# 2025-01-13
ETIS support said the wrong publication GUIDs under projects should be fixed now.

# 2025-01-12
"Free to read" is a great term for what I've been calling "available".

Added functionality to deduplicate publications.

TODO: should drop articles with status "Fourthcoming". Not published yet - can't determine open access status.

TODO: deduplicate publcations. It seems that some times same publication is mentioned in several different projects.

Added check for ambiguous publication open access status (when ETIS and Open Access Button disagree).

Added functionality to manually define publication open availability status.

Restructured project directories.

Created the data structure for publication open access info.

Refactored `get_data` to pull publication open access url from Open Access Button API and save an intermediate raw json with the data.

# 2025-01-11
Refactored `get_data` to pull publication data from ETIS and save an intermediate raw json with the data.

Refactored `get_data` to pull project data from ETIS and save an intermediate raw json with the data.

---

Some publication 1c2c5e88-e433-4aa1-b7d1-14d25d48850d:
Not visible in project API response: https://www.etis.ee:7443/api/project/getitems?Format=json&Take=1&Guid=b1fac2a5-d883-48ed-b95e-1ab1b3381a89
Visible in project display page: https://www.etis.ee/Portal/Projects/Display/b1fac2a5-d883-48ed-b95e-1ab1b3381a89
Has UUID 3380759f-3947-4fe3-ba2b-63536ce9a737 in project page - seems to be the same ETIS API problem that I reported before.

---

In ETIS project info, it seems that the roof project total funding is total funding for all organizations participating in the project. The funding period total is the funding to the Estonian organization.

# 2025-01-08
Reported false negatives to OpenAccessButton

# 2024-12-22
Changed data save format to JSON.

Created machine-readable file for manually checked open access publications.

Added summary calculation code.

# 2024-12-20
ETIS API fix failed. New estimated time unknown.

# 2024-12-16
ETIS API wrong publication GUIDs will be fixed on 20th of Dec.

Started dev log.

Started git repo.

Investigated OpenAccessButton bad hits.

# 2024-12-15
Pulled project publications.

Developed OpenAccessButton API class.

Checked publications where ETIS open access status doesn't match with what OpenAccessButton returns.

Found ~40 project publication GUIDs with no actual publication. Reported to ETIS API team.

Number of citations for open vs not open articles #idea.

How many articles in predatory journals? #idea.

# 2024-12-14
ETIS project codes & pull projects data.

Use https://github.com/martroben/citations_analyser as starter point.

Idea conception.
