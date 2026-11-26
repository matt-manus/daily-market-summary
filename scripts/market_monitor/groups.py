"""
Draft: NASDAQ industry -> readable group (v0, 26/11/26, for the user's review).

The mapping is by *industry*, not by stock: any new listing that carries
one of these NASDAQ industries joins its group automatically. An industry
not listed here goes to "Unclassified" and is shown on the page as unmapped.
"""

GROUPS = {
    "Biotech – Drugs": [
        "Biotechnology: Pharmaceutical Preparations", "Medicinal Chemicals and Botanical Products",
        "Other Pharmaceuticals", "Pharmaceuticals and Biotechnology"],
    "Biotech – Biologics": [
        "Biotechnology: Biological Products (No Diagnostic Substances)"],
    "Diagnostics & Research Tools": [
        "Biotechnology: In Vitro & In Vivo Diagnostic Substances", "Biotechnology: Laboratory Analytical Instruments",
        "Biotechnology: Commercial Physical & Biological Resarch", "Misc Health and Biotechnology Services"],
    "Medical Devices": [
        "Medical/Dental Instruments", "Biotechnology: Electromedical & Electrotherapeutic Apparatus",
        "Ophthalmic Goods", "Medical Electronics", "Medical Specialities"],
    "Healthcare Services": [
        "Hospital/Nursing Management", "Medical/Nursing Services", "Retail-Drug Stores and Proprietary Stores"],
    "Software": [
        "Computer Software: Prepackaged Software", "Computer Software: Programming Data Processing",
        "Retail: Computer Software & Peripheral Equipment"],
    "IT Services": ["EDP Services"],
    "Semiconductors": ["Semiconductors", "Electronic Components", "Electronics Distribution"],
    "Hardware & Networking": [
        "Telecommunications Equipment", "Computer Communications Equipment", "Computer Manufacturing",
        "Computer peripheral equipment", "Radio And Television Broadcasting And Communications Equipment",
        "Precision Instruments", "Professional and commerical equipment"],
    "Electrical & Infrastructure": [
        "Electrical Products", "Engineering & Construction",
        "Water Sewer Pipeline Comm & Power Line Construction", "General Bldg Contractors - Nonresidential Bldgs"],
    "Industrial Machinery": [
        "Industrial Machinery/Components", "Metal Fabrications", "Industrial Specialties", "Fluid Controls",
        "Construction/Ag Equipment/Trucks", "Miscellaneous manufacturing industries", "Tools/Hardware",
        "Pollution Control Equipment", "Multi-Sector Companies", "Durable Goods"],
    "Aerospace & Defense": ["Aerospace", "Military/Government/Technical", "Ordnance And Accessories"],
    "Business Services": [
        "Business Services", "Diversified Commercial Services", "Professional Services",
        "Office Equipment/Supplies/Services", "Advertising", "Misc Corporate Leasing Services",
        "Rental/Leasing Companies", "Environmental Services"],
    "Shipping": ["Marine Transportation"],
    "Transport & Logistics": [
        "Air Freight/Delivery Services", "Trucking Freight/Courier Services", "Railroads",
        "Transportation Services", "Integrated Freight & Logistics"],
    "Autos": [
        "Auto Parts:O.E.M.", "Auto Manufacturing", "Motor Vehicles", "Automotive Aftermarket",
        "Retail-Auto Dealers and Gas Stations", "Auto & Home Supply Stores"],
    "Homebuilding & Building Products": [
        "Homebuilding", "RETAIL: Building Materials", "Building Materials", "Building Products"],
    "Home & Leisure Goods": [
        "Home Furnishings", "Consumer Electronics/Appliances", "Recreational Games/Products/Toys"],
    "Retail": [
        "Other Specialty Stores", "Department/Specialty Retail Stores", "Catalog/Specialty Distribution",
        "Clothing/Shoe/Accessory Stores", "Food Chains", "Consumer Electronics/Video Chains", "Books"],
    "Apparel & Footwear": ["Apparel", "Shoe Manufacturing", "Garments and Clothing", "Textiles"],
    "Restaurants": ["Restaurants"],
    "Travel & Leisure": ["Hotels/Resorts", "Services-Misc. Amusement & Recreation", "Other Consumer Services"],
    "Consumer Staples": [
        "Packaged Foods", "Beverages (Production/Distribution)", "Package Goods/Cosmetics", "Consumer Specialties",
        "Meat/Poultry/Fish", "Specialty Foods", "Food Distributors", "Farming/Seeds/Milling", "Tobacco",
        "Wholesale Distributors"],
    "Media": [
        "Broadcasting", "Cable & Other Pay Television Services", "Movies/Entertainment",
        "Newspapers/Magazines", "Publishing"],
    "Banks": ["Major Banks", "Commercial Banks", "Savings Institutions", "Banks"],
    "Insurance": ["Property-Casualty Insurers", "Life Insurance", "Specialty Insurers", "Accident &Health Insurance"],
    "Capital Markets": [
        "Investment Bankers/Brokers/Service", "Investment Managers", "Finance/Investors Services",
        "Diversified Financial Services", "Trusts Except Educational Religious and Charitable"],
    "Consumer Finance": ["Finance: Consumer Services", "Finance Companies"],
    "Real Estate": ["Real Estate Investment Trusts", "Real Estate", "Building operators"],
    "Oil & Gas": ["Oil & Gas Production", "Integrated oil Companies", "Oil/Gas Transmission", "Oil Refining/Marketing"],
    "Oil Services": ["Oilfield Services/Equipment", "Oil and Gas Field Machinery"],
    "Utilities & Power": ["Electric Utilities: Central", "Natural Gas Distribution", "Water Supply", "Power Generation"],
    "Precious Metals": ["Precious Metals"],
    "Metals & Mining": [
        "Metal Mining", "Steel/Iron Ore", "Aluminum", "Other Metals and Minerals",
        "Mining & Quarrying of Nonmetallic Minerals (No Fuels)", "Coal Mining"],
    "Chemicals & Materials": [
        "Major Chemicals", "Specialty Chemicals", "Agricultural Chemicals", "Paints/Coatings",
        "Plastic Products", "Containers/Packaging", "Paper", "Forest Products"],
    "Other": ["Blank Checks", "Miscellaneous"],
}


def _key(s):
    return " ".join(str(s).split()).lower()


GROUP_OF = {_key(ind): g for g, inds in GROUPS.items() for ind in inds}


def group_of(industry):
    """Group for a NASDAQ industry; None if unmapped (blank or new name)."""
    if industry is None or str(industry).strip() in ("", "Unclassified", "nan"):
        return None
    return GROUP_OF.get(_key(industry))
