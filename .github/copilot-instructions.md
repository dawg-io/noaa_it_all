# NOAA Integration for Home Assistant

NOAA Integration is a Home Assistant custom component that provides NOAA solar and geomagnetic data through sensors and images. This is a HACS (Home Assistant Community Store) integration that fetches real-time data from NOAA Space Weather Prediction Center APIs.

**ALWAYS reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.**

## Working Effectively

### Prerequisites and Environment Setup
- Install Python 3.8+ (tested with Python 3.12.3):
  - `python3 --version` to verify installation
- Install required dependencies:
  - `pip install requests aiohttp` -- takes 10-15 seconds. Required for all testing.
  - `pip install flake8` -- takes 5-10 seconds. Required for code quality validation.

### Code Validation and Quality
- **ALWAYS validate Python syntax before making changes**:
  - `python3 -m py_compile custom_components/noaa_it_all/__init__.py custom_components/noaa_it_all/sensor.py custom_components/noaa_it_all/image.py` -- takes <1 second
- **ALWAYS run code linting before committing**:
  - `flake8 custom_components/noaa_it_all/ --max-line-length=120` -- takes <5 seconds
  - Fix all linting issues before proceeding. Common issues: blank line spacing (E302), line length (E501), unused imports (F401)
- **NEVER commit code with linting errors** - the HACS validation will fail

### HACS Validation
- **CRITICAL**: The main validation is through HACS workflow in `.github/workflows/hacs-validate.yml`
- Run validation manually: Workflow is triggered via `workflow_dispatch` (manual trigger)
- **TIMING**: HACS validation typically takes 2-5 minutes in CI. NEVER CANCEL.
- All changes must pass HACS validation to be accepted

### Comprehensive Validation (Recommended)
For thorough validation of your changes, run all essential checks:
```bash
# Essential validation sequence (takes <30 seconds total)
python3 --version                                                    # Verify Python
python3 -m py_compile custom_components/noaa_it_all/*.py         # Syntax check
flake8 custom_components/noaa_it_all/ --max-line-length=120     # Code quality
python3 -c "import json; print('Valid:', json.load(open('custom_components/noaa_it_all/manifest.json'))['domain'])"  # JSON validation
```
**CRITICAL**: Fix ALL flake8 issues before committing - zero tolerance for linting errors.

### Testing External APIs (Manual Validation)
**IMPORTANT**: This integration fetches live data from NOAA APIs. When possible, test connectivity:
- Test geomagnetic storm data: `curl -s --connect-timeout 30 --max-time 30 "https://services.swpc.noaa.gov/json/geospace/geospace_dst_1_hour.json"`
- Test planetary K-index data: `curl -s --connect-timeout 30 --max-time 30 "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"`
- Test geoelectric field image: `curl -s -I --connect-timeout 30 --max-time 30 "https://services.swpc.noaa.gov/images/animations/geoelectric/InterMagEarthScope/EmapGraphics_1m/latest.png"`
- Test aurora forecast image: `curl -s -I --connect-timeout 30 --max-time 30 "https://services.swpc.noaa.gov/experimental/images/aurora_dashboard/tonights_static_viewline_forecast.png"`
- **LIMITATION**: These APIs are often not accessible from sandboxed/restricted environments
- **Alternative**: Validate API handling code through syntax and import checks instead

## Validation Scenarios

**CRITICAL**: Since this is a Home Assistant custom component, full end-to-end testing requires a Home Assistant installation. However, you MUST validate these scenarios:

### Basic Component Validation
1. **Syntax validation**: Ensure all Python files compile without errors
2. **Import validation**: Verify all required dependencies can be imported
3. **JSON validation**: Ensure `manifest.json` is valid JSON with correct structure
4. **Code quality**: All linting issues resolved

### Integration Testing (Requires Home Assistant)
**When making changes that affect functionality, always test**:
1. Component loads without errors in Home Assistant
2. Sensors populate with valid data from NOAA APIs
3. Image entities display current geoelectric field and aurora forecast images
4. Entity updates occur according to the 5-minute scan interval
5. Error handling works properly when APIs are unavailable

## Repository Structure and Navigation

### Key Files and Locations
```
/custom_components/noaa_it_all/
├── __init__.py          # Component setup and platform forwarding
├── manifest.json        # Component metadata, dependencies, version
├── config_flow.py       # UI config flow (config_flow: true in the manifest)
├── const.py             # Constants, API endpoints, defaults
├── coordinator.py       # DataUpdateCoordinator: fetches and caches NOAA data
├── parsers.py           # Parsing helpers for NOAA API and text-product responses
├── astro.py             # Positional astronomy (stdlib only, no HA imports, no network)
├── meteor.py            # Meteor shower rate/score model (stdlib only, no HA imports)
├── meteor_catalog.py    # Bundled shower catalog, keyed by solar longitude
├── entity_naming.py     # Shared entity naming helpers
├── sensor.py            # Sensor platform
├── binary_sensor.py     # Binary sensor platform
├── image.py             # Image platform: geoelectric field and aurora forecast images
├── weather.py           # Weather platform
├── strings.json         # UI strings for the config flow
├── sensors/             # Per-area sensor definitions (space_weather, surf, alerts,
│                        #   forecasts, hurricanes, weather_observations, weather_extra,
│                        #   meteor_showers)
├── translations/        # en.json
└── brand/               # Brand images served by HA (icon/logo, incl. @2x and dark)
```

### Configuration Files
- `.github/workflows/hacs-validate.yml` - HACS validation workflow (currently manual trigger only)
- `hacs.json` - HACS integration configuration
- `README.md` - Basic setup instructions for users

### Important Code Patterns
- **Sensor Updates**: All sensors use 5-minute scan intervals (`SCAN_INTERVAL = timedelta(minutes=5)`)
- **API Timeouts**: All HTTP requests use 30-second timeouts (`REQUEST_TIMEOUT = 30`)
- **Error Handling**: APIs return 'Error' or 'unknown' states when data unavailable
- **Image Caching**: Images use timestamp-based cache busting for updates

## Common Development Tasks

### Adding New Sensors
1. Add sensor class to `sensor.py` following existing patterns
2. Include in `setup_platform()` function
3. Update manifest version in `manifest.json`
4. Test with syntax validation and linting

### Modifying API Endpoints
1. Update URL constants in respective files
2. Validate new endpoints with curl commands
3. Test error handling for invalid responses
4. Update timeout values if needed for slower endpoints

### Code Style Requirements
- Maximum line length: 120 characters
- Follow PEP 8 standards with flake8 validation
- Use proper spacing around functions and classes (2 blank lines)
- Remove unused imports
- Handle exceptions properly with logging

## Build and Deployment

**IMPORTANT**: This is NOT a traditional application with build steps. It's a Python module for Home Assistant.

### No Build Process Required
- This integration does not require compilation or building
- Files are used directly by Home Assistant as Python modules
- Changes take effect when Home Assistant restarts or components reload

### Deployment Process
1. Code validation (syntax + linting)
2. HACS validation workflow passes
3. Release through HACS distribution
4. Users install via HACS in Home Assistant

### Version Management
- Update version in `custom_components/noaa_it_all/manifest.json`
- Version format: semantic versioning (e.g., "1.0.12")
- HACS uses manifest version for release tracking

## Troubleshooting Common Issues

### Import Errors
- Ensure all dependencies are installed: `pip install requests aiohttp`
- Check Python path includes component directory

### API Connection Issues
- NOAA APIs may have rate limiting or temporary outages
- Always implement proper timeout and error handling
- Test API availability with curl commands

### HACS Validation Failures
- Most common: linting errors (use flake8 to identify)
- Manifest JSON format issues (validate with Python json module)
- Missing required fields in manifest.json

### Performance Considerations
- API calls are asynchronous where possible (image.py)
- 5-minute update intervals prevent API overload
- Proper timeout handling prevents hanging requests

## External Dependencies and Limitations

### Required Python Packages
- `requests>=2.31.0` - for synchronous HTTP requests in sensors
- `aiohttp>=3.12.0` - for asynchronous HTTP requests in image entities

### Home Assistant Integration
- Requires Home Assistant 2024.9.1+ (specified in hacs.json)
- Uses discovery platform loading (legacy method)
- No config flow - uses YAML configuration

### Network Dependencies
- Requires internet access to NOAA Space Weather Prediction Center
- APIs may be intermittently unavailable
- No offline functionality - shows error states when disconnected

## Time Expectations

### Development Tasks
- Syntax validation: <1 second
- Code linting: <5 seconds  
- Dependency installation: 10-15 seconds
- HACS validation workflow: 2-5 minutes - **NEVER CANCEL**
- Manual API testing: 5-10 seconds per endpoint

### CI/CD Pipeline
- HACS validation in GitHub Actions: 2-5 minutes - **NEVER CANCEL**
- No additional build or test phases required
- Workflow runs on manual trigger (`workflow_dispatch`)

**CRITICAL REMINDER**: Always allow sufficient time for validation. Set timeouts of 10+ minutes for any CI operations. This integration has no traditional build process but relies on validation workflows that must complete successfully.