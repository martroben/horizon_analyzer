# 2026-10-03
Articles with the same DOI are one article. ETIS had 3 records of the same article (10.2478/fsmu-2023-0006: d4f49870, e1e69ca8, 213e0586, created in the same second, all under ACTRIS IMP), so the analysis counted it 3 times. `get_data` merges ETIS records with the same DOI into the first record (ETIS order): projects, authors and institutions of all records, an Estonian author if any record has one, the Jan 2025 manual check of any record. `ETIS.DUPLICATE_GUIDS` has the other records. Articles without a DOI are not merged (no two have the same title). `get_etis_project_horizon_ids` counts article grant links over `articles` instead of the ETIS records, so a duplicated article doesn't count several times.
- Reran the `get_data` summary, `get_etis_project_horizon_ids`, `make_open_data_queue`, `analyse_data` and the `get_manual_fulltexts` fetch list (no new downloads): 840 articles (842 before), all other records the same. The grant link counts of ACTRIS IMP changed (871115: 12 -> 10 links), its grant didn't. The pilot articles keep their queue positions. Open access: 606 of 716 articles with known status (608 of 718 before), 85%.

Missing full texts, step 2 of 3: full texts saved by hand. `get_manual_fulltexts` lists the articles without a full text with links to try (`data/fulltext/inbox/fetch_list.html`, by publisher) and takes in the files that the user saves into `data/fulltext/inbox/`. The folder is the source: `open` (free without login on the publisher site or in a repository - evidence of open access), `other` (other free copies, e.g. ResearchGate, author's website - not open access, like in Unpaywall), `library` (library access - never open access). Articles looked for without result go into `not_found.txt` (open: no free published version or accepted manuscript - evidence for not open; library: no access). They are attempts in the full text info file, and `get_fulltext` keeps them when it tries the article again.
- Open round: 109 articles that ETIS, OpenAlex, the Jan 2025 manual check or an OpenAIRE copy say are free (Elsevier 39, T&F 11, no DOI 11). Library round: 91 articles without a sign of a free copy (Elsevier 28, T&F 11, Wiley 9) and the ones that weren't found in the open round. The 65 articles whose full text is an OpenAlex `submittedVersion` copy are not in the lists (22 are arXiv preprints, many others are published versions in repositories).
- Files are matched to articles by the DOI and title in the first 2000 characters, then in the first 10000 (texts cite other articles further on), or by the GUID prefix at the start of the file name. Tested on the 642 cached full texts: 630 matched correctly, none wrongly, 12 not matched (2 pairs of articles with nearly the same title, an article with 3 ETIS records, 7 texts without the DOI or the ETIS title near the beginning). Firefox (snap) doesn't save the download URL in file attributes, so manual copies have no URL.
- The National Library proxy `ezp.nlib.ee` that the rara.ee database page links to doesn't resolve (NXDOMAIN).

Missing full texts, step 1 of 3 (automatic sources; then a manual round for open copies and a library round for paywalled articles). Of the 250 articles without a full text, 69 had an ETIS link to a site other than a publisher, 82 had an open copy only on publisher sites that block scripts (Elsevier 40, T&F 10, MDPI 7), 15 only a preprint and 84 no open copy.
- ETIS publications have a full text location (`FullTextLocation`, 656 of 842 articles) that wasn't used. `articles` has it as `ETIS.FULLTEXT_URL`. ETIS URLs are typed in by hand: doubled schemes (`http://https://...`), no scheme, or only `http://` (22 publication URLs) - `get_data` cleans them (`ETIS.URL` too).
- `get_fulltext` tries the ETIS links (full text location, then publication URL) after the OpenAIRE copies and before the OpenAlex cached copy (ETIS links to preprint servers last). A file from an ETIS link counts only if it has the article title somewhere in the text: ETIS links can point to other documents, and some are whole journal issues with the article inside (2 of the new texts).
- Pages: most journal and repository pages name their PDF in a `citation_pdf_url` meta tag (Highwire tags for Google Scholar). If a page isn't a full text, `get_fulltext` downloads that PDF. OpenAIRE open copies that aren't PDF links (repository landing pages, journal pages) are now tried this way (`openaire_html`), and so are OpenAlex repository landing pages without a PDF link. Only journal pages and ETIS pages can be HTML full texts - repository landing pages, PubMed, Scopus or DOAJ pages can be longer than 20000 characters without being the article. A PDF link that gives a page is also followed to its `citation_pdf_url` (before: `wrong_content_type`).
- The same link in several sources is tried once (http and https, dx.doi.org and doi.org).
- Rerun of `get_fulltext` (only the 250 without a full text), `make_open_data_queue`, `analyse_data`: full texts for 642 of 842 articles (+50: 27 ETIS links, 17 OpenAIRE pages, 6 journal pages via `citation_pdf_url`). All 50 have the article title; 4 are preprints (arXiv, Research Square). The existing assessments are unchanged (validator 0 errors). 200 articles still have no full text: 78 with an open copy only on publisher sites (Elsevier 33, T&F 11), 16 only a preprint, 13 open according to ETIS without a working link (11 without DOI), 93 without an open copy (Elsevier 29, T&F 12, Wiley 9).
- Dry run before: MDPI pages and `/pdf` links sometimes give an empty page and sometimes the PDF; scientific.net PDF links 403; DSpace 7 handle pages can have `citation_pdf_url` on `localhost`; Springer pages are JavaScript challenges.

Library access for paywalled articles (researched, not tested): TalTech licensed full texts open only in the TalTech network; remote access (VPN, Uni-ID) only for TalTech members. Outside users can register and use library computers. The National Library of Estonia gives registered readers (free, ID card / Mobile-ID / Smart-ID) remote access to Taylor & Francis Journals, Oxford Academic and Emerald through its proxy (`ezp.nlib.ee`). Elsevier API with a free key (tested on 5 open and 2 closed Elsevier articles without a full text): ScienceDirect article retrieval answers 403 ("Requestor configuration settings insufficient") for all of them, also for the open access journal SoftwareX, and ScienceDirect search 401; Scopus search, Scopus abstracts and serial titles work. Outside a subscribing institution's network ScienceDirect APIs are a subscriber feature (Elsevier support), although the key settings page lists open access articles for default keys. So the 33 open Elsevier articles go to the manual round. Elsevier's text mining licence is for researchers of subscribing institutions. Elsevier and Wiley allow licensed content only in AI tools that don't train on or keep it. Copies from library access never count as open access.

Documentation review: decisions and findings are in this log. README, `doc/data_schema.md`, the `check-open-data` skill and code comments say what things are, without the reasons. Shorter README (setup, secrets and costs together, script list without details), with a short description of the project logic at the beginning. Removed reasons from the schema (queue order, wrong ETIS programme codes), the skill (dossier contents, check reason codes that are in the schema) and code comments (accountability for articles, mandate definitions, OpenAIRE copies, queue order). The notes of `doc/manual_operations_notes.md` are now in the 2024-12-16 entry.

PDFs are converted with pypdfium2 (PDFium, Apache-2.0/BSD-3, the wheel has the library) instead of pdftotext, so no system package (poppler-utils, sudo) is needed. Compared on the 308 cached PDFs: all converted, 15 s (pdftotext 23 s), as few glued words as pdftotext (39 vs 45). PDFium marks hyphens at line breaks with \x02 and joins the lines - the converter drops the mark and joins the word, like pdftotext. The texts differ from pdftotext mostly in the order of tables, formulas and running heads. PyMuPDF was as good, but it's AGPL. pypdf was ~9x slower with 4x more glued words, pdfminer.six ~9x slower. Cached texts were not converted again, so the quotes of the existing assessments still match (with pypdfium2 texts, 1 of the 13 quotes from PDFs would match only approximately: "1 H NMR" vs "1H NMR").

Review step 3: consistent data schema. Data files, fields and codes are described in `doc/data_schema.md`. Conventions: boolean fields start with `IS_` or `HAS_`, lists have plural names, counts start with `N_`, missing values are null (not ""), categorical values are snake case codes. Project = ETIS project, grant = Horizon grant. Top-level fields are the values that the analysis uses; what a single source says is in a block named after the source (`ETIS`, `OPENALEX`, `OPENAIRE`, `EUROPEPMC`, `SCHOLEXPLORER`, `DATACITE`, `MANUAL_CHECK`). Before, `IS_OPEN_ACCESS` was the ETIS status in the article data and the final status in the analysis data.
- Results: `open_access_data` -> `articles`, `etis_project_horizon_ids` -> `projects`, `project_datasets` -> `grant_datasets`, analysis `articles` -> `article_analysis`. `open_access_data_ambiguous` is dropped - the queue's `CHECK_NEEDED_REASON` replaces it. Raw files have the source as prefix: `etis_publications`, `etis_publications_without_data`, `etis_articles`, `openalex_works`, `openaire_projects`, `openaire_project_searches`, `datacite_records`.
- `articles`: one `DOI` (ETIS DOI, else the DOI that OpenAlex title search found) instead of `DOI or OPENALEX_DOI` in 4 scripts. `OPENALEX.FOUND_BY` (doi, title_search). Dropped `IS_PUBLIC_FILE` (false for all).
- `projects`: has `ACRONYM`, `FRAMEWORK_PROGRAMME`, `HAS_PUBLICATION_MANDATE` (true for all Horizon programmes, was set in the queue) and `HAS_DATA_MANDATE`. `FRAMEWORK_PROGRAMME` is the framework programme of the grant, or of the ETIS programme codes if there is no grant (before: from the OpenAIRE ID, null for 14 projects with articles). ETIS programme codes are wrong for 4 matched projects: 3 Horizon Europe grants under 442 (e.g. NOVASOIL 101091268), 1 H2020 grant under 450 (BoostEuroTeQ). `MATCHED_BY` codes.
- `open_data_queue`: the automatic open access verdict (`OPEN_ACCESS.AUTOMATIC_VERDICT`: open, not_open, null if the full text check has to settle it) is computed only here, the analysis used to compute it again. `CHECK_NEEDED_REASON` codes. Dropped `DATA_MANDATE_GROUP` (the analysis groups by `HAS_DATA_MANDATE`). Has the authors and institutions, so `analyse_data` reads only the queue and the assessments. Grant datasets are joined by `HORIZON_ID` everywhere (the queue used the OpenAIRE ID).
- Full texts: source codes `openalex_pdf`, `openalex_html` (were `oa_pdf`, `oa_html`), version codes `published_version`, `accepted_version`, `submitted_version`, attempt `RESULT` code with `RESULT_DETAIL` (HTTP status, content type, error). Failed PMC attempts have the PMC URL instead of the PMC ID.
- Queue order: pilot articles first, then the rest by GUID (was a shuffle with a fixed seed). ETIS GUIDs are random (all 842 are UUID version 4, GUID order doesn't correlate with publication year or ETIS order), so the GUID order is a random order. Unlike the shuffle, it stays the same when articles are added or removed: new articles get a random place, so the checked articles stay the first ones of a random order of the current articles after a data refresh. Only the pilot articles had been checked, so nothing changes for them.
- Assessments: `TEXT_FILES` (was `SOURCES`), `CODE_AVAILABILITY` (was `CODE`), `IS_GRANT_ACKNOWLEDGED`, `GRANT_DATASETS_NOTE`, `IS_OWN_DATA`, `IS_OPENLY_DOWNLOADABLE`, `SIDE_NOTES` is a list. `article_analysis` also has `DATA_LEVEL`, `CODE_AVAILABILITY` and `CONFIDENCE`.

The data were converted, not downloaded again: raw files renamed, OpenAlex and OpenAIRE search wrappers, full text sidecars and the 10 assessments rewritten with a one-off script. Results rebuilt from the converted data. Checked: the old code and the new code give the same results on the same data (all result files compared field by field after mapping the old fields to the new ones, same full text attempts for all 842 articles, same dossier texts, validator 0 errors). API code tested live on 8 articles (all full text sources, OpenAlex, OpenAIRE search, research products and datasets, ScholeXplorer, DataCite, Europe PMC). Removed the superseded 2026 results (they are in git history). The Jan 2025 `open_access_data` file stays.

OpenAlex now has two works with the title of c5e4bbb0 (W2908037306 and W7217823533, same year), so the next OpenAlex run won't find it by title search.

Review step 2: code cleanup without changes in results. Ran the offline steps (`get_data` from the publication info onwards, `get_etis_project_horizon_ids`, summary of `get_open_data_candidates`, full text index, `make_open_data_queue`, `analyse_data`, `next_open_data_batch`, validator) with the old and the new code on the same data: same results, apart from the fixed order of publication project links (see below). API steps compared on small samples (ETIS programme 137, 7 OpenAlex lookups incl. title searches, 5 articles for OpenAIRE, ScholeXplorer, DataCite and Europe PMC, all OpenAIRE graph projects, full texts of 6 articles from different sources): same results, apart from the order that the APIs give.
- `get_data`: bad responses and saving with helper functions (`check_bad_response`, `save_data`), like in `get_open_data_candidates`. `OPEN_ACCESS_VERSIONS` is now `PEER_REVIEWED_VERSIONS`, like in `get_fulltext` and the validator.
- `get_etis_project_horizon_ids`: search API matches in one loop over the searched fields, framework programme ID prefixes in one function, OpenAIRE graph projects loaded once. Logs the number of title matches. The two best title candidates of unmatched projects go to the log instead of print. Removed the old manual checks comment: 5a326ac0 is now matched by publication project links, fac0ede3 is not in the current ETIS pull, the other 2 (EIT, Horizon Europe) had no answer. Publication project link counts are saved in a fixed order - before, the order changed between runs (set order), so the results of two runs differed.
- `get_openaire_search_project_results`: removed unused inputs, logs the number of projects with matches.
- All scripts: the copies of the shared helper functions are the same in every script (`rstrip("/")` instead of `strip("/")` in paths, which would break absolute paths). Smaller: `os.makedirs(exist_ok=True)`, removed unused parameters and variables, constants for repeated values (polars print options, funding hint length, allowed values in the validator).

Review step 1: analysis logic for the question how many Estonian Horizon projects don't fulfil the open access mandate. Decisions: analyse by article, with the article's ETIS projects, Horizon grants and mandates on each article. Only articles with an Estonian author count - researchers can't be held accountable for articles they didn't write. All articles of the Horizon projects count; whether the article links to the grant is a separate dimension. Open access of publications and open data are separate verdicts. Mandates are project dimensions: all Horizon projects (incl. ERA-NET and EIT) have the publication mandate, the data mandate comes from OpenAIRE (unknown for unmatched projects). Data mandate compliance can be derived by comparing open data with the data mandate.

`get_data` gets the author lists from OpenAlex (authorships) and saves ETIS authors (with whether they are in the OpenAlex author list) and ETIS institutions (with business registry code) of each article. An article has an Estonian author if an author in the published author list has an Estonian affiliation, or an ETIS author is in the list and ETIS gives an Estonian institution (OpenAlex lacks many affiliations). Names are compared fuzzily (double surnames, "Surname, Name", Estonian spelling of Russian names, e.g. Semtšenko - Semchenko). Title search matches are fetched again by OpenAlex ID, because search results have at most 100 authors. Rerun of the OpenAlex step: 840 of 842 articles have an Estonian author. The 2 that don't (799787ca, 157fa43f) have only foreign affiliations, although an ETIS author is in the author list. 67 ETIS authors of 43 articles are not in the OpenAlex author list (name changes, consortium members, spelling).

`make_open_data_queue`: new open access check reason - not open by ETIS and OpenAlex, but OpenAIRE has an open copy that OpenAlex doesn't list and that isn't a preprint (16 articles, mostly Zenodo). Scopus records that OpenAIRE marks open are not copies. The projects of each article have programme codes, the publication mandate and `HORIZON_GRANT_LINKED` (OpenAIRE project links or OpenAlex awards of the article have the project's Horizon ID: 718 of 936 article-project pairs). Articles without an Estonian author stay in the queue, but `next_open_data_batch` skips them. 124 articles need an open access check.

`analyse_data` saves `articles_<timestamp>.json`: one record per article with the dimensions above, open access status and how it was settled, data label and open data status. A full text check verdict now settles open access of every checked article, not only of the ones that needed a check, and the analysis compares it with the automatic status. Articles pending an open access check have unknown open access (before, they counted as not open): 608 of the 718 articles with known status are open (85%), 122 pending. Articles linked to their grant are open more often (90% vs 65%), partly because OpenAIRE gets grant links from repository deposits.

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

ETIS publications with IS_PUBLIC_FILE = true and IS_OPEN_ACCESS = false are sometimes open (03a149cb-e0e5-418b-b01d-1b8980d12cc5, https://www.eccomas2016.org/proceedings/pdf/5264.pdf), sometimes not (f0078a05-4621-422b-bd14-1b293447fbfc, http://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=7743740&isnumber=7743712).

Example of a paper with summary data and code available: https://www.nature.com/articles/s41586-022-05165-3#data-availability

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
