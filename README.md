# Geo-TIDE Inputs from Encode Artifacts

This code transforms output artifacts from Encode Energy's BEV (Battery Electric Vehicle) route simulations into geospatial formats compatible with [Geo-TIDE](https://climate.mit.edu/geo-tide), an interactive platform for freight decarbonization planning. It produces enriched GeoJSON layers that include segmented routes, charger locations, and state-level emission intensities.

---

## Features

- Parses BEV simulation CSV outputs from Encode Energy
- Segments vehicle routes into discrete LineStrings with cumulative metrics
- Annotates segments with state-level electricity emission intensities (e.g., CO₂ rate in g/kWh)
- Extracts charger locations from route configuration files
- Outputs:
  - Route segments GeoJSON
  - Charger points GeoJSON
  - Human-readable simulation summaries (TXT)

---

## Input Files

Each route must reside in its own folder under `encode_artifacts/{ROUTE_NAME}/`, and include:

- `bev_simulation.csv` – the route-level BEV simulation output
- `base_config.yaml` – simulation configuration with charger locations, vehicle types, and routing metadata

---

## Installation

Clone the repository and install required packages:

```bash
git clone git@github.com:mcsc-impact-climate/encode_geotide.git
cd encode-geotide
pip install -r requirements.txt
```

---

## Usage 

```python
python source/make_geojsons.py
```

Outputs will be written to:

```bash
encode_artifacts/geojsons/
  ├── I-80_route_segments.geojson
  ├── I-80_chargers.geojson
  ├── I-80_simulation_summary.txt
  └── ...
```

## Emissions Data Source

State-level electricity emissions are loaded from a public S3 bucket:

```bash
s3://mcsc-datahub-public/geojsons_simplified/grid_emission_intensity/eia2022_state_merged.geojson
```

This dataset contains 2022 CO₂ intensity values from the EIA (in lb/MWh) for each U.S. state.
