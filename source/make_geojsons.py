import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString
import yaml
from shapely.geometry import Point
from common_tools import get_top_dir, ensure_directory_exists
import boto3
from io import BytesIO

top_dir = get_top_dir()

def load_bev_data(csv_path):
    """Load and parse the BEV simulation CSV."""
    df = pd.read_csv(csv_path)
    df[['longitude', 'latitude']] = df['Location'].str.split(',', expand=True).astype(float)
    df['Time'] = pd.to_datetime(df['Time'])
    df = df.sort_values(by=['Vehicle ID', 'Time'])
    return df
    
def load_states_geojson_from_s3(bucket_name, key):
    """
    Load state-level emissions GeoJSON from S3 and return it as a GeoDataFrame,
    forcibly overriding the incorrect CRS.
    """
    s3 = boto3.client('s3')
    response = s3.get_object(Bucket=bucket_name, Key=key)
    geojson_bytes = response['Body'].read()

    # Read file (likely wrongly declares EPSG:4326)
    gdf = gpd.read_file(BytesIO(geojson_bytes))

    # Forcefully override CRS to EPSG:3857
    gdf.set_crs(epsg=3857, inplace=True, allow_override=True)

    print("Loaded states GeoJSON CRS:", gdf.crs)
    return gdf


def build_segments(df):
    """Build LineString segments with attributes and cumulative metrics from BEV simulation data."""
    segments = []

    grouped = df.groupby('Vehicle ID')

    for vehicle_id, group in grouped:
        group = group.reset_index(drop=True)

        # Initialize cumulative sums
        cum_energy = 0.0
        cum_distance = 0.0
        cum_driving_time = 0.0

        for i in range(1, len(group)):
            prev = group.iloc[i - 1]
            curr = group.iloc[i]

            # Only build a segment if locations are distinct
            if (prev['longitude'], prev['latitude']) != (curr['longitude'], curr['latitude']):
                # Update cumulative totals
                cum_energy += curr['Energy Consumed']
                cum_distance += curr['Distance']
                cum_driving_time += curr['Driving Time']

                segment = {
                    'geometry': LineString([
                        (prev['longitude'], prev['latitude']),
                        (curr['longitude'], curr['latitude'])
                    ]),
                    'Vehicle ID': vehicle_id,
                    'Date': curr['Date'],
                    'Start Time': prev['Time'],
                    'End Time': curr['Time'],
                    'Energy Level': curr['Energy Level'],
                    'Energy Consumed': curr['Energy Consumed'],
                    'Distance': curr['Distance'],
                    'Driving Time': curr['Driving Time'],
                    'Idle Time': curr['Idle Time'],
                    'Parking Time': curr['Parking Time'],
                    'Cumulative Energy Consumed': cum_energy,
                    'Cumulative Driving Time': cum_driving_time,
                    'Cumulative Distance': cum_distance
                }
                segments.append(segment)

    # Create GeoDataFrame in lat/lon degrees (WGS84), then convert to meters (Web Mercator)
    segments_gdf = gpd.GeoDataFrame(segments, crs="EPSG:4326")
    return segments_gdf.to_crs("EPSG:3857")


def save_segments(segments_gdf, output_path):
    """Save segments as GeoJSON."""
    segments_gdf.to_file(output_path, driver='GeoJSON')
    
def extract_charger_points(config_path):
    """Load charger locations from base_config.yaml and return as GeoDataFrame."""
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    charger_data = config.get('chargers', {}).get('locations', [])
    features = []

    for charger in charger_data:
        features.append({
            'geometry': Point(charger['lon'], charger['lat']),
            'charging_power': charger['charging_power'],
            'voltage': charger['voltage'],
            'id': charger['id']
        })

    return gpd.GeoDataFrame(features, crs="EPSG:3857")

def write_simulation_summary(config_path, output_txt_path):
    """Generate a human-readable summary of simulation settings and save to a text file."""
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    lines = []

    # --- ROUTES ---
    routes = config.get('routes', {})
    lines.append("=== ROUTES ===")

    assignments = routes.get('vehicle_assignments', {})
    for route_name, vehicles in assignments.items():
        lines.append(f"Route '{route_name}':")
        for v in vehicles:
            lines.append(f"  - Count: {v.get('count')}, Daily Miles: {v.get('daily_miles')}")

    waypoints = routes.get('waypoints', [])
    lines.append(f"Waypoints: {len(waypoints)} defined")

    # --- SIMULATION ---
    simulation = config.get('simulation', {})
    lines.append("\n=== SIMULATION SETTINGS ===")
    lines.append(f"Mode: {simulation.get('mode', 'N/A')}")
    lines.append(f"Start Date: {simulation.get('start_date', 'N/A')}")
    lines.append(f"Number of Days: {simulation.get('num_days', 'N/A')}")
    lines.append(f"Use Current Date: {simulation.get('use_current_date', False)}")
    routes_to_simulate = simulation.get('routes_to_simulate', [])
    lines.append(f"Routes to Simulate: {', '.join(routes_to_simulate)}")

    # --- VEHICLES ---
    vehicle_types = config.get('vehicle_types', {})
    lines.append("\n=== VEHICLE TYPES ===")
    for props in vehicle_types.values():
        meta = props.get('metadata', {})
        lines.append(f"- {meta.get('make', 'Unknown')} {meta.get('model', '')} ({meta.get('year', '')}):")
        lines.append(f"  Battery Capacity: {props.get('battery_capacity')} kWh")
        lines.append(f"  Max Range: {props.get('max_range')} miles")
        lines.append(f"  Voltage: {props.get('voltage')} V")
        lines.append(f"  Payload: {props.get('payload')} kg")
        lines.append(f"  Drag Coeff.: {props.get('drag_coefficient')}, Rolling Resistance: {props.get('rolling_resistance')}")
        lines.append(f"  Frontal Area: {props.get('frontal_area')} m^2, HVAC Power: {props.get('hvac_power')} kW")

    # Write to file
    with open(output_txt_path, 'w') as out:
        out.write('\n'.join(lines))

def add_emission_intensity_to_segments(segments_gdf, states_gdf):
    """Assign CO2_rate to each LineString based on which state its centroid falls within."""
    # Convert segments to projected CRS (Web Mercator)
    segments_proj = segments_gdf.to_crs("EPSG:3857")
    segments_proj['centroid'] = segments_proj.geometry.centroid

    # Build centroid GeoDataFrame
    centroids_gdf = gpd.GeoDataFrame(
        segments_proj.drop(columns='geometry'),
        geometry='centroid',
        crs="EPSG:3857"
    )

    # Spatial join (may produce >1 match per centroid)
    joined = gpd.sjoin(
        centroids_gdf,
        states_gdf[['geometry', 'CO2_rate']],
        how='left',
        predicate='within'
    )

    # Remove duplicate matches: keep only first match for each segment
    joined_unique = joined[~joined.index.duplicated(keep='first')]

    # Confirm match count
    if len(joined_unique) != len(segments_gdf):
        print(f"⚠️  Warning: CO2_rate assigned to {len(joined_unique)} of {len(segments_gdf)} segments")

    # Assign CO2_rate back to segments_gdf
    segments_gdf['CO2_rate'] = joined_unique['CO2_rate'].reindex(segments_gdf.index).values

    return segments_gdf



def main():
    routes = ["I-80", "I-95"]
    
    for route in routes:
        base_path = f"{top_dir}/encode_artifacts/{route}"
        csv_path = f"{base_path}/bev_simulation.csv"
        config_path = f"{base_path}/base_config.yaml"
        ensure_directory_exists(f"{top_dir}/encode_artifacts/geojsons")
        output_segments_geojson = f"{top_dir}/encode_artifacts/geojsons/{route}_route_segments.geojson"
        output_chargers_geojson = f"{top_dir}/encode_artifacts/geojsons/{route}_chargers.geojson"

        print("Loading BEV simulation data...")
        df = load_bev_data(csv_path)

        print("Building route segments...")
        segments_gdf = build_segments(df)
        
        print("Loading state-level emissions data from S3...")
        bucket = "mcsc-datahub-public"
        key = "geojsons_simplified/grid_emission_intensity/eia2022_state_merged.geojson"
        states_gdf = load_states_geojson_from_s3(bucket, key)

        print("Assigning emission intensities by state...")
        segments_gdf = add_emission_intensity_to_segments(segments_gdf, states_gdf)

        print(f"Saving segments to {output_segments_geojson}...")
        save_segments(segments_gdf, output_segments_geojson)
        print("Done.")
#
#        print("Extracting charger locations...")
#        charger_gdf = extract_charger_points(config_path)
#        print(f"Saving chargers to {output_chargers_geojson}...")
#        save_segments(charger_gdf, output_chargers_geojson)
#
#        output_summary_txt = f"{top_dir}/encode_artifacts/geojsons/{route}_simulation_summary.txt"
#        print(f"Writing simulation summary to {output_summary_txt}...")
#        write_simulation_summary(config_path, output_summary_txt)


if __name__ == '__main__':
    main()
