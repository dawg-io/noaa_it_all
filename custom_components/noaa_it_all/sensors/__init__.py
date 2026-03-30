"""Sensor sub-modules for NOAA Integration.

Each data domain lives in its own module so that sensor.py stays small
and each file remains well under 1 000 lines.
"""

from .space_weather import (  # noqa: F401
    GeomagneticSensor,
    GeomagneticSensorInterpretation,
    PlanetaryKIndexSensor,
    PlanetaryKIndexSensorRating,
    AuroraNextTimeSensor,
    AuroraDurationSensor,
    AuroraVisibilityProbabilitySensor,
    SolarRadiationStormAlertsSensor,
)
from .hurricanes import (  # noqa: F401
    HurricaneAlertsSensor,
    HurricaneActivitySensor,
)
from .surf import (  # noqa: F401
    RipCurrentRiskSensor,
    SurfHeightSensor,
    WaterTemperatureSensor,
)
from .weather_observations import (  # noqa: F401
    WeatherObservationSensor,
    TemperatureSensor,
    HumiditySensor,
    WindSpeedSensor,
    WindDirectionSensor,
    BarometricPressureSensor,
    DewpointSensor,
    VisibilitySensor,
    SkyConditionsSensor,
    FeelsLikeSensor,
)
from .forecasts import (  # noqa: F401
    ForecastBaseSensor,
    ExtendedForecastSensor,
    HourlyForecastSensor,
)
from .alerts import NWSAlertsSensor  # noqa: F401
from .weather_extra import (  # noqa: F401
    CloudCoverSensor,
    RadarTimestampSensor,
    ForecastDiscussionSensor,
)
