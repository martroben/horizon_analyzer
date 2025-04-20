# standard
import datetime
import json
import logging
import os
import re
import sys
import time
import urllib
# external
import polars
import requests
import tqdm


##########
# Inputs #
##########

RAW_DATA_DIRECTORY_PATH = "./data/raw/"
RESULTS_DATA_DIRECTORY_PATH = "./data/results/"
projects_path = os.path.join(RAW_DATA_DIRECTORY_PATH, "project.csv")

project_schema = {
    "id": polars.Utf8,
    "acronym": polars.Utf8,
    "code": polars.Utf8,
    "startdate": polars.Date,
    "start_year": polars.Int64,
    "enddate": polars.Date,
    "end_year": polars.Int64,
    "funding_lvl0": polars.Utf8,
    "funding_lvl1": polars.Utf8,
    "funding_lvl2": polars.Utf8,
    "callidentifier": polars.Utf8,
    "type": polars.Utf8,
    "topic": polars.Utf8,
    "topicdescription": polars.Utf8,
    "cost": polars.Float64
}

project = polars.read_csv(projects_path, schema=project_schema)
print(project.head())
