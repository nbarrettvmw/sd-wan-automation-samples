from ipaddress import IPv4Address, IPv4Network, ip_address, ip_network
from typing import Optional, cast
import requests

from models import LatLon


def calculate_lat_lon(gmaps_api_key: str, postal_code: str, country: str) -> LatLon:
    resp = requests.get(
        f'https://maps.googleapis.com/maps/api/geocode/json?address={postal_code},{country}&key={gmaps_api_key}').json()

    first_location = resp['results'][0]['geometry']['location']
    return LatLon(first_location['lat'], first_location['lng'])


def ipv4_network(net: str) -> IPv4Network:
    return cast(IPv4Network, ip_network(net))


def ipv4_address(addr: str) -> IPv4Address:
    return cast(IPv4Address, ip_address(addr))


def extract_module(module_stack: list[dict], module_name: str) -> Optional[dict]:
    return next((m for m in module_stack if m["name"] == module_name), None)