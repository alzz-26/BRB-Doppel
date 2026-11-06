import os

import httpx
from dotenv import set_key

# Importing register also loads .env. Its main block won't run.
from register import ENV_PATH, register_agent

base_url = os.environ["SWITCH_URL"]
setup_id = os.environ.get("SETUP_AGENT_ID")
setup_key = os.environ.get("SETUP_API_KEY")

if not setup_id:
    # Same bootstrap key, so this helper has the same owner as BRB.
    helper = register_agent(
        base_url,
        os.environ["SWITCH_REGISTRATION_KEY"],
        name="brb.setup",
        description="One-off helper that sets BRB's addressing.",
    )
    setup_id, setup_key = helper["id"], helper["api_key"]
    set_key(ENV_PATH, "SETUP_AGENT_ID", setup_id)
    set_key(ENV_PATH, "SETUP_API_KEY", setup_key)

response = httpx.post(
    f"{base_url}/agents/{setup_id}/ops/update_agent_detail",
    headers={"Authorization": f"Bearer {setup_key}"},
    json={"agent_id": os.environ["BRB_AGENT_ID"], "addressing": "anyone"},
    timeout=30,
)
print(response.status_code)
if response.is_error:
    print(response.text)