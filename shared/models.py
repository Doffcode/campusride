"""
CampusRide canonical data models.

OWNER: orchestrator. READ-ONLY for all agents.
Import these models. NEVER copy, redefine, rename, or add fields.

    from shared.models import EV, Ride, Stop, State, BookingIntent, ...

Units:
    distance  -> meters (int)
    time      -> unix seconds (int)
    eta_min   -> whole minutes (int), always rounded UP (math.ceil)
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Global constants. Import these; never hardcode the numbers elsewhere.
# ---------------------------------------------------------------------------
EV_SPEED_M_PER_MIN = 250            # ~15 km/h
EV_SPEED_M_PER_S = EV_SPEED_M_PER_MIN / 60   # 4.1666...
EV_CAPACITY = 4                     # seats per EV
NO_SHOW_SECONDS = 120               # wait this long at a pickup, then no_show
TICK_SECONDS = 1.0                  # simulation step
DEFAULT_EV_STARTS = {               # ev_id -> starting node for the demo
    "ev_1": "main_gate",
    "ev_2": "hostel_b",
    "ev_3": "library",
}
SUPPORTED_LANGS = [                 # languages offered in the UI
    "en-IN", "hi-IN", "ta-IN", "te-IN", "kn-IN", "bn-IN", "mr-IN",
]

EVStatus = Literal["idle", "enroute", "waiting"]
StopKind = Literal["pickup", "drop"]
RideStatus = Literal[
    "pending",            # created, no EV assigned yet
    "assigned",           # EV assigned, driving to pickup
    "waiting_at_pickup",  # EV is at the pickup node, waiting for the student
    "picked",             # student is on board
    "done",               # dropped off
    "no_show",            # student did not come within NO_SHOW_SECONDS
    "cancelled",          # student cancelled
]
FINAL_RIDE_STATUSES = ("done", "no_show", "cancelled")


class Location(BaseModel):
    id: str            # "hostel_a"
    name: str          # "Hostel A"
    x: float           # map coordinates, only for drawing (viewBox 0 0 1000 800)
    y: float


class Stop(BaseModel):
    ride_id: str
    node: str          # Location.id
    kind: StopKind


class EV(BaseModel):
    id: str                                   # "ev_1"
    current_node: str                         # last node the EV was exactly at
    route: list[str] = Field(default_factory=list)
    # route = upcoming node ids in order, NOT including current_node.
    # route[0] is the node the EV is currently driving towards.
    progress: float = 0.0
    # 0.0..1.0 fraction of the edge current_node -> route[0] already driven.
    # Always 0.0 when route is empty or the EV is waiting.
    stops: list[Stop] = Field(default_factory=list)   # upcoming pickups/drops, in order
    seats_free: int = EV_CAPACITY
    # seats_free = EV_CAPACITY - (rides assigned to this EV that are
    #              "assigned", "waiting_at_pickup" or "picked")
    status: EVStatus = "idle"


class Ride(BaseModel):
    id: str                     # "ride_1", "ride_2", ... (counter starts at 1)
    student_name: str
    pickup: str                 # Location.id
    drop: str                   # Location.id
    lang: str                   # BCP-47, e.g. "hi-IN"
    status: RideStatus = "pending"
    ev_id: Optional[str] = None
    eta_min: Optional[int] = None
    # eta_min meaning depends on status:
    #   assigned            -> minutes until the EV reaches the pickup
    #   waiting_at_pickup   -> 0
    #   picked              -> minutes until the EV reaches the drop
    #   pending/done/no_show/cancelled -> None
    created_at: int
    arrived_at: Optional[int] = None   # when the EV reached the pickup (no-show timer)


class State(BaseModel):
    evs: list[EV]
    rides: list[Ride]
    server_time: int


class BookingIntent(BaseModel):
    pickup: Optional[str] = None      # Location.id, or None if not understood
    drop: Optional[str] = None
    confidence: float = 0.0           # 0..1
    needs_clarification: bool = True
    reply_text: str = ""              # in the user's language


class Assignment(BaseModel):
    """Return value of dispatch.assign(). Pure data, not stored anywhere."""
    ev_id: str
    stops: list[Stop]          # the EV's complete new stop list
    route: list[str]           # the EV's complete new route (from its current_node)
    eta_min: int               # minutes until this EV reaches the new ride's pickup
    cost_m: int                # the cost that won (meters), useful for debugging


# ---------------------------------------------------------------------------
# API request / response bodies
# ---------------------------------------------------------------------------
class RideRequest(BaseModel):
    student_name: str
    pickup: str
    drop: str
    lang: str = "en-IN"


class RideIdRequest(BaseModel):
    ride_id: str


class VoiceBookResponse(BaseModel):
    transcript: str                 # what Sarvam STT heard (shown in the UI)
    intent: BookingIntent
    ride: Optional[Ride] = None     # None when needs_clarification is true
    reply_audio_b64: str = ""       # base64 WAV from Sarvam TTS; "" if TTS failed


class ErrorResponse(BaseModel):
    error: str
