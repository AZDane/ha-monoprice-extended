cat > README.md <<'EOF'
# Monoprice 6-Zone Amplifier (Extended)

Extends the Home Assistant Monoprice integration with:
- Configurable unit count (1–3) to avoid polling non-existent zones
- Per-zone Bass and Treble controls (Number entities)

## Installation (manual)
Copy `custom_components/monoprice` into your Home Assistant `/config/custom_components/monoprice/` and restart Home Assistant.

## Configure
Settings → Devices & services → Monoprice → Configure → Units (1–3)
EOF
