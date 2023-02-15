import dotenv
import jsonpatch
from ipaddress import ip_address, ip_network, IPv4Network, IPv4Address
import os
from requests import Session, session
from typing import Optional, cast
import uuid

from api import *
from models import BranchData, CommonData, WanData
from util import calculate_lat_lon, extract_module, ipv4_address, ipv4_network


def build_static_routes_patch(branch: BranchData) -> list[dict]:
    return [
        {
            "op": "add",
            "path": "/segments/0/routes/static/-",
            "value": {
                "advertise": True,
                "cidrPrefix": str(n.prefixlen),
                "cost": 0,
                "description": "",
                "destination": str(n.network_address),
                "gateway": str(branch.transit_net[250]),
                "icmpProbeLogicalId": None,
                "netmask": str(n.netmask),
                "preferred": True,
                "sourceIp": None,
                "subinterfaceId": -1,
                "vlanId": None,
                "wanInterface": "GE2",
            },
        }
        for n in branch.corporate_nets
    ]


def build_vlan_999_patch() -> list[dict]:
    return [
        {
            "op": "add",
            "path": "/lan/networks/0/cidrIp",
            "value": "169.254.255.255",
        },
        {
            "op": "add",
            "path": "/lan/networks/0/netmask",
            "value": "255.255.255.255",
        },
        {
            "op": "add",
            "path": "/lan/networks/0/cidrPrefix",
            "value": "32",
        },
    ]


def build_ge2_patch(branch: BranchData, current_ds: dict) -> list[dict]:
    ge2_index = next(
        (i for i, e in enumerate(current_ds["routedInterfaces"]) if e["name"] == "GE2"),
        None,
    )

    if ge2_index is None:
        raise ValueError("GE2 was not found in routedInterfaces")

    return [
        {
            "op": "add",
            "path": f"/routedInterfaces/{ge2_index}/addressing/cidrIp",
            "value": str(branch.transit_net[254]),
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{ge2_index}/addressing/cidrPrefix",
            "value": branch.transit_net.prefixlen,
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{ge2_index}/addressing/netmask",
            "value": str(branch.transit_net.netmask),
        },
        {
            "op": "replace",
            "path": f"/routedInterfaces/{ge2_index}/l2/probeInterval",
            "value": "3",
        },
        {
            "op": "move",
            "from": f"/routedInterfaces/{ge2_index}",
            "path": "/routedInterfaces/0",
        },
        {
            "op": "remove",
            "path": "/routedInterfaces/0/cellular",
        },
    ]


def provision_branch(s: Session, shared: CommonData, branch: BranchData):
    lat_lon = calculate_lat_lon(
        shared.google_maps_api_key, branch.postal_code, branch.country
    )
    if lat_lon is None:
        raise LookupError("failed to retrieve lat/lon")

    post_resp = post_edge(
        s,
        shared,
        "edge6X0",
        shared.branch_profile_logical_id,
        extras={
            "name": branch.name,
            "license": shared.branch_license_logical_id,
            "haEnabled": True,
            "site": {
                "lat": lat_lon.lat,
                "lon": lat_lon.lon,
                "contactName": branch.contact_name,
                "contactEmail": branch.contact_email,
            },
            "serialNumber": branch.serial_number,
        },
    )

    edge_url = post_resp["_href"]
    edge_url = f"https://{shared.vco}{edge_url}"
    edge_logical_id = post_resp["logicalId"]

    try:
        # use edge logical ID to get edge ID using APIv1
        edge_info_v1 = find_edge(s, shared, edge_logical_id)
        if edge_info_v1 is None:
            raise RuntimeError("could not find v1 info for new edge")
        edge_id = edge_info_v1["id"]

        edge_config_stack = get_configuration_stack(s, shared, edge_id)
        edge_specific_config = edge_config_stack[0]

        edge_ds = extract_module(edge_specific_config["modules"], "deviceSettings")
        if edge_ds is None:
            raise LookupError("could not find deviceSettings module")
        edge_ds_id = edge_ds["id"]

        edge_ds_data = edge_ds["data"]

        static_routes_patch = build_static_routes_patch(branch)
        vlan_999_patch = build_vlan_999_patch()
        ge2_patch = build_ge2_patch(branch, edge_ds_data)

        # zscaler cannot be done until edge is activated
        patch_set = jsonpatch.JsonPatch(
            [
                *static_routes_patch,
                *vlan_999_patch,
                *ge2_patch,
            ]
        )
        patch_set.apply(edge_ds_data, in_place=True)

        update_configuration_module(s, shared, edge_ds_id, edge_ds_data)

    finally:
        return


branch_data = BranchData(
    "test edge 778", # name
    "US", # country
    "62269", # postal code
    "Nick Barrett", # on-site contact name
    "nbarrett@vmware.com", # on-site contact email
    "someserialnumber", # put serial # here
    ipv4_network("10.253.252.0/24"), # corp transit net
    [ipv4_network("10.253.253.0/24")] # corp networks
)


def read_env(name: str) -> str:
    value = os.getenv(name)
    assert value is not None, f"missing environment var {name}"
    return value


dotenv.load_dotenv(".env")
shared = CommonData(
    read_env("VCO"),
    read_env("VCO_TOKEN"),
    read_env("ENT_LOG_ID"),
    "", #read_env("ZS_CLOUD_SUB_LOG_ID"),
    read_env("BRANCH_PROF_LOG_ID"),
    read_env("BRANCH_LIC_LOG_ID"),
    read_env("GOOGLE_MAPS_API_KEY"),
)

s = session()
s.headers.update({"Authorization": f"Token {shared.token}"})

provision_branch(s, shared, branch_data)
