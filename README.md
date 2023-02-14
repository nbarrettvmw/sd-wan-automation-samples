# SD-WAN Automation Samples

This repository contains a few sample scripts to handle common SD-WAN provisioning scenarios.

---

## [Branch Provisioning](./branch-provisioning/)

This script is designed to provision branch edges which are using a standardized configuration set.

### Common Environment Variables

See [.example.env](./.example.env) for a template.
- VCO
- VCO API Token
- Enterprise Logical ID
- Branch Profile Logical ID
- Branch License Logical ID

### Per-Branch Inputs

These values are visible in [main.py](./branch-provisioning/main.py) at the end of the file.
The input data is represented using a Python [dataclass](https://docs.python.org/3/library/dataclasses.html).
Various input file formats could be converted into this format to use the tool (CSV, Pandas, etc.).

- Edge name
- Edge country and postal code
- Site contact name and email
- Transit network to be used for corporate clients
- Corporate subnets which are statically routed via the transit network
- BYOD and guest networks
- 2 ISPs with
    - Name
    - IP address details
    - Bandwidth

### Outputs

The branch will be provisioned as follows.

- HA enabled
- GE2 is the corporate transit, using VLAN 10 on the parent interface
- GE2.11 is the BYOD network subinterface, acting as the default gateway
- GE2.12 is the guest network subinterface, acting as the default gateway
- Static routes for the corporate networks are configured
- GE3 & GE4 are configured for the 2 ISPs

TODO: Add scripted override on GE3/GE4 for LOS detection & probeInterval to allow edits in VCO again.

---

