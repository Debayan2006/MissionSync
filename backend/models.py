"""Validated public commands. Synthetic prototype; no provider credentials."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Role = Literal['viewer', 'analyst', 'commander', 'administrator']
Category = Literal['flood', 'fire', 'medical', 'infrastructure']
ResourceType = Literal['rescue', 'medical', 'fire', 'logistics']

class Command(BaseModel):
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=True)

class Coordinates(Command):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)

class Login(Command):
    role: Role

class IncidentCreate(Command):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(default='', max_length=4000)
    category: Category
    coordinates: Coordinates
    people_at_risk: int | None = Field(default=None, ge=0, le=1000000)
    damage_severity: float | None = Field(default=None, ge=0, le=10)
    response_time_minutes: float | None = Field(default=None, ge=0, le=1440)
    source_reliability: float = Field(default=.8, ge=0, le=1)

class IncidentPatch(Command):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=3, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    category: Category | None = None
    coordinates: Coordinates | None = None
    people_at_risk: int | None = Field(default=None, ge=0, le=1000000)
    damage_severity: float | None = Field(default=None, ge=0, le=10)
    response_time_minutes: float | None = Field(default=None, ge=0, le=1440)
    source_reliability: float | None = Field(default=None, ge=0, le=1)
    status: Literal['open', 'monitoring', 'resolved'] | None = None

    @model_validator(mode='after')
    def non_nullable(self):
        for key in ['title','description','category','coordinates','source_reliability','status']:
            if key in self.model_fields_set and getattr(self,key) is None:
                raise ValueError(f'{key} cannot be null')
        return self

class ResourceCreate(Command):
    name: str = Field(min_length=3, max_length=120)
    type: ResourceType
    coordinates: Coordinates
    capacity: int = Field(ge=1, le=10000)
    status: Literal['available', 'assigned', 'unavailable'] = 'available'
    estimated_response_time: float = Field(default=30, ge=0, le=1440)

class ResourcePatch(Command):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=3, max_length=120)
    type: ResourceType | None = None
    coordinates: Coordinates | None = None
    capacity: int | None = Field(default=None, ge=1, le=10000)
    status: Literal['available', 'assigned', 'unavailable'] | None = None
    estimated_response_time: float | None = Field(default=None, ge=0, le=1440)

    @model_validator(mode='after')
    def non_nullable(self):
        for key in self.model_fields_set:
            if getattr(self,key) is None:
                raise ValueError(f'{key} cannot be null')
        return self

class Analyze(Command):
    agent_id: Literal['vision', 'incident', 'weather', 'resource', 'risk', 'coordinator'] | None = None
    incident_id: str | None = None

class Generate(Command):
    incident_ids: list[str] | None = Field(default=None, max_length=100)

class Approve(Command):
    expected_version: int = Field(ge=1)
    alternative_id: str | None = None

class Reject(Command):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=1000)

class Revision(Command):
    expected_version: int = Field(ge=1)
    comment: str = Field(min_length=3, max_length=1000)

class Load(Command):
    confirmed: bool = False

class Reset(Command):
    scenario_id: str
    confirmed: bool = False

class Weather(Command):
    hazard_risk: float = Field(ge=0, le=1)
    access_blocked: bool
    expected_version: int | None = Field(default=None, ge=1)

class SimResource(Command):
    resource_id: str | None = None
    expected_version: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=3, max_length=120)
    type: ResourceType | None = None
    coordinates: Coordinates | None = None
    capacity: int | None = Field(default=None, ge=1, le=10000)
    status: Literal['available', 'assigned', 'unavailable'] | None = None
    estimated_response_time: float | None = Field(default=None, ge=0, le=1440)

    @model_validator(mode='after')
    def non_nullable(self):
        for key in self.model_fields_set:
            if getattr(self,key) is None:
                raise ValueError(f'{key} cannot be null')
        return self

class Weights(Command):
    people: float = Field(ge=0, le=1)
    damage: float = Field(ge=0, le=1)
    response: float = Field(ge=0, le=1)
    conflict: float = Field(ge=-1, le=0)
    friction: float = Field(ge=-1, le=0)

    @model_validator(mode='after')
    def useful(self):
        if self.people + self.damage + self.response == 0:
            raise ValueError('At least one positive priority weight is required')
        return self

class SettingsPatch(Command):
    expected_version: int = Field(ge=1)
    weights: Weights | None = None
    event_interval_seconds: int | None = Field(default=None, ge=5, le=300)

    @model_validator(mode='after')
    def non_nullable(self):
        for key in self.model_fields_set:
            if getattr(self,key) is None:
                raise ValueError(f'{key} cannot be null')
        return self

class Stress(Command):
    event_count: int = Field(default=20, ge=1, le=250)

class Empty(Command):
    pass
