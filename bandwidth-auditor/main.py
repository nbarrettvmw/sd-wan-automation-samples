from dataclasses import dataclass
from typing import cast
import dotenv
import json
import os
import pandas as pd
from requests import Session, session
import time


@dataclass
class CommonData:
    vco: str
    token: str


def do_portal(s: Session, shared: CommonData, method: str, params: dict):
    resp = s.post(
        f"https://{shared.vco}/portal/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        },
    ).json()
    if "result" not in resp:
        raise ValueError(json.dumps(resp, indent=2))
    return resp["result"]


@dataclass
class LinkData:
    edge_id: int
    edge_name: str
    link_internal_id: str
    link_name: str
    isp: str
    upstream_mbps: float
    downstream_mbps: float


def get_link_data(s: Session, shared: CommonData) -> list[LinkData]:
    # start_time = int((time.time() - 24 * 60 * 60) * 1000)
    start_time = int((time.time() - 30 * 60) * 1000)
    resp = do_portal(
        s,
        shared,
        "monitoring/getAggregateEdgeLinkMetrics",
        params={
            "metrics": ["bpsOfBestPathRx", "bpsOfBestPathTx"],
            "interval": {
                "start": start_time,
            },
        },
    )
    return [
        LinkData(
            l["link"]["edgeId"],
            l["link"]["edgeName"],
            l["link"]["internalId"],
            l["link"]["displayName"],
            l["link"]["isp"],
            l["bpsOfBestPathTx"] / 1000000,
            l["bpsOfBestPathRx"] / 1000000,
        )
        for l in resp
    ]


def get_edge_stack(s: Session, shared: CommonData, edge_id: int) -> list[dict]:
    return do_portal(
        s, shared, "edge/getEdgeConfigurationStack", params={"edgeId": edge_id}
    )


def update_module(
    s: Session, shared: CommonData, configuration_module_id: int, new_data: dict
):
    do_portal(
        s,
        shared,
        "configuration/updateConfigurationModule",
        params={
            "id": configuration_module_id,
            "_update": {
                "data": new_data,
            },
        },
    )


def extract_module(module_stack: list[dict], module_name: str) -> dict | None:
    return next((m for m in module_stack if m["name"] == module_name), None)


def audit_links(s: Session, shared: CommonData):
    # fetch the link metrics and build pandas frame
    links_df = pd.DataFrame(get_link_data(s, shared))

    if len(links_df) == 0:
        print("no links found")
        return

    # select any link which measured 200 > downstream > 175 while having upstream < 175
    # these are candidates for when burst mode should have been enabled
    affected_links = links_df[
        (links_df["downstream_mbps"] < 200.0)
        & (links_df["downstream_mbps"] > 175.0)
        & (links_df["upstream_mbps"] < 175.0)
    ]
    affected_edges = affected_links.groupby("edge_id")

    print(f"{len(affected_links)} affected links found on {len(affected_edges)} edges")

    for edge_id, df in affected_edges:
        edge_stack = get_edge_stack(s, shared, cast(int, edge_id))
        # edge-specific config is 0th element
        edge_config = edge_stack[0]

        wan_module = extract_module(edge_config["modules"], "WAN")
        if wan_module is None:
            continue

        # pandas way to retrieve edge_name from first row
        edge_name = df["edge_name"].head(1).item()

        wan_id = wan_module["id"]
        wan_data = wan_module["data"]
        wan_links = wan_data["links"]

        should_update_module = False
        for wan_link in wan_links:
            if wan_link["bwMeasurement"] != "SLOW_START":
                continue

            link_internal_id = wan_link["internalId"]

            # pandas way to check if a value exists in a column
            id_series = df["link_internal_id"]
            if len(id_series.where(id_series == link_internal_id)) > 0:
                link_name = wan_link["name"]
                print(f"updating edge [{edge_name}] link [{link_name}]")
                # STATIC means burst mode
                wan_link["bwMeasurement"] = "STATIC"
                # set flag to update the module once done iterating over links
                should_update_module = True

        if should_update_module:
            update_module(s, shared, wan_id, wan_data)


def readenv(name: str) -> str:
    val = os.getenv(name)
    assert val is not None, f"missing env var {name}"
    return val


dotenv.load_dotenv(".env")
shared = CommonData(readenv("VCO"), readenv("VCO_TOKEN"))

s = session()
s.headers.update({"Authorization": f"Token {shared.token}"})

audit_links(s, shared)
