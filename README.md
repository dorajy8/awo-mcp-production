# AWO MCP Server

MCP (Model Context Protocol) server that exposes processed AWO facility data to AI assistants like Claude Desktop.

## Overview

This MCP server provides a standardized interface between AI assistants and AWO organizational data. It enables natural language queries about AWO facilities, services, and statistics.

**Data Source:** The [civic-data.de](https://civic-data.de) federated directory (Turtle/RDF), loaded at startup. The data is not stored in this repository.

**Status:** ✅ Production-ready

---

## Architecture

```text
User
  │
Claude Desktop
  │
MCP Server (this repo)
  │
Processed AWO Data (CSV)
```

---

## Features

### Available Tools

| Tool                         | Description                        | Example                                   |
| ---------------------------- | ---------------------------------- | ----------------------------------------- |
| `count_facilities(city)`     | Count facilities in a city         | "How many AWO facilities are in Berlin?"  |
| `search_facilities(city)`    | List all facilities in a city      | "Show me all AWO facilities in Berlin"    |
| `get_facility_details(name)` | Get detailed info about a facility | "Tell me about AWO Sozialstation Wedding" |
| `search_services(query)`     | Search for services by keyword     | "Find addiction services"                 |
| `generate_statistics()`      | Get data statistics                | "Show me statistics about AWO facilities" |
| `check_completeness()`       | Check data quality                 | "Check data completeness for AWO records" |
| `detect_duplicates()`        | Find duplicate records             | "Are there duplicates in the AWO data?"   |
| `compare_facilities(f1, f2)` | Compare two facilities             | "Compare AWO Mitte and AWO Spree-Wuhle"   |
| `get_awo_details(iri)`       | Address, map link, opening hours   | "When is vista WIGWAM Connect open?"      |
| `find_nearby(location, ...)` | Facilities near a place, nearest first | "Addiction help within 1 km of 13353" |

`find_nearby` accepts `"latitude,longitude"`, a postal code, or part of a street name, plus optional `radius_km`, `query`, `accessible_only`, and `limit`.

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/awo-mcp-production.git
cd awo-mcp-production
```

### 2. Create and Activate Conda Environment

```bash
conda create -n awo-mcp python=3.11
conda activate awo-mcp
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure the Data Source

The server reads the federated directory's Turtle (`.ttl`) export. Set `AWO_DATA_SOURCE` to its URL or a local file path:

```bash
export AWO_DATA_SOURCE=https://example.org/path/to/directory.ttl
```

If `AWO_DATA_SOURCE` isn't set, the server looks for a local copy at `data/directory.ttl`. The `data/` folder is git-ignored, so local copies are never committed.

A directory of the older CSV exports (`einrichtungSchema.csv`, `adresseSchema.csv`, `angebotSchema.csv`, `traegerSchema.csv`) also works as a source, but the Turtle export is preferred: the CSVs lost leading zeros in phone numbers and contain empty rows.

---

## Running the Server

Start the MCP server:

```bash
python server.py
```

The server will start and wait for MCP requests. Leave this terminal running.

---

## Connecting to Claude Desktop

### Step 1: Install Claude Desktop

Download from [Claude Desktop](https://claude.ai/download).

> **Note:** No Claude subscription is required for MCP server integration.

### Step 2: Configure MCP Server

1. Open Claude Desktop.
2. Go to **Settings → Developer → Local MCP Servers → Edit Config**.
3. Add the following configuration:

```json
{
  "mcpServers": {
    "awo": {
      "command": "C:\\Users\\<YOUR_USERNAME>\\miniconda3\\envs\\awo-mcp\\python.exe",
      "args": [
        "D:\\path\\to\\awo-mcp-production\\server.py"
      ],
      "env": {
        "AWO_DATA_SOURCE": "https://example.org/path/to/directory.ttl"
      }
    }
  }
}
```

### Step 3: Restart Claude Desktop

Save the configuration and restart Claude Desktop completely.

The MCP server should appear under **Settings → Developer → Local MCP Servers** with a green status.

---

## Example Queries

Once connected, try asking Claude:

### Count Facilities

> "How many AWO facilities are in Berlin?"

### Search by City

> "Show me all AWO facilities in Berlin with their addresses"

### Get Facility Details

> "Tell me about AWO Sozialstation Wedding"

### Search Services

> "Find AWO services related to addiction counseling"

### Get Statistics

> "Show me statistics about AWO facilities"

### Data Quality

> "Check data completeness for AWO records"

### Find Duplicates

> "Are there any duplicates in the AWO datasets?"

### Compare Facilities

> "Compare AWO Mitte and AWO Spree-Wuhle"

### Find Nearby Facilities

> "Which wheelchair-accessible facilities are within 2 km of Leopoldplatz?"

---

## Facility Map

`docs/` contains a standalone web map (Leaflet + OpenStreetMap) with the same nearby search: search by postal code, street, or place name, use your location, or click the map; filter by group, keyword, and wheelchair access.

Click a pin or result to open its details: contact, opening hours, offers, accessibility, provider, directions, and a link to the source directory entry. Each facility has a shareable link (`#org-…`), and category names can be switched between English and German.

### View it locally

Generate `docs/facilities.json` from the data source (it is git-ignored):

```bash
python export_map_data.py
```

Then serve the folder:

```bash
python -m http.server 8765 --directory docs
```

Then open http://localhost:8765.

### Publish it with GitHub Pages

The workflow in `.github/workflows/pages.yml` fetches the directory, generates `facilities.json`, and publishes the map. It runs on every push to `main`, weekly, and on demand.

1. **Settings → Secrets and variables → Actions → Variables:** add `AWO_DATA_SOURCE` with the directory's public `.ttl` URL.
2. **Settings → Pages → Source:** choose **GitHub Actions**.

The map is then served at `https://<username>.github.io/awo-mcp-production/`.

Place names that aren't in the dataset are looked up with OpenStreetMap Nominatim, so those search terms are sent to OpenStreetMap.

---

## Data Overview

The loader builds four tables from the directory's RDF types:

| Table         | RDF type                  | Description             | Count |
| ------------- | ------------------------- | ----------------------- | ----- |
| `einrichtung` | `org:OrganizationalUnit`  | Facilities              | 166   |
| `adresse`     | `schema:PostalAddress`    | Addresses               | 108   |
| `angebot`     | `schema:Service`          | Services/offers         | 99    |
| `traeger`     | `schema:Organization`     | Providers               | 4     |

Counts are for the current Berlin export.

---

## File Structure

```text
awo-mcp-production/
├── .github/workflows/
│   └── pages.yml              # Builds and publishes the map
├── data/                      # Optional local copy of the data (git-ignored)
├── src/                       # Core modules
│   ├── data_loader.py         # Loads Turtle (or legacy CSV) into tables
│   └── data_repository.py
├── docs/                      # Web map (GitHub Pages)
│   ├── index.html
│   └── facilities.json        # Generated, git-ignored
├── export_map_data.py         # Exports map data from the data source
├── server.py                  # MCP server
├── requirements.txt
└── README.md
```

---

## Testing

### Test the Server

```bash
python -c "from server import mcp; print('✅ Server loaded successfully')"
```

### Run the Client (Optional)

If you have `client.py` for interactive testing:

```bash
python client.py
```

---

## Deployment

### Local Development

* Run `python server.py` directly.
* Connect Claude Desktop to the local server.

### Cloud Deployment

* Deploy to a cloud VM or container.
* Configure Claude Desktop to use a remote endpoint when supported.

---
## Demo with Claude Desktop

Here a video of the demo with Claude Desktop:

![AWO MCP Demo with Claude Desktop](assets/awo_mcp_claude_demo.gif)

## Troubleshooting

### Server Not Showing in Claude Desktop

* Check the JSON syntax in the configuration file.
* Make sure there are no trailing commas.
* Verify that the Python path exists.
* Check Claude logs at:

```text
%APPDATA%\Claude\logs\mcp*.log
```

### Server Fails to Start

* Ensure all dependencies are installed.
* Check that `AWO_DATA_SOURCE` points to a reachable `.ttl` URL or file, or that `data/directory.ttl` exists.
* Run the server manually to see any errors:

```bash
python server.py
```

---

## License

MIT License

---

## Contributing

1. Fork the repository.
2. Create a feature branch.
3. Commit your changes.
4. Push to the branch.
5. Open a Pull Request.

---
