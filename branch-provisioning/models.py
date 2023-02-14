from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network


@dataclass
class LatLon:
    lat: float
    lon: float


@dataclass
class CommonData:
    vco: str
    token: str
    enterprise_logical_id: str
    branch_profile_logical_id: str
    branch_license_logical_id: str
    google_maps_api_key: str

    def validate(self):
        assert self.vco is not None
        assert self.token is not None
        assert self.enterprise_logical_id is not None
        assert self.branch_profile_logical_id is not None
        assert self.branch_license_logical_id is not None
        assert self.google_maps_api_key is not None


@dataclass
class WanData:
    name: str
    network: IPv4Network
    local: IPv4Address
    gateway: IPv4Address
    mpbs_upstream: float
    mpbs_downstream: float
    standby: bool = False


@dataclass
class BranchData:
    name: str
    country: str
    postal_code: str
    contact_name: str
    contact_email: str
    transit_net: IPv4Network
    corporate_nets: list[IPv4Network]
    byod_net: IPv4Network
    guest_net: IPv4Network
    wans: tuple[WanData, WanData]


@dataclass
class EdgeLicense:
    id: int
    logical_id: str
    name: str
    bandwidth_tier: str
    edition: str
    term_months: int
