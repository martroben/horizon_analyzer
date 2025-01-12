# standard
import json
import logging
import sys


##########
# Inputs #
##########

OPEN_ACCESS_DATA_PATH = "./data/results/open_access_data_20250112182245UTC.json"


#####################
# Environment setup #
#####################

# Logger
logger = logging.getLogger()
logger.setLevel("INFO")
logger.addHandler(logging.StreamHandler(sys.stdout))


#############
# Load data #
#############

with open(OPEN_ACCESS_DATA_PATH, encoding="utf8") as read_file:
    open_access_data = json.loads(read_file.read())


################
# Analyse data #
################

publications_open = []
publications_not_open = []
for publication in open_access_data:
    # Publication is open if it is manually verified that it's open
    if publication["IS_AVAILABLE_MANUALLY_CHECKED"]:
        publications_open += [publication]
        continue

    # Publication is open if ETIS and Open Access Button both say that it's open and there is no manually checked info
    if publication["IS_AVAILABLE_MANUALLY_CHECKED"] is None and publication["OA_BUTTON_URL"] and publication["IS_OPEN_ACCESS"]:
        publications_open += [publication]
        continue

    publications_not_open += [publication]

info_string = f'{len(publications_open)} of {len(open_access_data)} publications ({round(len(publications_open) / len(open_access_data) * 100)}%) are open to read'
logger.info(info_string)
