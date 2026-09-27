# Stretch: connecting the agents through our backend

Goal: the student stays on the line while we call the driver, then hears the real ETA.
Our backend (FastAPI on Vercel, `mvp/`) adds the "brain": it picks the **nearest driver by shortest road path** (the Dijkstra map we already built).

```
Student Desk agent ──API tool request_driver──▶ POST /api/samvaad/request_driver
                                                   1. pick nearest free driver (shortest path on campus map)
                                                   2. Sarvam Instant Outbound → Driver Caller agent calls that driver
                                                      (agent_variables: driver_name, student_name, pickup_place, drop_place)
                                                   ◀── returns {request_id, driver_name, road_eta_min}
Student Desk agent ──API tool get_driver_status──▶ POST /api/samvaad/driver_status {request_id}
                                                   long-polls up to 20 s for the driver call result
Driver call ends ──webhook (final_agent_variables)──▶ POST /api/samvaad/driver_webhook
                                                   stores {accepted, eta_minutes} for request_id
```

## Sarvam APIs used (from docs.sarvam.ai/conversations)
- **Instant outbound:** `POST https://apps.sarvam.ai/api/outbounds/v1/orgs/{org_id}/workspaces/{workspace_id}/outbounds`
  - header `X-API-Key: <Voice Agents API key>` (Settings → API Key)
  - body:
    ```json
    {
      "app_config": {
        "app_id": "<Driver Caller app id>", "app_version": 1,
        "connection_config": {"connection_id": "<telephony connection>", "agent_phone_number": "<your Sarvam number>"},
        "agent_variables": {"driver_name": "Ramesh", "student_name": "Priya", "pickup_place": "Opal Hostel", "drop_place": "Orion", "request_id": "R7"}
      },
      "user_config": {"user_phone_number": "+91XXXXXXXXXX"},
      "webhook_config": {"url": "https://<vercel-app>/api/samvaad/driver_webhook", "metadata": {"request_id": "R7"}}
    }
    ```
  - response: `{"attempt_id": "..."}`
- **Webhook payload** (sent to our URL when the call ends): `attempt_id`, `status`, `final_agent_variables` (includes `driver_accepted`, `driver_eta_minutes`, …), `interaction_transcript`, plus our `metadata`.
- org_id / workspace_id: copy them from the dashboard URL or from Settings. app_id / connection_id: from the agent's deployment and the phone-number screens.

## Student Desk API tools (configure in Build → Tools → API tool)
1. `request_driver`: POST `https://<vercel-app>/api/samvaad/request_driver`
   Body: `{"student_name": "@student_name", "pickup_place": "@pickup_place", "drop_place": "@drop_place"}`
   Save reply into variables: `request_id`, `driver_name`, `road_eta_min`. Timeout 10 s.
2. `get_driver_status`: POST `https://<vercel-app>/api/samvaad/driver_status`
   Body: `{"request_id": "@request_id"}`. Save reply into variables: `status` (calling|accepted|declined|no_answer), `driver_eta_minutes`. Timeout 25 s.

## Backend notes
- Vercel functions are stateless. Results from the webhook need a store: **Upstash Redis** (Vercel Marketplace, free tier), or read the attempt via Sarvam's analytics API (`/conversations/api/analytics/attempts`) using the attempt_id.
- The driver roster is `drivers.json` with name, phone, and current campus place. Nearest = shortest road distance from the driver's place to the pickup.
- Secrets in Vercel env vars: `SARVAM_AGENTS_API_KEY`, `SARVAM_ORG_ID`, `SARVAM_WORKSPACE_ID`, `DRIVER_APP_ID`, `DRIVER_APP_VERSION`, `SARVAM_CONNECTION_ID`, `SARVAM_AGENT_NUMBER`.
- Allowlist: if the endpoint is firewalled, Sarvam calls from IP `4.213.167.70`.
- The web dashboard can show the same requests live on the map (stretch of the stretch).
