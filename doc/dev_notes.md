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
