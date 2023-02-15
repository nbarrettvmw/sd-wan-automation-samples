import dotenv
import json
import os
from requests import Session, session
import sys

import api
from models import CommonData
from util import extract_module


def read_env(name: str) -> str:
    value = os.getenv(name)
    assert value is not None, f"missing environment var {name}"
    return value


dotenv.load_dotenv(".env")
shared = CommonData(
    read_env("VCO"),
    read_env("VCO_TOKEN"),
    read_env("ENT_LOG_ID"),
    read_env("BRANCH_PROF_LOG_ID"),
    read_env("BRANCH_LIC_LOG_ID"),
    read_env("GOOGLE_MAPS_API_KEY"),
)

s = session()
s.headers.update({"Authorization": f"Token {shared.token}"})

edge_id = 34225
cfg = api.get_configuration_stack(s, shared, edge_id)
edge_specific = cfg[0]
device_settings = extract_module(edge_specific["modules"], "deviceSettings")

output_file = sys.argv[1]
with open(output_file, 'w') as fp:
    json.dump(device_settings, fp, indent=2)
