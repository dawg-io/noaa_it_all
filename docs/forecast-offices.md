# NWS Forecast Offices

**Weather** works with any NWS forecast office. Setup asks NWS which office covers your location and pre-selects it, so an inland location such as Las Vegas gets its own office (VEF), radar site and forecast discussion.

**Surf** comes from the 36 coastal offices that issue Surf Zone Forecasts. Every one gives rip current risk; water temperature needs a NOAA tide station and surf height an NDBC buoy:

| Office | Code | Water temperature | Surf height |
|---|---|---|---|
| Boston, MA | `BOX` | ✓ | ✓ |
| Brownsville, TX | `BRO` | ✓ | — |
| Caribou, ME | `CAR` | ✓ | — |
| Charleston, SC | `CHS` | ✓ | ✓ |
| Chicago, IL | `LOT` | — | — |
| Cleveland, OH | `CLE` | ✓ | — |
| Corpus Christi, TX | `CRP` | ✓ | ✓ |
| Detroit, MI | `DTX` | — | — |
| Duluth, MN | `DLH` | ✓ | — |
| Eureka, CA | `EKA` | ✓ | ✓ |
| Gaylord, MI | `APX` | — | — |
| Grand Rapids, MI | `GRR` | — | — |
| Green Bay, WI | `GRB` | ✓ | — |
| Guam | `GUM` | ✓ | — |
| Honolulu, HI | `HFO` | ✓ | ✓ |
| Jacksonville, FL | `JAX` | ✓ | ✓ |
| Los Angeles, CA | `LOX` | ✓ | ✓ |
| Marquette, MI | `MQT` | ✓ | — |
| Medford, OR | `MFR` | — | — |
| Melbourne, FL | `MLB` | ✓ | ✓ |
| Miami, FL | `MFL` | ✓ | ✓ |
| Milwaukee, WI | `MKX` | ✓ | — |
| Mobile, AL | `MOB` | ✓ | ✓ |
| New York, NY | `OKX` | ✓ | ✓ |
| Newport, NC | `MHX` | ✓ | ✓ |
| Norfolk, VA | `AKQ` | ✓ | ✓ |
| Northern Indiana | `IWX` | — | — |
| Philadelphia, PA | `PHI` | ✓ | — |
| Portland, ME | `GYX` | ✓ | ✓ |
| Portland, OR | `PQR` | ✓ | ✓ |
| San Diego, CA | `SGX` | ✓ | ✓ |
| San Francisco, CA | `MTR` | ✓ | ✓ |
| San Juan, PR | `SJU` | ✓ | ✓ |
| Tallahassee, FL | `TAE` | ✓ | ✓ |
| Tampa, FL | `TBW` | ✓ | ✓ |
| Wilmington, NC | `ILM` | ✓ | ✓ |

Brownsville has no surf height buoy: the one it shared with Corpus Christi was recovered and no other buoy nearby reports wave height. Some offices, such as the Great Lakes ones, only issue Surf Zone Forecasts in their summer season.

**Nearshore marine forecasts** come from the Great Lakes offices: Buffalo (BUF), Cleveland (CLE), Detroit (DTX), Duluth (DLH), Gaylord (APX), Grand Rapids (GRR), Green Bay (GRB), Marquette (MQT), Milwaukee (MKX), Chicago (LOT) and Northern Indiana (IWX).
