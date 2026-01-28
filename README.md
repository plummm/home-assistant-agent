# Home Assistant Agent (Home Assistant integration)

Bridge Home Assistant to a locally running `ha_agent_core` service.

## Install via HACS (custom repo)
1. Open HACS → Integrations → overflow menu → Custom repositories.
2. Add this repository URL and select **Integration**.
3. Install **Home Assistant Agent** and restart Home Assistant.

## Manual install
Copy `custom_components/home_assistant_agent` into your Home Assistant `config/custom_components/home_assistant_agent` folder and restart.

## Configure
Settings → Devices & Services → Add Integration → **Home Assistant Agent**.

## Requirements
`ha_agent_core` must be running locally (default `http://localhost:3511`).
