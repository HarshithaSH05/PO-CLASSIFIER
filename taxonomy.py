
TAXONOMY = """
L1 | L2 | L3
---|---|---
Banking & Financial | Banking Charges |
Banking & Financial | Global Rating |
Banking & Financial | Insurance |
Facilities | Food Services |
Facilities | Janitorial Services |
Facilities | Security Services |
Facilities | Uniform |
HR | Employee Benefits |
HR | Employee Recognition |
HR | Recruitment Services |
HR | Training |
IT | Hardware | Accessories
IT | Hardware | Laptop
IT | Hardware | Mobile
IT | Software | Licenses Cost
IT | Software | Subscription
Professional Services | Audit Services |
Professional Services | Consulting Services |
Professional Services | Legal Services |
Professional Services | Risk Consulting Services |
T&E | Air |
T&E | Food |
T&E | GROUND TRANSPORTATION |
T&E | Hotel |
T&E | Parking fees |
Unaddressable | Tax |
Utilities | Power |
Utilities | Water |
"""


def get_taxonomy_set() -> set[str]:
    entries = set()
    for row in get_taxonomy_rows():
        entries.add(f"{row['L1']}|{row['L2']}|{row['L3']}")
    return entries


def get_taxonomy_rows() -> list[dict[str, str]]:
    rows = []
    for line in TAXONOMY.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("L1 ") or line.startswith("---"):
            continue
        parts = [part.strip() for part in line.split("|")]
        while len(parts) < 3:
            parts.append("")
        l1, l2, l3 = parts[0], parts[1], parts[2]
        rows.append({"L1": l1, "L2": l2, "L3": l3})
    return rows
