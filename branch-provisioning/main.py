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


def generate_wan_overlay(wan_data: tuple[WanData, WanData]):
    val = {
        "links": [
            {
                "MTU": 1500,
                "addressingVersion": "IPv4",
                "backupOnly": wan.standby,
                "bwMeasurement": "USER_DEFINED",
                "classesOfService": {"classId": None, "classesOfService": []},
                "classesOfServiceEnabled": False,
                "customVlanId": False,
                "description": "",
                "discovery": "USER_DEFINED",
                "downstreamMbps": str(wan.mpbs_downstream),
                "dscpTag": "",
                "dynamicBwAdjustmentEnabled": False,
                "enable8021P": False,
                "encryptOverlay": True,
                "hotStandby": False,
                "internalId": str(uuid.uuid4()),
                "logicalId": str(uuid.uuid4()),
                "isp": "",
                "lastActive": "",
                "minActiveLinks": 1,
                "mode": "PUBLIC",
                "name": wan.name,
                "nextHopIpAddress": "",
                "overheadBytes": 0,
                "pmtudDisabled": False,
                "priority8021P": 0,
                "privateNetwork": None,
                "publicIpAddress": "",
                "sourceIpAddress": "",
                "staticSLA": {"jitterMs": "0", "latencyMs": "0", "lossPct": "0"},
                "staticSlaEnabled": False,
                "strictIpPrecedence": False,
                "type": "WIRED",
                "udpHolePunching": False,
                "upstreamMbps": str(wan.mpbs_upstream),
                "virtualIpAddress": "",
                "vlanId": 2,
            }
            for wan in wan_data
        ]
    }
    val["links"][0]["interfaces"] = ["GE3"]
    val["links"][1]["interfaces"] = ["GE4"]
    return val


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
                "gateway": str(branch.transit_net[2]),
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


def build_wan_patch(wan: WanData, interface_name: str, current_ds: dict) -> list[dict]:
    interface_index = next(
        (
            i
            for i, e in enumerate(current_ds["routedInterfaces"])
            if e["name"] == interface_name
        ),
        None,
    )

    if interface_index is None:
        raise ValueError(f"{interface_name} was not found in routedInterfaces")

    return [
        {
            "op": "add",
            "path": f"/routedInterfaces/{interface_index}/addressing/cidrIp",
            "value": str(wan.local),
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{interface_index}/addressing/cidrPrefix",
            "value": wan.network.prefixlen,
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{interface_index}/addressing/netmask",
            "value": str(wan.network.netmask),
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{interface_index}/addressing/gateway",
            "value": str(wan.gateway),
        },
        {
            "op": "replace",
            "path": f"/routedInterfaces/{interface_index}/l2/probeInterval",
            "value": "5",
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{interface_index}/l2/losDetection",
            "value": False,
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{interface_index}/override",
            "value": True,
        },
    ]


def build_ge2_patch(branch: BranchData, current_ds: dict) -> list[dict]:
    ge2_index = next(
        (i for i, e in enumerate(current_ds["routedInterfaces"]) if e["name"] == "GE2"),
        None,
    )
    ge2_11_index = 0
    ge2_12_index = 1

    if ge2_index is None:
        raise ValueError("GE2 was not found in routedInterfaces")

    return [
        {
            "op": "add",
            "path": f"/routedInterfaces/{ge2_index}/addressing/cidrIp",
            "value": str(branch.transit_net[1]),
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
            "op": "add",
            "path": f"/routedInterfaces/{ge2_index}/subinterfaces/{ge2_11_index}/addressing/cidrIp",
            "value": str(branch.byod_net[1]),
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{ge2_index}/subinterfaces/{ge2_11_index}/addressing/cidrPrefix",
            "value": branch.byod_net.prefixlen,
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{ge2_index}/subinterfaces/{ge2_11_index}/addressing/netmask",
            "value": str(branch.byod_net.netmask),
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{ge2_index}/subinterfaces/{ge2_12_index}/addressing/cidrIp",
            "value": str(branch.guest_net[1]),
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{ge2_index}/subinterfaces/{ge2_12_index}/addressing/cidrPrefix",
            "value": branch.guest_net.prefixlen,
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{ge2_index}/subinterfaces/{ge2_12_index}/addressing/netmask",
            "value": str(branch.guest_net.netmask),
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


# pre-provisioning of ZS is limited
# VCO will auto-populate some fields once the edge activates
# - refs/deviceSettings:css:site, refs/deviceSettings:zscaler:location
# - data/segments/0/css/sites (1 created per WAN), data/zscaler/deployment/location (only 1 created)
# - notably, data/zscaler/config is a bare template
# Once these configurations are populated, it will take the VCE 10-30 minutes for tunnels to establish
# - This is because ZScaler takes a long time to provision the VPN. You can see in the logs that IKE is failing.
# sub-locations may be added after activation is complete
# - ideally after the tunnels are up
# this is done using a single deviceSettings update
# - in data, /zscaler/deployment is un-touched
# - in data, /zscaler/config is modified to include
# - remove old css:site & zscaler:location refs, they must be re-created. VCO will do this.


def build_zscaler_data_patch(
    branch_data: BranchData, shared: CommonData, current_data: dict
) -> list[dict]:
    # TODO: pull sublocations from branch_data
    sublocations = [
        {
            "gwProperties": {
                "aupEnabled": False,
                "authRequired": True,
                "cautionEnabled": False,
                "dnBandwidth": 5000,
                "ipsControl": True,
                "ofwEnabled": True,
                "surrogateIP": False,
                "surrogateIPEnforcedForKnownBrowsers": False,
                "upBandwidth": 5000,
            },
            "includeAllLanInterfaces": True,
            "includeAllVlans": True,
            "internalId": "",
            "ipAddresses": ["10.0.0.0/30"],
            "ipAddressSelectionManual": True,
            "lanRoutedInterfaces": ["GE2"],
            "name": "CorpNets",
            "ruleId": "",
            "vlans": [],
        },
    ]
    return [
        {
            "op": "replace",
            "path": "/zscaler/config/cloud",
            "value": "zscalerthree.net",  # TODO: parameterize
        },
        {
            "op": "replace",
            "path": "/zscaler/config/enabled",
            "value": True,
        },
        {
            "op": "replace",
            "path": "/zscaler/config/provider",
            "value": {
                "logicalId": shared.zscaler_cloud_subscription_logical_id,
                "ref": "deviceSettings:zscaler:iaasSubscription",
            },
        },
        {
            "op": "replace",
            "path": "/zscaler/config/sublocations",
            "value": sublocations,
        },
    ]


def build_zscaler_refs_patch(branch_data: BranchData) -> list[dict]:
    return [
        {
            "op": "remove",
            "path": "/deviceSettings:css:site",
        },
        {
            "op": "remove",
            "path": "/deviceSettings:zscaler:location",
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
        ge3_patch = build_wan_patch(branch.wans[0], "GE3", edge_ds_data)
        ge4_patch = build_wan_patch(branch.wans[1], "GE4", edge_ds_data)
        ge2_patch = build_ge2_patch(branch, edge_ds_data)

        # zscaler cannot be done until edge is activated
        patch_set = jsonpatch.JsonPatch(
            [
                *static_routes_patch,
                *vlan_999_patch,
                *ge3_patch,
                *ge4_patch,
                *ge2_patch,
            ]
        )
        patch_set.apply(edge_ds_data, in_place=True)

        update_configuration_module(s, shared, edge_ds_id, edge_ds_data)

        edge_wan = extract_module(edge_specific_config["modules"], "WAN")
        if edge_wan is None:
            raise LookupError("could not find WAN module")
        edge_wan_id = edge_wan["id"]

        new_edge_wan_data = generate_wan_overlay(branch.wans)
        update_configuration_module(s, shared, edge_wan_id, new_edge_wan_data)

        quit_key = input(
            "pre-provisioning complete. press enter to continue to ZScaler provisioning, any other key to exit: "
        )
        if quit_key == "":
            print("Exiting")
            return

        print("ZScaler not implemented yet")
        return

        print("proceeding with ZScaler configuration...")

        # TODO: poll configuration stack repeatedly
        # wait for edge/modules/deviceSettings/data/segments/0/css to appear
        # this indicates that the VCO finished backend API to ZScaler
        # for now, just don't press enter unless the edge is activated and has the CSS provisioned

        edge_config_stack = get_configuration_stack(s, shared, edge_id)
        edge_specific_config = edge_config_stack[0]

        edge_ds = extract_module(edge_specific_config["modules"], "deviceSettings")
        if edge_ds is None:
            raise LookupError("could not find deviceSettings module")
        edge_ds_id = edge_ds["id"]

        edge_ds_data = edge_ds["data"]
        edge_ds_refs = edge_ds["refs"]

        data_patch_set = jsonpatch.JsonPatch(
            build_zscaler_data_patch(branch, shared, edge_ds_data)
        )
        refs_patch_set = jsonpatch.JsonPatch(build_zscaler_refs_patch(branch))
        data_patch_set.apply(edge_ds_data, in_place=True)
        refs_patch_set.apply(edge_ds_refs, in_place=True)

        update_configuration_module(s, shared, edge_ds_id, edge_ds_data, edge_ds_refs)

    finally:
        return


branch_data = BranchData(
    "test edge 778",
    "US",
    "62269",
    "Nick Barrett",
    "nbarrett@vmware.com",
    ipv4_network("10.0.0.4/30"),
    [ipv4_network("172.16.11.0/24")],
    ipv4_network("192.168.202.0/24"),
    ipv4_network("192.168.203.0/24"),
    (
        WanData(
            "ISP-A",
            ipv4_network("172.16.0.0/30"),
            ipv4_address("172.16.0.2"),
            ipv4_address("172.16.0.1"),
            50,
            50,
        ),
        WanData(
            "ISP-B",
            ipv4_network("192.168.12.0/24"),
            ipv4_address("192.168.12.240"),
            ipv4_address("192.168.12.1"),
            50,
            50,
        ),
    ),
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
    read_env("ZS_CLOUD_SUB_LOG_ID"),
    read_env("BRANCH_PROF_LOG_ID"),
    read_env("BRANCH_LIC_LOG_ID"),
    read_env("GOOGLE_MAPS_API_KEY"),
)

s = session()
s.headers.update({"Authorization": f"Token {shared.token}"})

provision_branch(s, shared, branch_data)
