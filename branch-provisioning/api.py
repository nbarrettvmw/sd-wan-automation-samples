from requests import Session
import json

from models import EdgeLicense, CommonData


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


def get_async(s: Session, shared: CommonData, async_token: str):
    return do_portal(
        s,
        shared,
        "async/getStatus",
        {
            "apiToken": async_token,
        },
    )


def get_enterprise_edges_v1(s: Session, shared: CommonData) -> list[dict]:
    return do_portal(s, shared, "enterprise/getEnterpriseEdges", {})


def find_edge(s: Session, shared: CommonData, edge_logical_id: str):
    edges = get_enterprise_edges_v1(s, shared)
    return next((e for e in edges if e["logicalId"] == edge_logical_id), None)


def get_configuration_stack(s: Session, shared: CommonData, edge_id: int) -> list[dict]:
    return do_portal(
        s, shared, "edge/getEdgeConfigurationStack", params={"edgeId": edge_id}
    )


def update_configuration_module(
    s: Session,
    shared: CommonData,
    configuration_module_id: int,
    new_data: dict,
    new_refs: dict | None = None,
):
    update = {"data": new_data}
    if new_refs is not None:
        update["refs"] = new_refs

    do_portal(
        s,
        shared,
        "configuration/updateConfigurationModule",
        params={
            "id": configuration_module_id,
            "_update": update,
        },
    )


def get_licenses_v1(s: Session, shared: CommonData) -> list[EdgeLicense]:
    resp = do_portal(s, shared, "license/getEnterpriseEdgeLicenses", {})
    licenses = []
    for lic in resp:
        licenses.append(
            EdgeLicense(
                lic["id"],
                lic["logicalId"],
                lic["name"],
                lic["bandwidthTier"],
                lic["edition"],
                lic["termMonths"],
            )
        )
    return licenses


def get_edges(s: Session, shared: CommonData, next_page_token: str | None = None):
    params = f"?nextPageLink={next_page_token}" if next_page_token is not None else ""

    return s.get(
        f"https://{shared.vco}/api/sdwan/v2/enterprises/{shared.enterprise_logical_id}/edges{params}"
    ).json()


def post_edge(
    s: Session,
    shared: CommonData,
    model_name: str,
    profile_logical_id: str,
    extras: dict,
):
    post_edge_resp = s.post(
        f"https://{shared.vco}/api/sdwan/v2/enterprises/{shared.enterprise_logical_id}/edges",
        json={
            "modelNumber": model_name,
            "profile": profile_logical_id,
            **extras,
        },
    )

    post_edge_resp_json = post_edge_resp.json()

    return post_edge_resp_json
