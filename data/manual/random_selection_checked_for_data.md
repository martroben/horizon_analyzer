# Motivation
It seems to be hard to manually check for whether a publication has open access data or not. To get a better idea of the situation, I selected a random sample of 20 publication GUIDs to manually check for data.

# Selected GUIDs
1. 5bd15d8a-8d24-4c10-9e62-04cb85602b5e
2. 81f611f3-629d-4cbb-a59e-4df6a34ac290
3. 9087611f-3dd3-4bd5-a127-f38a91a5f35a
4. 116b3e75-e8b1-4705-9650-28f3da7fc052
5. 371f55d4-8474-468d-8c56-c454d6b34e58
6. d8ca08a8-4a94-41fa-909e-02dfe04fca42
7. 8a065e38-97dc-4e0c-a64c-465b320c7d6c
8. 39cb1d48-36ac-4cbe-a139-3a5e718779ba
9. 7acfa15b-766a-4188-9e90-82a3b265ac41
10. df8d34d1-6d8a-4694-9e9b-1101afed20f8
11. 3f5f834b-7343-45b4-b053-cfac698c016d
12. badd8530-41d1-408b-8223-e9944c8d5fa9
13. 907c1854-5d2c-43c6-bf8b-6605d000f1f1
14. 21bd1269-486a-4e0e-87bc-38431be0ed3e
15. 5c3170f9-5646-48ca-9f71-b752c41ba8bd
16. 9190ba78-161d-4efb-b87a-eef4c2c159e2
17. 30cc44af-536c-4f3b-a622-d7f812119635
18. a40c5f1f-c826-4d1c-bb1e-f8950b45b322
19. 4e24e03b-ab74-4456-982e-ccdc64dd343c
20. f61a5133-288a-4960-a38d-c2fa62f84fef


# 1. 5bd15d8a-8d24-4c10-9e62-04cb85602b5e
## Current data
```json
{
    "GUID": "5bd15d8a-8d24-4c10-9e62-04cb85602b5e",
    "PROJECT_GUIDS": [
        "6921c6e6-4bf4-4aba-b120-6836bc172bb0"
    ],
    "TITLE": "Tumor-penetrating peptide for systemic targeting of Tenascin-C.",
    "PERIODICAL": "Scientific Reports",
    "DOI": "10.1038/s41598-020-62760-y",
    "URL": "",
    "IS_OPEN_ACCESS": true,
    "OPEN_ACCESS_TYPE": "gold",
    "LICENSE": "Attribution (CC BY)",
    "IS_PUBLIC_FILE": true,
    "OA_BUTTON_URL": "https://www.nature.com/articles/s41598-020-62760-y.pdf",
    "IS_AVAILABLE_MANUALLY_CHECKED": null
}
```
## Publication link
https://www.nature.com/articles/s41598-020-62760-y.pdf
Relevant sections from the article pdf
```
Acknowledgements
We thank Gabriele Bergers for WT GBM cells, Erkki Juronen for help with ÄKTA Protein Purification System,
Rein Laiverik for help with the characterization of the NWs. This work was supported by the European Regional
Development Fund (Project No. 2014–2020.4.01.15–0012), by EMBO Installation grant #2344 (to T. Teesalu),
European Research Council grants GBMDDS and GLIOGUIDE from European Regional Development Fund (to
T. Teesalu), Wellcome Trust International Fellowship WT095077MA (to T. Teesalu), and Norwegian-Estonian
collaboration grant EMP181 (to T. Teesalu). We also acknowledge the support of Estonian Research Council
(grant PRG230 and EAG79 to T. Teesalu) and Estonian Research Council grants (IUT20‐17 and PSG230 to
S. Kopanchuk).

Additional information
Supplementary information is available for this paper at https://doi.org/10.1038/s41598-020-62760-y.
```

The supplementary information link directs to the journal page for the article. From there the **supporting information** section gives the following link: https://static-content.springer.com/esm/art%3A10.1038%2Fs41598-020-62760-y/MediaObjects/41598_2020_62760_MOESM1_ESM.pdf

The supporting information has additional methodological info, but no raw data.

## Project cordis data
- Project title from ETIS: Commercialising a novel glioblastoma targeted therapy and a companion diagnostic compound
- Project cordis link (search by title): https://cordis.europa.eu/project/id/780915
- Project annotation: GLIOGUIDE
- The project is mentioned in the article acknowledgements: GLIOGUIDE from European Regional Development Fund (to
T. Teesalu)

However, the cordis results section shows 3 other articles instead
```
Peptide-guided nanoparticles for glioblastoma targeting
https://doi.org/10.1016/j.jconrel.2019.06.018
Author(s): Pille Säälik, Prakash Lingasamy, Kadri Toome, Ignacio Mastandrea, Liat Rousso-Noori, Allan Tobi, Lorena Simón-Gracia, Hedi Hunt, Päärn Paiste, Venkata Ramana Kotamraju, Gabriele Bergers, Toomas Asser, Tõnu Rätsep, Erkki Ruoslahti, Rolf Bjerkvig, Dinorah Friedmann-Morvinski, Tambet Teesalu
Published in: Journal of Controlled Release, Issue 308, 2019, Page(s) 109-118, ISSN 0168-3659
Publisher: Elsevier BV
DOI: 10.1016/j.jconrel.2019.06.018

Bi-specific tenascin-C and fibronectin targeted peptide for solid tumor delivery
https://doi.org/10.1016/j.biomaterials.2019.119373
Author(s): Prakash Lingasamy, Allan Tobi, Maarja Haugas, Hedi Hunt, Päärn Paiste, Toomas Asser, Tõnu Rätsep, Venkata Ramana Kotamraju, Rolf Bjerkvig, Tambet Teesalu
Published in: Biomaterials, Issue 219, 2019, Page(s) 119373, ISSN 0142-9612
Publisher: Pergamon Press Ltd.
DOI: 10.1016/j.biomaterials.2019.119373

Dual-peptide functionalized acetalated dextran-based nanoparticles for sequential targeting of macrophages during myocardial infarction
https://doi.org/10.1039/c9nr09934d
Author(s): Giulia Torrieri, Flavia Fontana, Patrícia Figueiredo, Zehua Liu, Mónica P. A. Ferreira, Virpi Talman, João P. Martins, Manlio Fusciello, Karina Moslova, Tambet Teesalu, Vincenzo Cerullo, Jouni Hirvonen, Heikki Ruskoaho, Vimalkumar Balasubramanian, Hélder A. Santos
Published in: Nanoscale, Issue 12/4, 2020, Page(s) 2350-2358, ISSN 2040-3364
Publisher: Royal Society of Chemistry
DOI: 10.1039/c9nr09934d
```

ETIS GUIDs of these articles:
- Peptide-guided nanoparticles for glioblastoma targeting: be5368e1-3b11-4b0a-84c3-78fa37ee56d0
- Bi-specific tenascin-C and fibronectin targeted peptide for solid tumor delivery: 602843ab-c289-4214-9792-1bb4adce81b5
- Dual-peptide functionalized acetalated dextran-based nanoparticles for sequential targeting of macrophages during myocardial infarction: 7fb25b26-1bfa-49a6-825a-a51e21fb5ba5

## Project ETIS data
Let's check if all project publications cite the Horizon funding program
### b7b89fef-78b6-44ec-ae94-1dbd51e51c7e
Targeting pro-tumoral macrophages in early primary and metastatic breast tumors with CD206-binding mUNO peptide
- Not open access, can't see acknowledgements.

### 372ef27c-a963-4835-ae0c-fe294ebfc828
Neuropilin-1 facilitates SARS-CoV-2 cell entry and infectivity
- https://www.science.org/cms/asset/be8a4726-631c-474e-bfb7-51cb8fc7a7cc/pap.pdf
- Is not present in cordis project info
- Project funding mentioned
```
T.T. and
A.T. are supported by the European Regional Development Fund (Project No.
2014-2020.4.01.15-0012), by Welcome Trust International Fellowship
WT095077MA, by European Research Council grant GLIOGUIDE and Estonian
Research Council (grants PRG230 and EAG79, to T.T.)
```
### 4f637a42-e881-4237-8467-e793da0d7167
New Tools for Streamlined In Vivo Homing Peptide Identification. In:  Cell Penetrating Peptides. (385−412).  Humana Press. (Methods in Molecular Biology; 2383)
- Not classified as a scientific article in ETIS.
```
"ClassificationCode": "3.1.",
"ClassificationNameEng": "Articles/chapters in books published by the publishers listed in Annex (including collections indexed by the Web of Science Book Citation Index, Web of Science Conference Proceedings Citation Index, Scopus)",
```
### 7fb25b26-1bfa-49a6-825a-a51e21fb5ba5
Dual-peptide functionalized acetalated dextran-based nanoparticles for sequential targeting of macrophages during myocardial infarction
- https://pubs.rsc.org/en/content/articlepdf/2020/nr/c9nr09934d
- Is present in cordis project info
- Project funding mentioned
```
T. Teesalu was supported by the European Union
through the European Regional Development Fund (Project
No. 2014-2020.4.01.15-0012) and by European Research
Council grant GlioGuide from European Regional
Development Fund.
```
### 43a163a2-f43e-4f6e-b65c-6f8009a3582c
Exposed CendR Domain in Homing Peptide Yields Skin-Targeted Therapeutic in Epidermolysis Bullosa
- https://www.cell.com/molecular-therapy-family/molecular-therapy/pdf/S1525-0016(20)30251-3.pdf
- Is not present in cordis project info
- Project funding mentioned
```
T.T. was supported by the Eu-
ropean Regional Development Fund (Project 2014-2020.4.01.15-
0012), by European Research Council grant GLIOGUIDE from the
European Regional Development Fund, and by the Estonian Research
Council (grants PRG230 and EAG79).
```
### be5368e1-3b11-4b0a-84c3-78fa37ee56d0
Peptide-guided nanoparticles for glioblastoma targeting
- https://lirias.kuleuven.be/bitstream/123456789/639664/3/Saalik%20et%20al.pdf
- Is present in cordis project info
- Project funding mentioned
```
by EMBO Installation grant #2344 (to T. Teesalu), European Research Council grants4
GBMDDS and GLIOGUIDE from European Regional Development Fund (to T. Teesalu), Wellcome Trust5
International Fellowship WT095077MA (to T. Teesalu), and Norwegian-Estonian collaboration grant6
EMP181 (to T. Teesalu). We also acknowledge the support of Estonian Research Council (grant PRG2307
to T. Teesalu).
```
### 91506e7f-ae6a-49bb-9132-675dc37b7136
PL1 Peptide Engages Acidic Surfaces on Tumor-Associated Fibronectin and Tenascin Isoforms to Trigger Cellular Uptake
- https://www.mdpi.com/1999-4923/13/12/1998
- Is not present in cordis project info
- Project funding mentioned
```
This work was supported by the European Regional Development Fund (Project No. 2014-2020.4.01.15-0012), by EMBO Installation Grant No. 2344 (to T.T.), European Research Council grants GBMDDS (Project No: 281910) and GLIOGUIDE (project No. 780915) from European Regional Development Fund (to T.T.), Wellcome Trust International Fellowship WT095077MA (to T.T.), and Norwegian-Estonian collaboration grant EMP181 (to T.T.). We also acknowledge the support of Estonian Research Council (grant PRG230 and EAG79 to T.T.)
```
### 745844fd-2d62-4d41-bbcf-8f729b1edc17
Tumor Penetrating Peptide-Functionalized Tenascin-C Antibody for Glioblastoma Targeting
- https://pubmed.ncbi.nlm.nih.gov/33001014
- Is not present in cordis project info
- Project funding mentioned
```
This work was supported by the European Regional De-
velopment Fund (Project No. 2014-2020.4.01.15-0012), by
EMBO Installation grant #2344 (to T. Teesalu), European
Research Council grant GLIOGUIDE (780915) from Euro-
pean Regional Development Fund (to T. Teesalu), Well-
come Trust International Fellowship WT095077MA (to T.
Teesalu), and Norwegian-Estonian collaboration grant EM-
P181 (to T. Teesalu). We also acknowledge the support of
the Estonian Research Council (grants PRG230 and EAG79
to T. Teesalu).
```
### 602843ab-c289-4214-9792-1bb4adce81b5
Bi-specific tenascin-C and fibronectin targeted peptide for solid tumor delivery
- https://doi.org/10.1016/j.biomaterials.2019.119373
- Is present in cordis project info
- Project funding mentioned
```
This work was supported by the European Union through the European Regional Development Fund (Project No. 2014-2020.4.01.15-0012), by EMBO Installation Grant #2344, European Research Council grants GLIOMA DDS and GlioGuide from European Regional Development Fund and Wellcome Trust International Fellowship WT095077MA (TT), Cancer Center Support grant CA30199 from the US National Cancer Institute to the Sanford Burnham Prebys Medical Discovery Institute and grants from The Norwegian Cancer Society and the Norwegian Research Council.
```
### b9082faa-1240-4cd6-a85f-9b18cb79e4f4
Neuropilin-1 is a host factor for SARS-CoV-2 infection
- https://www.science.org/cms/asset/b7734c5b-6668-41ee-a2a4-c252ba76fc5b/pap.pdf
- Is not present in cordis project info
- Project funding mentioned
```
TT was supported by the European
Regional Development Fund (Project No. 2014-2020.4.01.15-0012), by European
Research Council grant GLIOGUIDE and Estonian Research Council (grants
PRG230 and EAG79, to T.T.). 
```
### eb0b5636-fec6-4835-a0f3-5ef341b898de
Novel Anthracycline Utorubicin for Cancer Therapy
- https://onlinelibrary.wiley.com/doi/pdfdirect/10.1002/anie.202016421
- Is not present in cordis project info
- Project funding mentioned
```
European
Regional Development Fund (Project No. 2014-2020.4.01.15-
0012), by EMBO Installation grant #2344 (to T.T.), European
Research Council grant GLIOGUIDE (780915) from Euro-
pean Regional Development Fund (to T.T.), Wellcome Trust
International Fellowship WT095077MA (to T.T.), and Nor-
wegian-Estonian collaboration grant EMP181 (to T.T.). We
also acknowledge the support of Estonian Research Council
(grants PRG230 and EAG79 to T.T.).
```
### 5bd15d8a-8d24-4c10-9e62-04cb85602b5e
- https://www.nature.com/articles/s41598-020-62760-y.pdf
- Is not present in cordis project info
- Project funding mentioned
```
Acknowledgements
We thank Gabriele Bergers for WT GBM cells, Erkki Juronen for help with ÄKTA Protein Purification System,
Rein Laiverik for help with the characterization of the NWs. This work was supported by the European Regional
Development Fund (Project No. 2014–2020.4.01.15–0012), by EMBO Installation grant #2344 (to T. Teesalu),
European Research Council grants GBMDDS and GLIOGUIDE from European Regional Development Fund (to
T. Teesalu), Wellcome Trust International Fellowship WT095077MA (to T. Teesalu), and Norwegian-Estonian
collaboration grant EMP181 (to T. Teesalu). We also acknowledge the support of Estonian Research Council
(grant PRG230 and EAG79 to T. Teesalu) and Estonian Research Council grants (IUT20‐17 and PSG230 to
S. Kopanchuk).
```
### faba4402-d9e9-4c7e-9b4c-a54f49f821d7
Homing Peptides for Cancer Therapy. In: Fontana, Flavia Santos, Hélder A (Ed.). Bio-Nanomedicine for Cancer Therapy. (29–48). Springer Nature Switzerland AG.
- Not classified as a scientific article in ETIS.
```
"ClassificationCode": "3.1.",
"ClassificationNameEng": "Articles/chapters in books published by the publishers listed in Annex (including collections indexed by the Web of Science Book Citation Index, Web of Science Conference Proceedings Citation Index, Scopus)",
```
### 62c8100b-0c6b-4fd9-b89e-87f4318e57b3
Silver Nanocarriers Targeted with a CendR Peptide Potentiate the Cytotoxic Activity of an Anticancer Drug
- https://onlinelibrary.wiley.com/doi/pdfdirect/10.1002/adtp.202000097
- Is not present in cordis project info
- Project funding mentioned
```
This work was supported by the European Union
through the European Regional Development Fund (Project No. 2014–
2020.4.01.15-0012), by Estonian Research Council grants PRG230 and
EAG79 (to T.T.), European Research Council starting grant GLIOGUIDE
from European Regional Development Fund (to T.T.), Wellcome Trust In-
ternational Fellowship WT095077MA (to T.T.)
```
### 13caa5ad-f2aa-46f4-8c27-74fa5c5fe860
In vivo phage display: identification of organ-specific peptides using deep sequencing and differential profiling across tissues
- https://academic.oup.com/nar/article-pdf/49/7/e38/37123769/gkaa1279.pdf
- Is not present in cordis project info
- Project funding mentioned
```
European Regional Development Fund [2014–
2020.4.01.15-0012]; EMBO Installation [2344 to T.T.];
European Research Council grant GLIOGUIDE from
European Regional Development Fund [780915 to T.T.];
Wellcome Trust International Fellowship [WT095077MA
to T.T.]; Norway Grants [EMP181 to T.T.]; Estonian
Research Council [PRG230, EAG79 to T.T.]. Funding
for open access charge: Wellcome Trust International
Fellowship.
```
### cc8ddfb3-ce35-4892-bc66-6e916c75d819
Phage-Display-Derived Peptide Binds to Human CD206 and Modeling Reveals a New Binding Site on the Receptor
https://upcommons.upc.edu/bitstream/2117/172370/1/manuscript_muno_v15tt_ea.pdf
- Is not present in cordis project info
- Project funding mentioned
```
European Regional Development Fund (Project No. 2014-2020.4.01.15-0012, to T.
Teesalu), European Research Council grant GLIOGUIDE from European Regional Development Fund
(to T. Teesalu), Estonian Research Council grant PRG230 (to T. Teesalu)
```
## Other funding projects mentioned in acknowledgements
- European Regional Development Fund [2014–2020.4.01.15-0012] GENTRANSMED. https://genomics.ut.ee/en/projects
- EMBO Installation 2344. https://www.embo.org/funding/fellowships-grants-and-career-support/installation-grants/
- PRG230: https://www.etis.ee/portal/projects/display/dd256cea-2f7d-4936-b373-9c4d80fe504b
- EAG79: https://www.etis.ee/portal/projects/display/0f30600d-3fdd-426c-aec2-c016a92a5dc6
- Wellcome Trust International Fellowship: https://wellcome.org/grant-funding/schemes/international-training-fellowships
- European Research Council grant GBMDDS (project 281910) / GLIOMADDS from European Regional Development Fund: https://edukad.etag.ee/project/3252?lang=en

# 81f611f3-629d-4cbb-a59e-4df6a34ac290
## Current data
```json
{
    "GUID": "81f611f3-629d-4cbb-a59e-4df6a34ac290",
    "PROJECT_GUIDS": [
        "1b69509f-38de-45de-be7e-f280b98e8acc"
    ],
    "TITLE": "Circular Renovation of an Apartment Building with Prefabricated Additional Insulation Elements to Nearly Zero Energy Building",
    "PERIODICAL": "Journal of Sustainable Architecture and Civil Engineering",
    "DOI": "10.5755/j01.sace.34.1.35674",
    "URL": "https://sace.ktu.lt/index.php/DAS/article/view/35674",
    "IS_OPEN_ACCESS": true,
    "OPEN_ACCESS_TYPE": "gold",
    "LICENSE": "Attribution (CC BY)",
    "IS_PUBLIC_FILE": true,
    "OA_BUTTON_URL": "https://sace.ktu.lt/index.php/DAS/article/download/35674/16249",
    "IS_AVAILABLE_MANUALLY_CHECKED": null
}
```
## Publication link
https://sace.ktu.lt/index.php/DAS/article/download/35674/16249

No mention of raw data.

## Project cordis data
- Project title from ETIS: Driving decarbonization of the EU building stock by enhancing a consumer centred and locally based circular renovation process
- Project cordis link (search by title): https://cordis.europa.eu/project/id/841850
- Project annotation: DRIVE 0
- The project is mentioned in the article acknowledgements: This work has been supported by the European Commission through the H2020 project DRIVE0, by the Estonian Centre of Excellence in Energy Efficiency, ENER (grant TK230) funded by the Estonian Ministry of Education and Research, and by the Estonian Research Council through the grant PRG483

Dissemination document talks about flyers and social media. No data or DMP included.


# 9087611f-3dd3-4bd5-a127-f38a91a5f35a
## Current data
```json
{
    "GUID": "9087611f-3dd3-4bd5-a127-f38a91a5f35a",
    "PROJECT_GUIDS": [
        "50c54142-34fd-47f7-b375-145a7b28ecd4"
    ],
    "TITLE": "To be or not to be: the case of the hot WHIM absorption in the blazar PKS 2155–304 sight line",
    "PERIODICAL": "Astronomy and Astrophysics",
    "DOI": "10.1051/0004-6361/201833109",
    "URL": "",
    "IS_OPEN_ACCESS": true,
    "OPEN_ACCESS_TYPE": "bronze",
    "LICENSE": "",
    "IS_PUBLIC_FILE": true,
    "OA_BUTTON_URL": "https://www.aanda.org/articles/aa/pdf/2019/01/aa33109-18.pdf",
    "IS_AVAILABLE_MANUALLY_CHECKED": null
}
```
## Publication link
https://www.aanda.org/articles/aa/pdf/2019/01/aa33109-18.pdf

No mention of raw data.

Some data is linked from the journal publication web page: https://www.aanda.org/articles/aa/full_html/2019/01/aa33109-18/aa33109-18.html

Links to: http://simbad.u-strasbg.fr/simbad/sim-ref?querymethod=bib&simbo=on&submit=submit+bibcode&bibcode=2019A%26A...621A..88N

However, it seems to be summary data, rather than raw data.

The project in mentioned in the article acknowledgements: We acknowledge the support by the Estonian Research Council grants PUT246, IUT26-2, IUT40-2, and by the European Regional Development Fund (TK133 and MOBTP86). Thanks to the Chandra X-ray observatory HelpDesk. JN acknowledges the funds from a European Horizon 2020 program AHEAD (Integrated Activities in the High Energy Astrophysics Domain), and from FINCA (the Finnish Centre for Astronomy with ESO). Thanks to Jelle de Plaa for his help with the Spex analysis

## Project cordis data
There is a link to data repository in the results: https://cordis.europa.eu/project/id/654215/results

It seems to include the raw data as tar files (unfortunately it's served via a random wordpress site): http://iachecdb.iaps.inaf.it/?page_id=144&cfrom=01+-+02+-+2015&cto=25+-+02+-+2025&limit=-1

Data available: Yes!

