# Monoprice 6-Zone Amplifier (Extended)

Extends the Home Assistant Monoprice integration with:
- Configurable unit count (1–3) to avoid polling non-existent zones
- Per-zone Bass and Treble controls (Number entities)
- Improved responsiveness by avoiding polling non-existent zones

## Installation

### HACS (Custom Repository)
1. HACS → Integrations → ⋮ → Custom repositories
2. Add repository: `AZDane/ha-monoprice-extended`
3. Category: Integration
4. Install and restart Home Assistant

### Manual
Copy `custom_components/monoprice` into:
`/config/custom_components/monoprice`

Restart Home Assistant.

## Configuration
Settings → Devices & services → Monoprice → Configure → Number of amplifier units (1–3)

## Notes
- Drop-in replacement for the core Monoprice integration
- Uses the existing Monoprice serial protocol
- No hardware changes required
