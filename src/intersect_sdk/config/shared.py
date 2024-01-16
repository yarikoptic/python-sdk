"""
Configuration types shared across both Clients and Services.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

HIERARCHY_REGEX = r'^[a-z]((?!--)[a-z0-9-]){2,62}$'
"""
The hierarchy regex needs to be fairly restricted due to the number of different
systems we want to be compatible with. The rules:

- Only allow unreserved characters (alphanumeric and .-~_): https://datatracker.ietf.org/doc/html/rfc3986#section-2.3
- Require lowercase letters to avoid incompatibilities with case-insensitive systems.
- MinIO has been found to forbid _ and ~ characters
- MinIO requires an alphanumeric character at the start of the string
- No adjacent non-alphanumeric characters allowed
- Range should be from 3-63 characters

The following commit tracks several issues with MINIO: https://code.ornl.gov/intersect/additive-manufacturing/ros-intersect-adapter/-/commit/fa71b791be0ccf1a5884910b5be3b5239cf9896f
"""

ControlProvider = Literal['mqtt3.1.1', 'amqp0.9.1']


class HierarchyConfig(BaseModel):
    """
    Configuration for registring this service in a system-of-system architecture
    """

    service: str = Field(pattern=HIERARCHY_REGEX)
    """
    The name of this application - should be unique within an INTERSECT cluster
    """

    subsystem: Optional[str] = Field(default=None, pattern=HIERARCHY_REGEX)
    """
    An associated subsystem / service-grouping of the service
    """

    system: str = Field(pattern=HIERARCHY_REGEX)
    """
    Name of the "system", could also be thought of as a "device"
    """

    facility: str = Field(pattern=HIERARCHY_REGEX)
    """
    Name of the facility (an ORNL institutional designation, i.e. Neutrons) (NOT abbreviated)
    """

    organization: str = Field(pattern=HIERARCHY_REGEX)
    """
    Name of the organization (i.e. ORNL) (NOT abbreviated)
    """

    def hierarchy_string(self, join_str: str = '') -> str:
        """
        return the full hierarchy string, joined together by join_str
        """
        if not self.subsystem:
            return join_str.join([self.organization, self.facility, self.system, '-', self.service])
        return join_str.join(
            [
                self.organization,
                self.facility,
                self.system,
                self.subsystem,
                self.service,
            ]
        )

    # we need to use the Python regex engine instead of the Rust regex engine here, because Rust's does not support lookaheads
    model_config = ConfigDict(regex_engine='python-re')


class ControlPlaneConfig(BaseModel):
    """
    Configuration for interacting with a broker
    """

    username: str = Field(min_length=1)
    """
    Username credentials for broker connection.
    """

    password: str = Field(min_length=1)
    """
    Password credentials for broker connection.
    """

    host: str = Field(default='127.0.0.1', min_length=1)
    """
    Broker hostname (default: 127.0.0.1)
    """

    port: Optional[PositiveInt] = Field(None)
    """
    Broker port. List of common ports:

    - 1883 (MQTT)
    - 4222 (NATS default port)
    - 5222 (XMPP)
    - 5223 (XMPP over TLS)
    - 5671 (AMQP over TLS)
    - 5672 (AMQP)
    - 7400 (DDS Discovery)
    - 7401 (DDS User traffic)
    - 8883 (MQTT over TLS)
    - 61613 (RabbitMQ STOMP - WARNING: ephemeral port)

    NOTE: INTERSECT currently only supports AMQP and MQTT.
    """

    protocol: ControlProvider = ...
    """
    The protocol of the broker you'd like to use (i.e. AMQP, MQTT...)
    """
    # TODO - support more protocols and protocol versions as needed - see https://www.asyncapi.com/docs/reference/specification/v2.6.0#serverObject


class DataStoreConfig(BaseModel):
    """
    Configuration for interacting with a data store.
    """

    username: str = Field(min_length=1)
    """
    Username credentials for data store connection.
    """

    password: str = Field(min_length=1)
    """
    Password credentials for data store connection.
    """

    host: str = Field(default='127.0.0.1', min_length=1)
    """
    Data store hostname (default: 127.0.0.1)
    """

    port: Optional[PositiveInt] = Field(None)
    """
    Data store port
    """


class DataStoreConfigMap(BaseModel):
    """
    Configurations for any data stores the application should talk to
    """

    minio: List[DataStoreConfig] = Field(..., min_length=1)
    """
    minio configurations
    """