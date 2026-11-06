import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv, set_key

# The .env file sits one folder above this script.
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)


def register_agent(
    base_url: str,
    registration_key: str,
    name: str = "brb",
    description: str = "Runs the BRB quiz, meeting checks and ledger.",
) -> dict:
    """Create the BRB agent and return its id and api_key."""
    response = httpx.post(
        f"{base_url}/agents",
        headers={"Authorization": f"Bearer {registration_key}"},
        json={
            "name": name,
            "description": description,
            "connector_type": "brb",
            "integration_profile": {
                "connection_model": "always_on",
                "message_exchange": True,
                "pre_invocation_mediation": [],
                "post_invocation_mediation": [],
                "event_reporting": [],
            },
        },
        timeout=30,
    )
    if response.is_error:
        print(response.status_code, response.text)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    # Stop early: registering twice would fail with a 409.
    if os.environ.get("BRB_API_KEY"):
        sys.exit("BRB is already registered.")

    agent = register_agent(
        os.environ["SWITCH_URL"],
        os.environ["SWITCH_REGISTRATION_KEY"],
    )

    # The api_key is shown only once, so save it straight away.
    set_key(ENV_PATH, "BRB_AGENT_ID", agent["id"])
    set_key(ENV_PATH, "BRB_API_KEY", agent["api_key"])
    print(f"Registered BRB with id {agent['id']}")